"""wiki_bootstrap — idempotent schema bootstrap for an Anytype space.

Creates (or skips, if already present) the six canonical wiki Types and their
Properties (created-and-linked inline via the create-type API), the default
domain-tag taxonomy (multi-select options on ``wiki_domain_tags``), a root
"Wiki" Collection, and a WikiLog entry recording the run. The WikiLog entry is
stamped with the running ``wiki_schema_version`` and is the marker read back for
upgrade detection. Idempotency is driven from the WikiClient list-helpers
(existing items are detected via GET and reported as ``*_skipped``).

Error handling follows the spec's three-category model:
- Anytype unreachable (``httpx.ConnectError`` / ``ConnectTimeout`` /
  ``TransportError``) → ``[API ERROR]`` with instructions to start the desktop
  app.
- Missing space (HTTP 404) → ``[CONFIG ERROR]`` with the space_id echoed.
- Insufficient token scope (HTTP 403) → ``[CONFIG ERROR] insufficient_token_scope``
  pointing at Anytype Settings → API.

Schema-upgrade exception (spec §Schema Compatibility, bootstrap-specific clause):
when an existing WikiLog marker carries a ``wiki_schema_version`` older than the
running code's ``WIKI_SCHEMA_VERSION``, bootstrap does NOT short-circuit with
``wiki_schema_outdated`` (that would be a self-recursive remediation loop).
Instead it proceeds with an idempotent upgrade and returns a ``schema_upgrade``
section in the result. The fresh WikiLog entry stamps the new version, so the
next bootstrap detects it.

API-contract notes are documented in ``types_schema`` (verified live against the
Anytype local API, version 2025-11-08).
"""

import logging
from datetime import datetime, timezone

import httpx

from . import types_schema
from .wiki_client import WikiClient

logger = logging.getLogger(__name__)

# The Anytype object type used for the root wiki Collection. The live type key
# for collections is "collection" (NOT "ot-collection").
_ROOT_COLLECTION_TYPE_KEY = "collection"
_ROOT_COLLECTION_NAME = "Wiki"
_DOMAIN_TAGS_PROPERTY_KEY = types_schema.DOMAIN_TAGS_PROPERTY_KEY
_SCHEMA_VERSION_PROPERTY_KEY = types_schema.SCHEMA_VERSION_PROPERTY_KEY
_ACTION_PROPERTY_KEY = "wiki_action"
_STATUS_PROPERTY_KEY = "wiki_status"
_SOURCE_TYPE_PROPERTY_KEY = "wiki_source_type"

# The six canonical wiki_action select values (Decision 3 + #289 D5). Seeded as
# tags on the wiki_action property so every wiki tool can stamp its WikiLog with
# the action that produced it. v0.3.1 adds "remember".
_WIKI_ACTION_TAGS = ["ingest", "query", "lint", "bootstrap", "archive", "remember"]

# wiki_status select values (#289 D5 Change 2): conflict review lifecycle.
_WIKI_STATUS_TAGS = ["needs-review", "reviewed", "archived"]

# wiki_source_type select values (#289 D5 Change 3): provenance classification.
_WIKI_SOURCE_TYPE_TAGS = ["document", "conversation", "agent"]

# Anytype property formats → the typed field name used in a PropertyLinkWithValue
# entry when writing an object.
_FORMAT_VALUE_FIELD = {
    "text": "text",
    "number": "number",
    "date": "date",
    "url": "url",
    "email": "email",
    "phone": "phone",
    "checkbox": "checkbox",
    "select": "select",
    "multi_select": "multi_select",
    "objects": "objects",
    "files": "files",
}


def _type_deeplink(space_id: str, type_key: str) -> str:
    return f"anytype://type/{space_id}/{type_key}"


def _object_deeplink(space_id: str, object_id: str) -> str:
    return f"anytype://object/{space_id}/{object_id}"


def _now_iso() -> str:
    """UTC timestamp in the ``...Z`` ISO-8601 form Anytype's date fields accept."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _version_tuple(version: str) -> tuple[int, ...]:
    """Parse a dotted version string into a tuple of ints for comparison.

    Non-integer components are treated as 0. Missing trailing components are
    padded to 0 so semantically-equal versions of differing arity compare equal
    (e.g. ``_version_tuple("0.2") == _version_tuple("0.2.0")``). Versions with
    more than three components retain all of them.
    """
    parts: list[int] = []
    for part in str(version).split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def _found_schema_version(obj: dict) -> str | None:
    """Read a wiki_schema_version off an object.

    Tolerates the real Anytype shape (``properties`` is a *list* of
    ``{"key": ..., "text": ...}`` entries), a legacy/mock dict shape, and a
    top-level key.
    """
    if not isinstance(obj, dict):
        return None
    top = obj.get(_SCHEMA_VERSION_PROPERTY_KEY)
    if top:
        return top
    props = obj.get("properties")
    if isinstance(props, dict):
        nested = props.get(_SCHEMA_VERSION_PROPERTY_KEY)
        if nested:
            return nested
    if isinstance(props, list):
        for p in props:
            if isinstance(p, dict) and p.get("key") == _SCHEMA_VERSION_PROPERTY_KEY:
                val = p.get("text") or p.get("select")
                if val:
                    return val
    return None


def _max_version(a: str | None, b: str | None) -> str | None:
    """Return the higher of two (possibly-None) version strings."""
    if a is None:
        return b
    if b is None:
        return a
    return a if _version_tuple(a) >= _version_tuple(b) else b


def _empty_result(space_id: str) -> dict:
    """Build the base BootstrapResult skeleton with all required keys."""
    return {
        "space_id": space_id,
        "types_created": [],
        "types_skipped": [],
        "properties_created": [],
        "properties_skipped": [],
        "tags_created": [],
        "tags_skipped": [],
        "root_collection_id": None,
        "root_collection_deeplink": None,
        "wiki_log_id": None,
        "wiki_log_deeplink": None,
        "status": "ok",
        "warnings": [],
    }


def _api_error(result: dict, exc: Exception) -> dict:
    """Populate the result for an unreachable-Anytype condition (AC #4)."""
    msg = (
        "[API ERROR] api_error: cannot reach the Anytype desktop app at the "
        "configured ANYTYPE_API_URL. Start the Anytype desktop application and "
        "ensure its local API is enabled, then re-run wiki_bootstrap. "
        f"(transport error: {type(exc).__name__})"
    )
    result["status"] = "error"
    result["error"] = msg
    result["error_category"] = "api_error"
    result["warnings"].append(msg)
    logger.error(msg)
    return result


def _config_error_missing_space(result: dict, space_id: str) -> dict:
    """Populate the result for a missing-space condition (AC #3)."""
    msg = (
        f"[CONFIG ERROR] wiki_space_missing: space {space_id} was not found. "
        "Check the space_id and that the Anytype API key has access to it."
    )
    result["status"] = "error"
    result["error"] = msg
    result["error_category"] = "config_error"
    result["warnings"].append(msg)
    logger.error(msg)
    return result


def _config_error_insufficient_scope(result: dict) -> dict:
    """Populate the result for a 403 insufficient-token-scope condition (AC #9)."""
    msg = (
        "[CONFIG ERROR] insufficient_token_scope: the configured ANYTYPE_API_KEY "
        "cannot create Types in this space. Regenerate with write scope via "
        "Anytype Settings → API."
    )
    result["status"] = "error"
    result["error"] = msg
    result["error_category"] = "config_error"
    result["warnings"].append(msg)
    logger.error(msg)
    return result


def wiki_bootstrap(space_id: str, domain_tags: list[str] | None = None) -> dict:
    """Idempotently create the wiki schema in an Anytype space.

    Args:
        space_id: Target Anytype space ID.
        domain_tags: Optional override for the domain-tag taxonomy. On a FIRST
            bootstrap (no existing tags) these replace the defaults. On a
            re-bootstrap (tags already exist) the semantic is union-only: only
            tags not already present are created; existing tags are preserved.

    Returns:
        A BootstrapResult dict. On error conditions returns ``status="error"``
        with a ``[API ERROR]`` / ``[CONFIG ERROR]`` message reachable via
        ``str(result)``.
    """
    result = _empty_result(space_id)
    client = WikiClient()
    try:
        return _run_bootstrap(client, space_id, domain_tags, result)
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.TransportError) as exc:
        return _api_error(result, exc)
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        if status_code == 404:
            return _config_error_missing_space(result, space_id)
        if status_code == 403:
            return _config_error_insufficient_scope(result)
        msg = (
            f"[API ERROR] api_error: Anytype returned HTTP {status_code} during "
            "bootstrap."
        )
        result["status"] = "error"
        result["error"] = msg
        result["error_category"] = "api_error"
        result["warnings"].append(msg)
        logger.error(msg)
        return result
    finally:
        client.close()


def _run_bootstrap(
    client: WikiClient,
    space_id: str,
    domain_tags: list[str] | None,
    result: dict,
) -> dict:
    """Core bootstrap flow. Raises httpx errors for the wrapper to categorize."""
    # --- detect existing schema version (from any WikiLog marker) ------------
    existing_objects = client.list_objects(space_id)
    root_collection = _find_root_collection(existing_objects)
    found_version: str | None = None
    for obj in existing_objects:
        found_version = _max_version(found_version, _found_schema_version(obj))

    is_upgrade = (
        found_version is not None
        and _version_tuple(found_version) < _version_tuple(types_schema.WIKI_SCHEMA_VERSION)
    )

    # --- Types (inline properties are created AND linked in one call) --------
    existing_types = client.list_types(space_id)
    existing_type_keys = {t.get("key") for t in existing_types if t.get("key")}
    pre_existing_prop_keys = {
        p.get("key") or p.get("property_key")
        for p in client.list_properties(space_id)
        if (p.get("key") or p.get("property_key"))
    }

    for type_def in types_schema.WIKI_TYPES:
        type_key = type_def["type_key"]
        if type_key in existing_type_keys:
            result["types_skipped"].append(
                {"type_key": type_key, "reason": "already_exists"}
            )
            continue
        created = client.create_type(
            space_id,
            {
                "key": type_key,
                "name": type_def["name"],
                "plural_name": type_def["plural_name"],
                "layout": type_def["layout"],
                "properties": [
                    {
                        "key": p["property_key"],
                        "name": p["name"],
                        "format": p["format"],
                    }
                    for p in type_def.get("properties", [])
                ],
            },
        )
        result["types_created"].append(
            {
                "type_key": type_key,
                "object_id": created.get("id"),
                "deeplink": _type_deeplink(space_id, type_key),
            }
        )

    # --- Properties: report created/skipped, build key->id map ---------------
    prop_map: dict[str, str | None] = {}
    for p in client.list_properties(space_id):
        key = p.get("key") or p.get("property_key")
        if key:
            prop_map[key] = p.get("id")

    # Inline-created properties may not yet surface an id via list_properties on a
    # first bootstrap. Anytype keys the tag endpoints by property key OR id, so
    # fall back to the property key for any known wiki property whose id is
    # unresolved — this keeps domain/action tag creation reachable.
    for type_def in types_schema.WIKI_TYPES:
        for prop in type_def.get("properties", []):
            pk = prop["property_key"]
            if not prop_map.get(pk):
                prop_map[pk] = pk

    properties_added: list[str] = []
    seen_prop_keys: set[str] = set()
    for type_def in types_schema.WIKI_TYPES:
        type_key = type_def["type_key"]
        for prop in type_def.get("properties", []):
            property_key = prop["property_key"]
            if property_key in seen_prop_keys:
                continue
            seen_prop_keys.add(property_key)
            if property_key in pre_existing_prop_keys:
                result["properties_skipped"].append(
                    {
                        "type_key": type_key,
                        "property_key": property_key,
                        "reason": "already_exists",
                    }
                )
            else:
                result["properties_created"].append(
                    {
                        "type_key": type_key,
                        "property_key": property_key,
                        "property_id": prop_map.get(property_key),
                    }
                )
                properties_added.append(property_key)

    # --- Domain tags (multi-select options on wiki_domain_tags) --------------
    domain_pid = prop_map.get(_DOMAIN_TAGS_PROPERTY_KEY)
    if domain_pid:
        existing_tags = client.list_tags(space_id, domain_pid)
        existing_tag_names = {t.get("name") for t in existing_tags if t.get("name")}

        if existing_tag_names:
            # Re-bootstrap: union-only. Preserve existing (skip); create only
            # argument tags not already present.
            for name in existing_tag_names:
                result["tags_skipped"].append(
                    {
                        "property_key": _DOMAIN_TAGS_PROPERTY_KEY,
                        "tag": name,
                        "reason": "already_exists",
                    }
                )
            new_tags = [t for t in (domain_tags or []) if t not in existing_tag_names]
        else:
            # First bootstrap: custom domain_tags replace the defaults entirely.
            new_tags = (
                domain_tags
                if domain_tags is not None
                else types_schema.DEFAULT_DOMAIN_TAGS
            )

        palette = types_schema.TAG_COLOR_PALETTE
        for i, tag in enumerate(new_tags):
            color = palette[i % len(palette)]
            tag_id = _create_tag(client, space_id, domain_pid, tag, color)
            result["tags_created"].append(
                {
                    "property_key": _DOMAIN_TAGS_PROPERTY_KEY,
                    "tag": tag,
                    "tag_id": tag_id,
                }
            )
    else:
        result["warnings"].append(
            f"domain-tag taxonomy skipped: property '{_DOMAIN_TAGS_PROPERTY_KEY}' "
            "id could not be resolved after type creation."
        )

    # --- wiki_action select tags (Decision 3) --------------------------------
    action_tag_map = _ensure_wiki_action_tags(client, space_id, prop_map, result)

    # --- wiki_status / wiki_source_type select tags (#289 D5) ----------------
    status_tag_map = _ensure_wiki_status_tags(client, space_id, prop_map, result)
    source_type_tag_map = _ensure_wiki_source_type_tags(client, space_id, prop_map, result)

    # --- Root Collection -----------------------------------------------------
    if root_collection is not None:
        collection_id = root_collection.get("id")
    else:
        collection_id = _create_object(
            client,
            space_id,
            type_key=_ROOT_COLLECTION_TYPE_KEY,
            name=_ROOT_COLLECTION_NAME,
            properties=None,
        )
    result["root_collection_id"] = collection_id
    if collection_id:
        result["root_collection_deeplink"] = _object_deeplink(space_id, collection_id)
        # Primary schema marker (Decision 2, Option a): stamp the running version
        # onto the root Collection. Best-effort — the WikiLog stamp below is the
        # retained fallback. A patch failure must not fail bootstrap.
        patched = _patch_schema_version_on_collection(
            client, space_id, collection_id, types_schema.WIKI_SCHEMA_VERSION
        )
        if not patched:
            logger.warning(
                "wiki_schema_version marker PATCH on root Collection %s failed; "
                "relying on WikiLog stamp fallback.",
                collection_id,
            )

    # --- schema_upgrade section ---------------------------------------------
    if is_upgrade:
        result["schema_upgrade"] = {
            "from": found_version,
            "to": types_schema.WIKI_SCHEMA_VERSION,
            "properties_added": properties_added,
        }
        logger.info(
            "wiki_schema_upgrade_started from=%s to=%s properties_added=%d",
            found_version,
            types_schema.WIKI_SCHEMA_VERSION,
            len(properties_added),
        )

    # --- WikiLog entry (best-effort; stamps the schema version) --------------
    total_created = (
        len(result["types_created"])
        + len(result["properties_created"])
        + len(result["tags_created"])
    )
    try:
        log_entries: list[tuple[str, str, object]] = [
            ("wiki_subject", "text", _ROOT_COLLECTION_NAME),
            ("wiki_objects_created", "number", total_created),
            ("wiki_timestamp", "date", _now_iso()),
            ("wiki_notes", "text", f"schema_version={types_schema.WIKI_SCHEMA_VERSION}"),
            (_SCHEMA_VERSION_PROPERTY_KEY, "text", types_schema.WIKI_SCHEMA_VERSION),
        ]
        # Stamp wiki_action=bootstrap when the tag id is resolvable (Decision 3,
        # AC-T3). Tolerant: an unresolved tag simply omits the action prop.
        bootstrap_tag_id = action_tag_map.get("bootstrap")
        if bootstrap_tag_id:
            log_entries.append((_ACTION_PROPERTY_KEY, "select", bootstrap_tag_id))
        log_props = _build_props_list(log_entries)
        log_id = _create_object(
            client,
            space_id,
            type_key="wiki_log",
            name=f"bootstrap {_now_iso()}",
            properties=log_props,
        )
        result["wiki_log_id"] = log_id
        if log_id:
            result["wiki_log_deeplink"] = _object_deeplink(space_id, log_id)
    except httpx.HTTPStatusError as exc:
        result["warnings"].append(
            "WikiLog entry could not be written (HTTP "
            f"{exc.response.status_code if exc.response else '?'}); "
            "bootstrap otherwise succeeded."
        )

    return result


def _schema_version_from_objects(objects: list[dict]) -> str | None:
    """Derive the live schema-version marker from an already-fetched object list.

    Primary source: the root "Wiki" Collection's ``wiki_schema_version`` property
    (G4 guard — BOTH name=='Wiki' AND type.key=='collection' required so a stray
    object named "Wiki" cannot spoof the marker). Fallback: the maximum version
    across all ``wiki_log`` objects. Returns ``max(collection, wikilog)`` so a
    stale collection marker cannot mask a newer WikiLog (SF7); None if neither
    carries a marker. Pure — does no I/O so callers that already enumerated the
    space can avoid a second ``list_objects`` (N+1).
    """
    collection_value: str | None = None
    wikilog_max: str | None = None
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        t = obj.get("type")
        type_key = t.get("key") if isinstance(t, dict) else t
        if obj.get("name") == _ROOT_COLLECTION_NAME and type_key == _ROOT_COLLECTION_TYPE_KEY:
            collection_value = _found_schema_version(obj)
        if type_key == "wiki_log":
            wikilog_max = _max_version(wikilog_max, _found_schema_version(obj))

    return _max_version(collection_value, wikilog_max)


def _read_schema_version(client, space_id: str) -> str | None:
    """Read the live schema-version marker for a space (Decision 2, Option a).

    Enumerates the space then delegates the marker scan to
    ``_schema_version_from_objects``.
    """
    objects = client.list_objects(space_id)
    return _schema_version_from_objects(objects)


def _patch_schema_version_on_collection(
    client, space_id: str, collection_id: str, version: str
) -> bool:
    """Best-effort PATCH of ``wiki_schema_version`` onto the root Collection.

    Returns True on success, False on any exception. The caller treats failure
    as non-fatal (the WikiLog stamp remains the fallback marker).
    """
    try:
        client.update_object(
            space_id,
            collection_id,
            {"properties": [{"key": _SCHEMA_VERSION_PROPERTY_KEY, "text": version}]},
        )
        return True
    except Exception:  # noqa: BLE001 — best-effort marker write, must not fail bootstrap
        return False


def _ensure_wiki_action_tags(
    client, space_id: str, prop_map: dict, result: dict
) -> dict[str, str]:
    """Seed the five wiki_action select tags idempotently (Decision 3).

    Records created/skipped tags into ``result`` and returns a name→id map built
    from a final ``list_tags`` read. Returns {} if the wiki_action property id is
    unresolved.
    """
    action_pid = prop_map.get(_ACTION_PROPERTY_KEY)
    if not action_pid:
        return {}

    existing = {t["name"] for t in client.list_tags(space_id, action_pid) if t.get("name")}
    palette = types_schema.TAG_COLOR_PALETTE

    for i, name in enumerate(_WIKI_ACTION_TAGS):
        if name in existing:
            result["tags_skipped"].append(
                {
                    "property_key": _ACTION_PROPERTY_KEY,
                    "tag": name,
                    "reason": "already_exists",
                }
            )
            continue
        color = palette[i % len(palette)]
        tag_id = _create_tag(client, space_id, action_pid, name, color)
        result["tags_created"].append(
            {"property_key": _ACTION_PROPERTY_KEY, "tag": name, "tag_id": tag_id}
        )

    return {
        t["name"]: t.get("id")
        for t in client.list_tags(space_id, action_pid)
        if t.get("name")
    }


def _ensure_select_tags(
    client,
    space_id: str,
    prop_map: dict,
    result: dict,
    property_key: str,
    tag_names: list[str],
) -> dict[str, str]:
    """Seed a select property's tags idempotently (union-only), mirroring
    ``_ensure_wiki_action_tags`` exactly.

    Resolves the property id via ``prop_map`` (NOT an independent
    ``list_properties`` lookup — B3), so a fresh space's key-as-id fallback
    keeps tag creation reachable. Records created/skipped tags into ``result``
    with the right ``property_key`` and returns a name→id map from a final
    ``list_tags`` read. Returns {} if the property id is unresolved.
    """
    pid = prop_map.get(property_key)
    if not pid:
        return {}

    existing_tags = client.list_tags(space_id, pid)
    existing = {t["name"] for t in existing_tags if t.get("name")}
    palette = types_schema.TAG_COLOR_PALETTE

    name_to_id: dict[str, str] = {
        t["name"]: t.get("id") for t in existing_tags if t.get("name")
    }

    for i, name in enumerate(tag_names):
        if name in existing:
            result["tags_skipped"].append(
                {
                    "property_key": property_key,
                    "tag": name,
                    "reason": "already_exists",
                }
            )
            continue
        color = palette[i % len(palette)]
        tag_id = _create_tag(client, space_id, pid, name, color)
        result["tags_created"].append(
            {"property_key": property_key, "tag": name, "tag_id": tag_id}
        )
        if tag_id is not None:
            name_to_id[name] = tag_id

    # Merge a final read so a backend that reflects newly-created tags supplies
    # any ids the create responses omitted; created ids above cover backends
    # whose list_tags does not yet surface fresh tags (fresh-space key fallback).
    for t in client.list_tags(space_id, pid):
        if t.get("name"):
            name_to_id.setdefault(t["name"], t.get("id"))

    return name_to_id


def _ensure_wiki_status_tags(
    client, space_id: str, prop_map: dict, result: dict
) -> dict[str, str]:
    """Seed wiki_status select tags idempotently (union-only — #289 D5 Change 2).

    Returns name→id map. Returns {} if the property id is unresolved.
    """
    return _ensure_select_tags(
        client, space_id, prop_map, result, _STATUS_PROPERTY_KEY, _WIKI_STATUS_TAGS
    )


def _ensure_wiki_source_type_tags(
    client, space_id: str, prop_map: dict, result: dict
) -> dict[str, str]:
    """Seed wiki_source_type select tags idempotently (union-only — #289 D5 Change 3).

    Returns name→id map. Returns {} if the property id is unresolved.
    """
    return _ensure_select_tags(
        client, space_id, prop_map, result, _SOURCE_TYPE_PROPERTY_KEY,
        _WIKI_SOURCE_TYPE_TAGS,
    )


def _build_props_list(entries: list[tuple[str, str, object]]) -> list[dict]:
    """Build a PropertyLinkWithValue array from ``(key, format, value)`` tuples.

    Skips entries whose value is None/empty. Unknown formats fall back to a
    ``text`` field with the stringified value.
    """
    out: list[dict] = []
    for key, fmt, value in entries:
        if value is None or value == "":
            continue
        field = _FORMAT_VALUE_FIELD.get(fmt, "text")
        out.append({"key": key, field: value})
    return out


def _create_tag(
    client: WikiClient, space_id: str, property_id: str, tag: str, color: str
) -> str | None:
    """Create a domain tag (name + required color), tolerating a mock 2xx body."""
    try:
        created = client.create_tag(space_id, property_id, {"name": tag, "color": color})
        return created.get("id")
    except KeyError:
        return None


def _create_object(
    client: WikiClient,
    space_id: str,
    type_key: str,
    name: str,
    properties: list | None,
) -> str | None:
    """Create an object, tolerating a mock 2xx response missing the envelope."""
    try:
        created = client.create_object(space_id, type_key, name, properties)
        return created.get("id")
    except KeyError:
        return None


def _find_root_collection(objects: list[dict]) -> dict | None:
    """Locate an existing root wiki Collection among listed objects (by name)."""
    for obj in objects:
        if isinstance(obj, dict) and obj.get("name") == _ROOT_COLLECTION_NAME:
            return obj
    return None
