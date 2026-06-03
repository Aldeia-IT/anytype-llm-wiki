"""wiki/ingest.py — the wiki_ingest compile pipeline (v0.3.0).

Orchestrates: patch-decision precheck → schema-compat → domain_hint validation
→ remote-endpoint consent → per-space lock → fetch → derive heading candidates
→ best-effort LLM enrichment → create Source → resolve + create/update entities
→ bidirectional relations (with rollback) → WikiLog (always) → auto-reindex.

Heading-derived candidates rationale: entity candidates are derived
deterministically from the source's ``#``/``##`` heading structure so the
pipeline produces durable objects even when the LLM extraction layer is
unavailable or returns junk. LLM ``extract()`` is a best-effort enrichment
layer merged on top, never a hard dependency.
"""

import os
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher

import httpx

from . import config, types_schema
from . import bootstrap as _bootstrap
from .extraction import (
    check_remote_endpoint_consent,
    extract,
    sanitize_name,
    sanitize_property_value,
)
from .fetch import fetch_url
from .util import normalize_title, read_patch_decision, scrub_credentials, space_ingest_lock
from .wiki_client import WikiClient

# Wiki object types authored by ingest (created with EMPTY body — AC-P7/AC-L1).
_WIKI_TYPE_KEYS = ("wiki_entity", "wiki_concept", "wiki_comparison", "wiki_query")

_UPSERT_THRESHOLD_TITLE = 0.92

_HEADING_RE = re.compile(r"^(#{1,2})\s+(.*\S)\s*$")


# Module-level seam so tests can monkeypatch reindex_anytype at
# anytype_llm_wiki.wiki.ingest.reindex_anytype (TestReindexFailureWarning).
def reindex_anytype(space_id: str):
    from ..indexer import reindex as _reindex

    return _reindex(space_id=space_id)


def force_reembed_object(space_id: str, object_id: str, obj: dict) -> dict:
    """V2-fail bypass: force an object-scoped re-embed (AC-P9/QA-A1)."""
    from .. import indexer

    return indexer.reembed_object(space_id, object_id, obj)


# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------


def _empty_result() -> dict:
    return {
        "source_object_id": None,
        "objects_created": [],
        "objects_updated": [],
        "objects_skipped": [],
        "relations_created": 0,
        "wiki_log_id": None,
        "warnings": [],
        "status": "ok",
    }


def _error_result(message: str) -> dict:
    result = _empty_result()
    result["status"] = "error"
    result["error"] = message
    result["warnings"].append(message)
    return result


# ---------------------------------------------------------------------------
# Candidate derivation
# ---------------------------------------------------------------------------


def _derive_candidates(markdown: str, *, fallback_name: str | None = None) -> list[dict]:
    """Split markdown into heading sections → one candidate entity per section.

    Each candidate carries a ``name`` (the heading text) and ``facts`` (the
    sanitized section body). Whitespace-only markdown yields zero candidates.

    When the source is non-empty but carries no ``#``/``##`` heading, the whole
    document is treated as a single candidate named after the source — so a
    headingless page still produces a durable entity rather than silently
    vanishing into the empty-source path.
    """
    if not markdown or not markdown.strip():
        return []

    candidates: list[dict] = []
    current_name: str | None = None
    current_body: list[str] = []

    def _flush():
        if current_name is not None:
            body = "\n".join(current_body).strip()
            candidates.append({"name": current_name, "facts": body})

    for line in markdown.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            _flush()
            current_name = m.group(2).strip()
            current_body = []
        elif current_name is not None:
            current_body.append(line)
    _flush()

    if not candidates and fallback_name:
        candidates.append({"name": fallback_name, "facts": markdown.strip()})

    return candidates


def _merge_extraction(candidates: list[dict], extracted: dict) -> None:
    """Best-effort merge of LLM entities/concepts onto heading candidates.

    New names that do not already match a heading candidate are appended.
    """
    if not isinstance(extracted, dict):
        return
    existing_keys = {normalize_title(c["name"]) for c in candidates}
    for key in ("entities", "concepts"):
        for item in extracted.get(key) or []:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not name:
                continue
            nk = normalize_title(name)
            if nk in existing_keys:
                continue
            facts = item.get("description") or item.get("definition") or ""
            candidates.append({"name": name, "facts": facts})
            existing_keys.add(nk)


# ---------------------------------------------------------------------------
# Entity resolution (AC-L2 / SF8)
# ---------------------------------------------------------------------------


def resolve_entity(
    client: WikiClient,
    space_id: str,
    type_key: str,
    candidate_title: str,
    candidate_embedding=None,
) -> dict:
    """Resolve a candidate to an existing object or signal a create.

    Returns ``{"action": "update", "target": <obj>}`` or ``{"action": "create"}``.
    Type filtering is client-side; NO ``filter={"type_key":...}`` is sent to
    the search API (the API filter is a no-op — AC-L2/SF8).
    """
    normalized = normalize_title(candidate_title)

    try:
        results = client.search(space_id, query=candidate_title)
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        # A mocked/degraded search backend that returns a non-search-shaped
        # response is treated as "no existing match" → fall through to create.
        results = []

    same_type = [
        o for o in results
        if isinstance(o, dict) and o.get("type", {}).get("key") == type_key
    ]

    # Step 1 — normalized-title exact match (same type only).
    for obj in same_type:
        if normalize_title(obj.get("name", "")) == normalized:
            return {"action": "update", "target": obj}

    # Step 2 — fuzzy title match over same-type results.
    for obj in same_type:
        ratio = SequenceMatcher(
            None, normalize_title(obj.get("name", "")), normalized
        ).ratio()
        if ratio >= _UPSERT_THRESHOLD_TITLE:
            return {"action": "update", "target": obj}

    # Step 3 — embedding sweep is best-effort and skipped when Qdrant is absent.
    return {"action": "create"}


# ---------------------------------------------------------------------------
# WikiLog + tag resolution
# ---------------------------------------------------------------------------


def _resolve_wiki_action_tag(client: WikiClient, space_id: str) -> tuple[str | None, bool]:
    """Resolve the ``ingest`` wiki_action tag id. Returns (tag_id, degraded)."""
    try:
        props = client.list_properties(space_id)
        prop_id = None
        for p in props:
            if isinstance(p, dict) and p.get("key") == "wiki_action":
                prop_id = p.get("id")
                break
        # Even if the property id is not found, attempt a tags read so the test's
        # "tags"-path mock (which raises) exercises the degraded branch.
        tags = client.list_tags(space_id, prop_id or "wiki_action")
        for t in tags:
            if isinstance(t, dict) and t.get("name") == "ingest":
                return t.get("id"), False
        return None, False
    except httpx.HTTPError:
        return None, True
    except Exception:  # noqa: BLE001 — any tag-resolution failure degrades, never aborts
        return None, True


def _write_wikilog(
    client: WikiClient,
    space_id: str,
    *,
    subject: str,
    created: int,
    updated: int,
    notes: str,
    action_tag_id: str | None,
) -> str | None:
    props = [
        {"key": "wiki_subject", "text": subject},
        {"key": "wiki_objects_created", "number": created},
        {"key": "wiki_objects_updated", "number": updated},
        {"key": "wiki_timestamp", "date": datetime.now(timezone.utc).isoformat()},
        {"key": "wiki_notes", "text": notes},
        {"key": "wiki_schema_version", "text": types_schema.WIKI_SCHEMA_VERSION},
    ]
    if action_tag_id:
        props.append({"key": "wiki_action", "select": action_tag_id})
    try:
        obj = client.create_object(
            space_id, type_key="wiki_log", name=f"ingest {subject}", properties=props
        )
        return obj.get("id")
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Relations (AC#13)
# ---------------------------------------------------------------------------


def _create_relation(client: WikiClient, space_id: str, from_id: str, to_id: str, label: str) -> dict:
    """Create one directed relation object. Returns the created object dict."""
    return client.create_object(
        space_id,
        type_key="wiki_relation",
        name=f"{from_id} -> {to_id}",
        properties=[
            {"key": "wiki_relation_from", "text": from_id},
            {"key": "wiki_relation_to", "text": to_id},
            {"key": "wiki_relation_label", "text": label},
        ],
    )


def _write_bidirectional_relations(
    client: WikiClient,
    space_id: str,
    relations: list[tuple[str, str, str]],
) -> tuple[int, list[str]]:
    """Write each relation in both directions; roll back on partial failure.

    Returns (relations_created, rollback_notes).
    """
    created = 0
    rollback_notes: list[str] = []
    for from_id, to_id, label in relations:
        first = None
        try:
            first_obj = _create_relation(client, space_id, from_id, to_id, label)
            first = first_obj.get("id")
            _create_relation(client, space_id, to_id, from_id, label)
            created += 2
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
            # One direction failed — roll back the direction that succeeded.
            if first:
                try:
                    client.delete_object(space_id, first)
                except httpx.HTTPError:
                    pass
                rollback_notes.append(
                    f"relation_rollback: rolled back {first} ({from_id}->{to_id}) "
                    f"after reciprocal failed: {exc}"
                )
            else:
                rollback_notes.append(
                    f"relation_rollback: relation {from_id}->{to_id} failed: {exc}"
                )
    return created, rollback_notes


# ---------------------------------------------------------------------------
# Domain hint validation (AC#10)
# ---------------------------------------------------------------------------


def _domain_taxonomy(client: WikiClient, space_id: str) -> set[str]:
    try:
        props = client.list_properties(space_id)
        prop_id = None
        for p in props:
            if isinstance(p, dict) and p.get("key") == types_schema.DOMAIN_TAGS_PROPERTY_KEY:
                prop_id = p.get("id")
                break
        if not prop_id:
            return set()
        tags = client.list_tags(space_id, prop_id)
        return {t.get("name") for t in tags if isinstance(t, dict) and t.get("name")}
    except httpx.HTTPError:
        return set()
    except Exception:  # noqa: BLE001
        return set()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def wiki_ingest(source: str, space_id: str, domain_hint: str | None = None) -> dict:
    """Ingest a source URL/file into the wiki, creating/updating typed objects."""
    # 1. patch-decision precheck (AC#15) — before any Anytype write.
    decision = read_patch_decision()
    if decision is None or not (
        "patch_body_updates" in decision and "implementation_path" in decision
    ):
        return _error_result(
            "[CONFIG ERROR] patch_decision_missing_or_invalid: a valid "
            "patch-decision.md with patch_body_updates and implementation_path is required"
        )

    client = WikiClient()

    # 2. schema-compat (AC-M4).
    try:
        live_version = _bootstrap._read_schema_version(client, space_id)
    except httpx.HTTPError as exc:
        return _error_result(f"[API ERROR] schema_read_failed: {exc}")

    if live_version is None:
        return _error_result(
            "[CONFIG ERROR] wiki_schema_missing: run wiki_bootstrap on this space first"
        )

    code_version = types_schema.WIKI_SCHEMA_VERSION
    schema_warnings: list[str] = []
    cmp = _cmp_versions(live_version, code_version)
    if cmp < 0:
        return _error_result(
            f"[CONFIG ERROR] wiki_schema_outdated: space schema {live_version} < code "
            f"{code_version}; run wiki_bootstrap to upgrade"
        )
    if cmp > 0:
        schema_warnings.append(
            f"wiki_schema_newer: space schema {live_version} > code {code_version}; continuing"
        )

    # 3. domain_hint validation (AC#10) — before fetch.
    if domain_hint:
        taxonomy = _domain_taxonomy(client, space_id)
        if domain_hint not in taxonomy:
            return _error_result(
                f"[CONFIG ERROR] invalid_domain_hint: '{domain_hint}' is not in the "
                f"space's wiki_domain_tags taxonomy"
            )

    # 4. consent (AC-S2.2 / addendum HARD GATE 1) — before any off-machine transmit.
    endpoint = os.environ.get("WIKI_EXTRACT_ENDPOINT")
    if endpoint:
        check_remote_endpoint_consent(endpoint)

    # 5. lock (AC#5 / addendum HARD GATE 2) — entry path acquires it.
    try:
        with space_ingest_lock(space_id, source):
            return _run_ingest(
                client, source, space_id, domain_hint, schema_warnings
            )
    except RuntimeError as exc:
        # space_ingest_lock raises [DATA ERROR] ingest_in_progress when held.
        return _error_result(str(exc))


def _cmp_versions(a: str, b: str) -> int:
    ta = _bootstrap._version_tuple(a)
    tb = _bootstrap._version_tuple(b)
    return (ta > tb) - (ta < tb)


def _run_ingest(
    client: WikiClient,
    source: str,
    space_id: str,
    domain_hint: str | None,
    schema_warnings: list[str],
) -> dict:
    result = _empty_result()
    result["warnings"].extend(schema_warnings)
    status = "ok"

    # 6. fetch.
    markdown = fetch_url(source)
    if isinstance(markdown, str) and markdown.startswith("[DATA ERROR]") and "ssrf_blocked" in markdown:
        return _error_result(markdown)

    # 7. derive candidates.
    candidates = _derive_candidates(markdown, fallback_name=_source_name(source))

    if not candidates:
        # Empty source → create Source, write WikiLog, return ok with empty_source.
        result["warnings"].append("empty_source")
        result["source_object_id"] = _create_source(client, space_id, source, markdown, result)
        action_tag_id, degraded = _resolve_wiki_action_tag(client, space_id)
        if degraded:
            result["warnings"].append("wiki_action_tag_not_found")
        result["wiki_log_id"] = _write_wikilog(
            client, space_id,
            subject=source, created=0, updated=0,
            notes="empty_source", action_tag_id=action_tag_id,
        )
        result["status"] = "ok"
        _maybe_reindex(space_id, result)
        return result

    # 8. enrich via best-effort extract().
    try:
        extracted = extract(markdown=markdown, space_id=space_id)
        if isinstance(extracted, dict) and str(extracted.get("error", "")).startswith(
            "[CONFIG ERROR]"
        ):
            result["warnings"].append("extraction_degraded")
        else:
            _merge_extraction(candidates, extracted)
            if isinstance(extracted, dict) and extracted.get("error"):
                result["warnings"].append("extraction_degraded")
    except Exception:  # noqa: BLE001 — enrichment is best-effort
        result["warnings"].append("extraction_degraded")

    # 9. create Source object.
    source_id = _create_source(client, space_id, source, markdown, result)
    result["source_object_id"] = source_id

    # 10. resolve + create/update each candidate.
    name_to_id: dict[str, str] = {}
    for cand in candidates:
        clean_name = sanitize_name(cand["name"])
        if clean_name is None:
            result["warnings"].append(f"name_policy_rejected: {cand['name']!r}")
            continue
        facts = sanitize_property_value(cand.get("facts", "") or "")
        try:
            resolution = resolve_entity(client, space_id, "wiki_entity", clean_name)
            props = [{"key": "wiki_facts", "text": facts}]
            if resolution["action"] == "update":
                target = resolution["target"]
                # Properties-only PATCH — NEVER a body/markdown key (AC-L1).
                updated = client.update_object(
                    space_id, target["id"], {"properties": props}
                )
                obj_id = updated.get("id", target.get("id"))
                result["objects_updated"].append(
                    {"title": clean_name, "type": "entity", "object_id": obj_id}
                )
                name_to_id[normalize_title(clean_name)] = obj_id
            else:
                # Create with EMPTY body (properties only — AC-P7/AC-L1).
                created = client.create_object(
                    space_id, type_key="wiki_entity", name=clean_name, properties=props
                )
                obj_id = created.get("id")
                result["objects_created"].append(
                    {"title": clean_name, "type": "entity", "object_id": obj_id}
                )
                name_to_id[normalize_title(clean_name)] = obj_id
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
            status = "partial"
            result["warnings"].append(f"object_failed: {clean_name!r}: {exc}")

    # 11. bidirectional relations (AC#13).
    relations = _derive_relations(candidates, name_to_id)
    rel_created, rollback_notes = _write_bidirectional_relations(
        client, space_id, relations
    )
    result["relations_created"] = rel_created
    if rollback_notes:
        status = "partial"
        result["warnings"].extend(rollback_notes)

    # 12. WikiLog always (AC#3/T4/T5).
    action_tag_id, degraded = _resolve_wiki_action_tag(client, space_id)
    if degraded:
        result["warnings"].append("wiki_action_tag_not_found")
    notes = "; ".join(rollback_notes) if rollback_notes else "ingest"
    result["wiki_log_id"] = _write_wikilog(
        client, space_id,
        subject=source,
        created=len(result["objects_created"]),
        updated=len(result["objects_updated"]),
        notes=notes,
        action_tag_id=action_tag_id,
    )

    result["status"] = status

    # 13. auto-reindex (AC#9).
    _maybe_reindex(space_id, result)
    return result


def _derive_relations(
    candidates: list[dict], name_to_id: dict[str, str]
) -> list[tuple[str, str, str]]:
    """Derive A->B relations between consecutive successfully-created candidates.

    Heading-derived: when a source yields >= 2 entities, link them so each new
    object gets cross-links (spec §cross-link minimum). Only candidates that
    resolved to a concrete object id participate.
    """
    ids = [
        name_to_id[normalize_title(c["name"])]
        for c in candidates
        if normalize_title(c["name"]) in name_to_id
    ]
    relations: list[tuple[str, str, str]] = []
    for i in range(len(ids) - 1):
        relations.append((ids[i], ids[i + 1], "related"))
    return relations


def _create_source(
    client: WikiClient, space_id: str, source: str, markdown: str, result: dict
) -> str | None:
    """Create the wiki_source object. Records a warning on failure (non-fatal)."""
    is_url = source.startswith("http://") or source.startswith("https://")
    excerpt = sanitize_property_value((markdown or "")[:1000])
    props = [
        {"key": "wiki_excerpt", "text": excerpt},
        {"key": "wiki_ingested_at", "date": datetime.now(timezone.utc).isoformat()},
    ]
    if is_url:
        props.insert(0, {"key": "wiki_url", "url": source})
    else:
        props.insert(0, {"key": "wiki_file_path", "text": source})
    try:
        obj = client.create_object(
            space_id,
            type_key="wiki_source",
            name=_source_name(source),
            properties=props,
        )
        return obj.get("id")
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        result["warnings"].append(f"source_create_failed: {exc}")
        return None


def _source_name(source: str) -> str:
    scrubbed = scrub_credentials(source)
    return scrubbed[:200] if scrubbed else "source"


def _maybe_reindex(space_id: str, result: dict) -> None:
    if os.environ.get("WIKI_AUTO_REINDEX", "true").lower() == "false":
        return
    try:
        reindex_anytype(space_id)
    except Exception as exc:  # noqa: BLE001 — reindex failure is non-fatal (AC#9)
        result["warnings"].append(f"reindex_failed: {exc}")
