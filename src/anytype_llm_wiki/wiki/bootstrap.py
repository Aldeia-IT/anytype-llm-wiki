"""wiki_bootstrap — idempotent schema bootstrap for an Anytype space.

Creates (or skips, if already present) the six canonical wiki Types, their
Properties, the default domain-tag taxonomy, a root Collection carrying the
schema version, and a WikiLog entry recording the run. Idempotency is driven
from the WikiClient list-helpers (existing items are detected via GET and
reported as ``*_skipped``).

Error handling follows the spec's three-category model:
- Anytype unreachable (``httpx.ConnectError`` / ``ConnectTimeout`` /
  ``TransportError``) → ``[API ERROR]`` with instructions to start the desktop
  app.
- Missing space (HTTP 404) → ``[CONFIG ERROR]`` with the space_id echoed.
- Insufficient token scope (HTTP 403) → ``[CONFIG ERROR] insufficient_token_scope``
  pointing at Anytype Settings → API.

Schema-upgrade exception (spec §Schema Compatibility, bootstrap-specific clause):
when an existing root Collection carries a ``wiki_schema_version`` older than the
running code's ``WIKI_SCHEMA_VERSION``, bootstrap does NOT short-circuit with
``wiki_schema_outdated`` (that would be a self-recursive remediation loop).
Instead it proceeds with an idempotent upgrade and returns a ``schema_upgrade``
section in the result.
"""

import logging
from datetime import datetime, timezone

import httpx

from . import types_schema
from .wiki_client import WikiClient

logger = logging.getLogger(__name__)

# The Anytype object type used for the root wiki Collection. Anytype's
# system collection type key.
_ROOT_COLLECTION_TYPE_KEY = "ot-collection"
_ROOT_COLLECTION_NAME = "Wiki"
_DOMAIN_TAGS_PROPERTY_KEY = "wiki_domain_tags"


def _type_deeplink(space_id: str, type_key: str) -> str:
    return f"anytype://type/{space_id}/{type_key}"


def _object_deeplink(space_id: str, object_id: str) -> str:
    return f"anytype://object/{space_id}/{object_id}"


def _version_tuple(version: str) -> tuple[int, ...]:
    """Parse a dotted version string into a tuple of ints for comparison.

    Non-integer components are treated as 0; missing components pad to 0.
    """
    parts: list[int] = []
    for part in str(version).split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _found_schema_version(obj: dict) -> str | None:
    """Read a wiki_schema_version off an object, checking top-level then properties."""
    if not isinstance(obj, dict):
        return None
    top = obj.get("wiki_schema_version")
    if top:
        return top
    props = obj.get("properties")
    if isinstance(props, dict):
        nested = props.get("wiki_schema_version")
        if nested:
            return nested
    return None


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
        # Other HTTP errors degrade to a generic API error rather than crashing.
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
    # --- detect existing schema version for the upgrade path -----------------
    existing_objects = client.list_objects(space_id)
    root_collection = _find_root_collection(existing_objects)
    found_version: str | None = None
    for obj in existing_objects:
        v = _found_schema_version(obj)
        if v:
            found_version = v
            break
    if root_collection is not None and found_version is None:
        found_version = _found_schema_version(root_collection)

    is_upgrade = (
        found_version is not None
        and _version_tuple(found_version) < _version_tuple(types_schema.WIKI_SCHEMA_VERSION)
    )

    # --- Types ---------------------------------------------------------------
    existing_types = client.list_types(space_id)
    existing_type_keys = {t.get("key") for t in existing_types if t.get("key")}
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
                "properties": type_def.get("properties", []),
            },
        )
        result["types_created"].append(
            {
                "type_key": type_key,
                "object_id": created.get("id"),
                "deeplink": _type_deeplink(space_id, type_key),
            }
        )

    # --- Properties ----------------------------------------------------------
    existing_props = client.list_properties(space_id)
    existing_prop_keys = {
        p.get("property_key") or p.get("key")
        for p in existing_props
        if (p.get("property_key") or p.get("key"))
    }
    properties_added: list[str] = []
    for type_def in types_schema.WIKI_TYPES:
        type_key = type_def["type_key"]
        for prop in type_def.get("properties", []):
            property_key = prop["property_key"]
            if property_key in existing_prop_keys:
                result["properties_skipped"].append(
                    {
                        "type_key": type_key,
                        "property_key": property_key,
                        "reason": "already_exists",
                    }
                )
                continue
            property_id = None
            try:
                created = client.create_property(
                    space_id,
                    type_key,
                    {"key": property_key, "format": prop["format"]},
                )
                property_id = created.get("id")
            except KeyError:
                # The create succeeded (2xx) but the response body lacked the
                # "property" envelope key; record the creation without an id.
                property_id = None
            result["properties_created"].append(
                {
                    "type_key": type_key,
                    "property_key": property_key,
                    "property_id": property_id,
                }
            )
            properties_added.append(property_key)
            # A property_key may be shared across types (e.g. wiki_domain_tags);
            # mark it created so the second type reports it as skipped.
            existing_prop_keys.add(property_key)

    # --- Domain tags ---------------------------------------------------------
    existing_tags = client.list_tags(space_id, _DOMAIN_TAGS_PROPERTY_KEY)
    existing_tag_names = {t.get("name") for t in existing_tags if t.get("name")}

    if existing_tag_names:
        # Re-bootstrap: union-only. Preserve all existing tags (skip), create
        # only argument tags that are not already present.
        for name in existing_tag_names:
            result["tags_skipped"].append(
                {
                    "property_key": _DOMAIN_TAGS_PROPERTY_KEY,
                    "tag": name,
                    "reason": "already_exists",
                }
            )
        target_tags = domain_tags or []
        for tag in target_tags:
            if tag in existing_tag_names:
                continue
            tag_id = _create_tag(client, space_id, tag)
            result["tags_created"].append(
                {
                    "property_key": _DOMAIN_TAGS_PROPERTY_KEY,
                    "tag": tag,
                    "tag_id": tag_id,
                }
            )
            existing_tag_names.add(tag)
    else:
        # First bootstrap: custom domain_tags replace the defaults entirely.
        target_tags = (
            domain_tags if domain_tags is not None else types_schema.DEFAULT_DOMAIN_TAGS
        )
        for tag in target_tags:
            tag_id = _create_tag(client, space_id, tag)
            result["tags_created"].append(
                {
                    "property_key": _DOMAIN_TAGS_PROPERTY_KEY,
                    "tag": tag,
                    "tag_id": tag_id,
                }
            )

    # --- Root Collection -----------------------------------------------------
    if root_collection is not None:
        collection_id = root_collection.get("id")
        result["root_collection_id"] = collection_id
        if collection_id:
            result["root_collection_deeplink"] = _object_deeplink(space_id, collection_id)
        if is_upgrade and collection_id:
            # Bring the recorded schema version forward (idempotent upgrade).
            try:
                client.update_object(
                    space_id,
                    collection_id,
                    {
                        "properties": {
                            "wiki_schema_version": types_schema.WIKI_SCHEMA_VERSION
                        }
                    },
                )
            except httpx.HTTPStatusError as exc:  # pragma: no cover - defensive
                result["warnings"].append(
                    f"schema_version PATCH failed (HTTP "
                    f"{exc.response.status_code if exc.response else '?'}); "
                    "re-run bootstrap to retry."
                )
    else:
        collection_id = _create_object(
            client,
            space_id,
            type_key=_ROOT_COLLECTION_TYPE_KEY,
            name=_ROOT_COLLECTION_NAME,
            properties={"wiki_schema_version": types_schema.WIKI_SCHEMA_VERSION},
        )
        result["root_collection_id"] = collection_id
        if collection_id:
            result["root_collection_deeplink"] = _object_deeplink(space_id, collection_id)

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

    # --- WikiLog entry (best-effort) -----------------------------------------
    try:
        log_id = _create_object(
            client,
            space_id,
            type_key="wiki_log",
            name=f"bootstrap {datetime.now(timezone.utc).isoformat()}",
            properties={
                "wiki_action": "bootstrap",
                "wiki_subject": _ROOT_COLLECTION_NAME,
                "wiki_objects_created": (
                    len(result["types_created"])
                    + len(result["properties_created"])
                    + len(result["tags_created"])
                ),
                "wiki_timestamp": datetime.now(timezone.utc).isoformat(),
                "wiki_notes": f"schema_version={types_schema.WIKI_SCHEMA_VERSION}",
            },
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


def _create_tag(client: WikiClient, space_id: str, tag: str) -> str | None:
    """Create a domain tag, tolerating a mock 2xx response missing the envelope."""
    try:
        created = client.create_tag(space_id, _DOMAIN_TAGS_PROPERTY_KEY, tag)
        return created.get("id")
    except KeyError:
        return None


def _create_object(
    client: WikiClient,
    space_id: str,
    type_key: str,
    name: str,
    properties: dict,
) -> str | None:
    """Create an object, tolerating a mock 2xx response missing the envelope."""
    try:
        created = client.create_object(space_id, type_key, name, properties)
        return created.get("id")
    except KeyError:
        return None


def _find_root_collection(objects: list[dict]) -> dict | None:
    """Locate an existing root wiki Collection among listed objects.

    A root collection is recognized either by name == "Wiki" or by carrying a
    ``wiki_schema_version`` marker (top-level or in properties).
    """
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        if obj.get("name") == _ROOT_COLLECTION_NAME:
            return obj
        if _found_schema_version(obj):
            return obj
    return None
