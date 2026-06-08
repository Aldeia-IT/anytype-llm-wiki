"""wiki/remember.py — the wiki_remember agent-memory write pipeline (v0.3.1).

Mirrors ``ingest.py``'s orchestration but for narrated, conversational knowledge
rather than a fetched document. The pipeline is:

  entry validation (empty/oversize knowledge) → schema-compat →
  domain-tag validation → remote-endpoint consent → per-space lock → LLM extract →
  resolve subjects → per-subject create/consolidate (conflict-flag FIRST, then the
  D3 idempotency PATCH gate) → lazy Source creation + wiki_sources back-link →
  bidirectional relations → WikiLog (action_name="remember") → auto-reindex.

The genuinely new surface vs. ingest is the LLM-assisted consolidation step
(``extraction.consolidate``) that merges new facts into an existing object's
``wiki_facts``/``wiki_definition`` instead of overwriting it.

Module-level seam imports: the symbols below are imported at module scope and
called by their bare names so tests can monkeypatch
``anytype_llm_wiki.wiki.remember.<name>`` (extract, consolidate, space_ingest_lock,
check_remote_endpoint_consent, _write_bidirectional_relations, _maybe_reindex).
"""

import os
from datetime import datetime, timezone

import httpx

from . import types_schema
from . import bootstrap as _bootstrap
from .bootstrap import _object_deeplink
from .extraction import (
    check_remote_endpoint_consent,
    consolidate,
    extract,
    sanitize_name,
    sanitize_property_value,
)
from .ingest import (
    _cmp_versions,
    _domain_taxonomy,
    _resolve_wiki_action_tag,
    _write_bidirectional_relations,
    _write_wikilog,
    resolve_entity,
)
from .ingest import _maybe_reindex as _ingest_maybe_reindex
from .util import (
    _existing_text,
    normalize_title,
    scrub_credentials,
    space_ingest_lock,
)
from .wiki_client import WikiClient
from . import worklog

# Hard cap on the narrated knowledge processed by the local generation model
# (AC-L4 / B2). Measured in Python str length (characters).
_KNOWLEDGE_MAX_CHARS = 32_000


# Module-level reindex seam so tests can patch remember._maybe_reindex without
# touching ingest's. Delegates to ingest's implementation by default. Tests may
# replace this with a raising stub; ``_reindex_guarded`` ensures any raise is
# caught and recorded as a non-fatal warning (AC-R16).
def _maybe_reindex(space_id: str, result: dict) -> None:
    _ingest_maybe_reindex(space_id, result)


def _reindex_guarded(space_id: str, result: dict) -> None:
    """Call the (patchable) ``_maybe_reindex`` seam; reindex failure is non-fatal."""
    try:
        _maybe_reindex(space_id, result)
    except Exception as exc:  # noqa: BLE001 — reindex failure is non-fatal (AC-R16)
        result["warnings"].append(f"reindex_failed: {exc}")


# ---------------------------------------------------------------------------
# Result helpers (SF2)
# ---------------------------------------------------------------------------


def _empty_remember_result() -> dict:
    return {
        "source_object_id": None,
        "objects": [],
        "relations_created": 0,
        "conflicts_flagged": 0,
        "wiki_log_id": None,
        "warnings": [],
        "status": "ok",
    }


def _error_remember_result(message: str) -> dict:
    result = _empty_remember_result()
    result["status"] = "error"
    result["error"] = message
    result["warnings"].append(message)
    return result


def _normalize_for_compare(text) -> str:
    import re

    if not isinstance(text, str):
        return ""
    return re.sub(r"\s+", " ", text).strip().lower()


# ---------------------------------------------------------------------------
# Runtime select tag resolution (D6/SF12)
#
# Tags are keyed by PROPERTY id in the real Anytype API
# (``/v1/spaces/{id}/properties/{property_id}/tags``), so these resolvers do the
# spec-mandated D6 two-step — list_properties → match the target property key →
# list_tags — mirroring ingest's ``_resolve_wiki_action_tag`` exactly, including
# the SF12 symmetry of reading tags even when the property id is unresolved (so a
# raising tags-mock still exercises the degraded branch). A read failure or a
# missing tag returns ``(None, degraded)`` and the caller skips the select write.
# ---------------------------------------------------------------------------


def _resolve_select_tag(
    client: WikiClient, space_id: str, property_key: str, tag_name: str
) -> tuple[str | None, bool]:
    """Resolve a select tag id by name under ``property_key``. Returns (id, degraded)."""
    try:
        props = client.list_properties(space_id)
        prop_id = None
        for p in props:
            if isinstance(p, dict) and p.get("key") == property_key:
                prop_id = p.get("id")
                break
        # Even if the property id is not found, attempt a tags read so the test's
        # tags-path mock (which may raise) exercises the degraded branch (SF12).
        tags = client.list_tags(space_id, prop_id or property_key)
        for t in tags:
            if isinstance(t, dict) and t.get("name") == tag_name:
                return t.get("id"), False
        return None, False
    except httpx.HTTPError:
        return None, True
    except Exception:  # noqa: BLE001 — any tag-resolution failure degrades, never aborts
        return None, True


def _resolve_wiki_status_tag(
    client: WikiClient, space_id: str, tag_name: str
) -> tuple[str | None, bool]:
    return _resolve_select_tag(client, space_id, "wiki_status", tag_name)


def _resolve_wiki_source_type_tag(
    client: WikiClient, space_id: str, tag_name: str
) -> tuple[str | None, bool]:
    return _resolve_select_tag(client, space_id, "wiki_source_type", tag_name)


# ---------------------------------------------------------------------------
# Provenance Source (D7/SF4/SF10)
# ---------------------------------------------------------------------------


def _create_remember_source(
    client: WikiClient,
    space_id: str,
    source_note: str | None,
    result: dict,
    source_type_tag_id: str | None,
) -> str | None:
    """Create a wiki_source object for narrated knowledge (lazy, no dedup).

    The note is scrubbed (URL credentials), sanitized, then truncated to 500
    chars before being written to wiki_excerpt. ``wiki_source_type`` is written
    only when ``source_type_tag_id`` is resolvable.
    """
    if source_note:
        excerpt = sanitize_property_value(scrub_credentials(source_note))[:500]
    else:
        excerpt = ""
    name = (
        scrub_credentials(source_note)[:200]
        if source_note
        else f"agent {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    )
    props = [
        {"key": "wiki_excerpt", "text": excerpt},
        {"key": "wiki_ingested_at", "date": datetime.now(timezone.utc).isoformat()},
    ]
    if source_type_tag_id:
        props.append({"key": "wiki_source_type", "select": source_type_tag_id})
    try:
        obj = client.create_object(
            space_id, type_key="wiki_source", name=name, properties=props
        )
        return obj.get("id")
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        result["warnings"].append(f"source_create_failed: {exc}")
        return None


# ---------------------------------------------------------------------------
# Subject assembly
# ---------------------------------------------------------------------------

_VALID_FACT_ACTIONS = {"merge", "add", "supersede", "keep", "conflict"}


def _subject_facts(item: dict) -> str:
    """Pull candidate fact text from an extracted entity/concept dict."""
    for key in ("facts", "wiki_facts", "wiki_definition", "definition", "description"):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return ""


def _build_subjects(extracted: dict) -> list[dict]:
    """Merge extracted entities + concepts into a flat subject list.

    Each subject: {"name", "kind" ("entity"|"concept"), "facts"}.
    """
    subjects: list[dict] = []
    if not isinstance(extracted, dict):
        return subjects
    for key, kind in (("entities", "entity"), ("concepts", "concept")):
        for item in extracted.get(key) or []:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not name:
                continue
            subjects.append(
                {"name": name, "kind": kind, "facts": _subject_facts(item)}
            )
    return subjects


def _type_for_kind(kind: str) -> tuple[str, str, str]:
    """Return (type_key, type_label, property_key) for a subject kind."""
    if kind == "concept":
        return "wiki_concept", "concept", "wiki_definition"
    return "wiki_entity", "entity", "wiki_facts"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def wiki_remember(
    space_id: str,
    knowledge: str,
    subject_hint: str | None = None,
    kind: str | None = None,
    relations: list[dict] | None = None,
    domain_tags: list[str] | None = None,
    source: str | None = None,
) -> dict:
    """Consolidate narrated knowledge into typed wiki objects (v0.3.1)."""
    # a. Entry validation BEFORE any HTTP / lock / extract (AC-L4 / B2 / B8).
    if not isinstance(knowledge, str) or not knowledge.strip():
        return _error_remember_result("[CONFIG ERROR] empty_knowledge")
    if len(knowledge) > _KNOWLEDGE_MAX_CHARS:
        return _error_remember_result("[DATA ERROR] knowledge_too_large")


    client = WikiClient()
    try:
        # c. schema-compat.
        try:
            live_version = _bootstrap._read_schema_version(client, space_id)
        except httpx.HTTPError as exc:
            return _error_remember_result(f"[API ERROR] schema_read_failed: {exc}")

        if live_version is None:
            return _error_remember_result(
                "[CONFIG ERROR] wiki_schema_missing: run wiki_bootstrap on this space first"
            )
        code_version = types_schema.WIKI_SCHEMA_VERSION
        schema_warnings: list[str] = []
        cmp = _cmp_versions(live_version, code_version)
        if cmp < 0:
            return _error_remember_result(
                f"[CONFIG ERROR] wiki_schema_outdated: space schema {live_version} < "
                f"code {code_version}; run wiki_bootstrap to upgrade"
            )
        if cmp > 0:
            schema_warnings.append(
                f"wiki_schema_newer: space schema {live_version} > code {code_version}; "
                "continuing"
            )

        # d. domain-tag validation — before any write.
        if domain_tags:
            taxonomy = _domain_taxonomy(client, space_id)
            for tag in domain_tags:
                if tag not in taxonomy:
                    return _error_remember_result(
                        f"[CONFIG ERROR] invalid_domain_hint: '{tag}' is not in the "
                        f"space's wiki_domain_tags taxonomy"
                    )

        # e. consent — MUST fire before extract.
        endpoint = os.environ.get("WIKI_EXTRACT_ENDPOINT")
        if endpoint:
            check_remote_endpoint_consent(endpoint)

        # f. per-space lock (HARD GATE AC-R-S2). Extraction runs INSIDE the lock
        #    (in _run_remember) on purpose: a contender on a held lock then fails
        #    fast WITHOUT first paying for a multi-minute extraction. See
        #    docs/architecture.md "Concurrency model" for the lock-hold trade-off
        #    and the (deferred) chunked-release design.
        try:
            with space_ingest_lock(space_id, knowledge[:50]):
                return _run_remember(
                    client, space_id, knowledge, subject_hint, kind,
                    relations, source, schema_warnings,
                )
        except RuntimeError as exc:
            return _error_remember_result(str(exc))
    finally:
        client.close()


def _run_remember(
    client: WikiClient,
    space_id: str,
    knowledge: str,
    subject_hint: str | None,
    kind: str | None,
    relations: list[dict] | None,
    source: str | None,
    schema_warnings: list[str],
) -> dict:
    result = _empty_remember_result()
    result["warnings"].extend(schema_warnings)
    status = "ok"

    # g. extract (inside lock). model-not-pulled aborts before any write. Kept
    #    under the lock so a contender fails fast without paying for extraction
    #    first (see docs/architecture.md "Concurrency model").
    extracted = extract(markdown=knowledge, space_id=space_id)
    if isinstance(extracted, str):
        if "ollama_model_not_pulled" in extracted:
            return _error_remember_result(extracted)
        extracted = {"entities": [], "concepts": []}
    if isinstance(extracted, dict) and "ollama_model_not_pulled" in str(
        extracted.get("error", "")
    ):
        return _error_remember_result(str(extracted["error"]))

    # h. build subjects.
    new_subjects = _build_subjects(extracted)
    if not new_subjects and subject_hint:
        hint_kind = "concept" if kind == "concept" else "entity"
        new_subjects = [
            {"name": subject_hint, "kind": hint_kind, "facts": knowledge}
        ]

    # i. Durability — the no-drop guarantee (replaces the old fixed subject cap).
    #    The previous design truncated the subject list to a hard limit and
    #    SILENTLY DROPPED the remainder (unbounded data loss, no record of what
    #    was lost). Instead: record every extracted subject in a durable per-space
    #    work-log BEFORE draining, fold back any subjects left pending by an
    #    interrupted prior run, and finish them here. Consolidation is idempotent,
    #    so re-processing a partially-applied subject converges to a no-op. Nothing
    #    is dropped; an interrupted drain resumes on the next run. See worklog.py.
    pending = _safe_load_pending(space_id, result)
    if pending:
        result["warnings"].append(f"resumed_pending_subjects: {len(pending)}")

    if not new_subjects and not pending:
        result["warnings"].append("no_subjects: extraction empty and no subject_hint")
        result["status"] = "partial"
        _reindex_guarded(space_id, result)
        return result

    # Record THIS batch durably (fsync) before draining. On a work-log failure we
    # still process everything in-process — we only warn that crash-resume isn't
    # guaranteed for this run. We never drop a subject.
    new_work_id = None
    enriched_new = new_subjects
    if new_subjects:
        new_work_id, enriched_new = _safe_begin(
            space_id, new_subjects,
            meta={"relations": relations or [], "source": source},
            result=result,
        )

    # Unified work list: pending (prior interrupted runs) first, then this batch.
    # De-duplicate by (normalized name, kind) to avoid redundant consolidations;
    # each item carries _id/_work_id so completion is recorded per subject.
    subjects: list[dict] = []
    relations = list(relations or [])
    seen: set[tuple[str, str]] = set()
    seen_meta_work: set[str] = set()
    for p in pending:
        wid = p.get("_work_id")
        if wid and wid not in seen_meta_work:
            seen_meta_work.add(wid)
            relations.extend((p.get("_meta") or {}).get("relations") or [])
        key = (normalize_title(p.get("name", "")), p.get("kind", "entity"))
        if key in seen:
            _safe_mark_done(space_id, p.get("_work_id"), p.get("id"), result)
            continue
        seen.add(key)
        subjects.append({
            "name": p.get("name", ""), "kind": p.get("kind", "entity"),
            "facts": p.get("facts", ""),
            "_id": p.get("id"), "_work_id": p.get("_work_id"),
        })
    for s in enriched_new:
        key = (normalize_title(s.get("name", "")), s.get("kind", "entity"))
        if key in seen:
            _safe_mark_done(space_id, new_work_id, s.get("id"), result)
            continue
        seen.add(key)
        subjects.append({
            "name": s.get("name", ""), "kind": s.get("kind", "entity"),
            "facts": s.get("facts", ""),
            "_id": s.get("id"), "_work_id": new_work_id,
        })

    # j. per-subject create/consolidate.
    name_to_id: dict[str, str] = {}
    kind_by_id: dict[str, str] = {}
    wikilog_notes: list[str] = []
    objects_written = 0  # created or updated (real writes — drives lazy Source)

    # Lazy Source (SF10): created on the FIRST real write so its id can be folded
    # into that same create/PATCH (one PATCH per object — no separate back-link
    # write). Returns the source id (or None on degrade).
    source_state: dict = {"id": None, "created": False}

    def _ensure_source() -> str | None:
        if source_state["created"]:
            return source_state["id"]
        source_state["created"] = True
        source_type_name = (
            "conversation"
            if source and "conversation" in source.lower()
            else "agent"
        )
        st_tag_id, st_degraded = _resolve_wiki_source_type_tag(
            client, space_id, source_type_name
        )
        if st_degraded or st_tag_id is None:
            result["warnings"].append("wiki_source_type_tag_not_found")
            st_tag_id = None
        sid = _create_remember_source(client, space_id, source, result, st_tag_id)
        source_state["id"] = sid
        result["source_object_id"] = sid
        return sid

    for subj in subjects:
        clean_name = sanitize_name(subj["name"])
        if clean_name is None:
            result["warnings"].append(f"name_policy_rejected: {subj['name']!r}")
            continue
        subj_kind = subj.get("kind", "entity")
        type_key, type_label, prop_key = _type_for_kind(subj_kind)
        subj_facts = sanitize_property_value(subj.get("facts", "") or "")

        obj_entry: dict = {
            "object_id": None,
            "title": clean_name,
            "kind": type_label,
            "action": None,
            "deeplink": "",
            "conflicts_flagged": 0,
            "relations_created": 0,
        }

        try:
            resolution = resolve_entity(client, space_id, type_key, clean_name)

            if resolution.get("action") == "update":
                # D9b/B9 — ambiguity check on the same-type, same-normalized-name set.
                normalized = normalize_title(clean_name)
                same_type = _same_type_candidates(client, space_id, clean_name, type_key)
                exact = [
                    o for o in same_type
                    if normalize_title(o.get("name", "")) == normalized
                ]
                if len(exact) > 1:
                    result["warnings"].append(
                        f"ambiguous_subject: {clean_name} ({len(exact)} candidates)"
                    )
                    obj_entry["action"] = "error"
                    obj_entry["error"] = "ambiguous_subject"
                    status = "partial"
                    result["objects"].append(obj_entry)
                    continue

                target = resolution["target"]
                target_id = target.get("id")
                obj_entry["object_id"] = target_id
                existing_text = _existing_text(target, prop_key)

                cons = consolidate(
                    existing_text=existing_text,
                    new_facts=subj_facts,
                    kind=subj_kind,
                    space_id=space_id,
                )

                if "consolidation_degraded" in str(cons.get("error", "")):
                    obj_entry["action"] = "consolidation_degraded"
                    result["warnings"].append(str(cons.get("error")))
                    status = "partial"
                    result["objects"].append(obj_entry)
                    continue

                consolidated_text = cons.get("consolidated_text", existing_text)
                changed = bool(cons.get("changed"))
                conflicts = cons.get("conflicts") or []
                fact_actions = [
                    fa for fa in (cons.get("fact_actions") or [])
                    if isinstance(fa, dict) and fa.get("action") in _VALID_FACT_ACTIONS
                ]

                # Conflict-flag FIRST (SF1), independent of the D3 PATCH gate.
                n_conflicts = len(conflicts)
                obj_entry["conflicts_flagged"] = n_conflicts
                if n_conflicts:
                    result["conflicts_flagged"] += n_conflicts
                    _flag_conflict_status(client, space_id, target_id, result)
                    result["warnings"].append("sources_overwrite_on_conflict")
                    pair_detail = "; ".join(
                        f"{c.get('existing_fact', '')} vs {c.get('new_fact', '')}: "
                        f"{c.get('reason', '')}"
                        for c in conflicts
                        if isinstance(c, dict)
                    )
                    wikilog_notes.append(
                        f"conflicts_flagged: {n_conflicts}; {pair_detail}"
                    )

                # Supersede audit (addendum item 1).
                for fa in fact_actions:
                    if fa.get("action") == "supersede" and fa.get("supersedes"):
                        wikilog_notes.append(
                            f"supersede: {fa.get('supersedes')}"
                        )

                # D3 text-PATCH gate.
                norm_equal = (
                    _normalize_for_compare(consolidated_text)
                    == _normalize_for_compare(existing_text)
                )
                if not changed or norm_equal:
                    obj_entry["action"] = "consolidated"
                    if changed and norm_equal:
                        result["warnings"].append("consolidated_despite_changed_flag")
                else:
                    # Real change → PATCH the consolidated text (B1 sanitize-on-write).
                    # The Source is created lazily HERE (first real write) so its id
                    # rides in the same PATCH (one PATCH per object — SF10/D2).
                    src_id = _ensure_source()
                    patch_props = [
                        {"key": prop_key, "text": sanitize_property_value(consolidated_text)},
                    ]
                    if not n_conflicts:
                        patch_props.append(
                            {"key": "wiki_last_reviewed",
                             "date": datetime.now(timezone.utc).isoformat()}
                        )
                    if src_id:
                        patch_props.append(
                            {"key": "wiki_sources", "objects": [src_id]}
                        )
                    client.update_object(space_id, target_id, {"properties": patch_props})
                    obj_entry["action"] = "updated"
                    objects_written += 1

                obj_entry["deeplink"] = _object_deeplink(space_id, target_id)
                name_to_id[normalize_title(clean_name)] = target_id
                kind_by_id[target_id] = subj_kind

            else:
                # Create with EMPTY body (properties only — AC-L1). The Source is
                # created lazily HERE and linked in the create payload.
                src_id = _ensure_source()
                create_props = [{"key": prop_key, "text": subj_facts}]
                if src_id:
                    create_props.append(
                        {"key": "wiki_sources", "objects": [src_id]}
                    )
                created = client.create_object(
                    space_id,
                    type_key=type_key,
                    name=clean_name,
                    properties=create_props,
                )
                obj_id = created.get("id")
                obj_entry["object_id"] = obj_id
                obj_entry["action"] = "created"
                obj_entry["deeplink"] = _object_deeplink(space_id, obj_id)
                objects_written += 1
                name_to_id[normalize_title(clean_name)] = obj_id
                kind_by_id[obj_id] = subj_kind

        except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
            obj_entry["action"] = "error"
            obj_entry["error"] = str(exc)
            status = "partial"

        result["objects"].append(obj_entry)

    # l. relations (SF5 type-safe; G1 per-object counts).
    rel_total = 0
    if relations:
        rel_tuples: list[tuple[str, str, str]] = []
        endpoint_objs: list[str] = []
        for rel in relations:
            if not isinstance(rel, dict):
                continue
            from_name = rel.get("from", "")
            to_name = rel.get("to", "")
            label = rel.get("label", "related")
            from_id = name_to_id.get(normalize_title(from_name))
            to_id = name_to_id.get(normalize_title(to_name))
            # Cross-batch / resume: an endpoint may name a subject that was
            # written by a PRIOR (interrupted) run, so it isn't in this run's
            # name_to_id. Resolve it against existing objects before giving up,
            # otherwise a relation spanning a crash boundary would be lost.
            if from_id is None:
                from_id = _resolve_existing_endpoint(
                    client, space_id, from_name, name_to_id, kind_by_id
                )
            if to_id is None:
                to_id = _resolve_existing_endpoint(
                    client, space_id, to_name, name_to_id, kind_by_id
                )
            if from_id and to_id:
                rel_tuples.append((from_id, to_id, label))
                endpoint_objs.extend([from_id, to_id])
            else:
                for endpoint_name in (to_name, from_name):
                    if endpoint_name and normalize_title(endpoint_name) not in name_to_id:
                        result["warnings"].append(
                            f"relation_endpoint_unresolved: {endpoint_name}"
                        )
        rel_total, rollback_notes = _write_bidirectional_relations(
            client, space_id, rel_tuples, kind_by_id
        )
        if rollback_notes:
            result["warnings"].extend(rollback_notes)
            status = "partial"
        # Per-object relations_created: count endpoint appearances.
        for obj in result["objects"]:
            oid = obj.get("object_id")
            if oid:
                obj["relations_created"] = endpoint_objs.count(oid)
    result["relations_created"] = rel_total

    # m. WikiLog always (action_name="remember").
    action_tag_id, degraded = _resolve_wiki_action_tag(
        client, space_id, action_name="remember"
    )
    if degraded or action_tag_id is None:
        result["warnings"].append("wiki_action_tag_not_found")
        action_tag_id = None
    created_count = sum(1 for o in result["objects"] if o.get("action") == "created")
    updated_count = sum(
        1 for o in result["objects"] if o.get("action") in ("updated", "consolidated")
    )
    notes = "; ".join(["remember", *wikilog_notes]) if wikilog_notes else "remember"
    result["wiki_log_id"] = _write_wikilog(
        client, space_id,
        subject=knowledge[:50],
        created=created_count,
        updated=updated_count,
        notes=notes,
        action_tag_id=action_tag_id,
        action_name="remember",
    )

    # Every subject in this run's work list was attempted exactly once above, so
    # mark them all done and compact the durable work-log. If the drain had been
    # interrupted (crash/kill/timeout) before reaching here, the log persists and
    # the next run resumes the outstanding subjects — that is the no-drop scope.
    # NOTE: a subject whose write hit a per-subject API error above (action=
    # "error", status=partial) is ALSO marked done here, on purpose: the error is
    # reported (not silently dropped), and leaving it pending would re-run a
    # deterministically-failing subject forever. Crash-resume covers process
    # death; per-subject API errors are surfaced, not retried.
    for subj in subjects:
        _safe_mark_done(space_id, subj.get("_work_id"), subj.get("_id"), result)
    _safe_compact(space_id, result)

    result["status"] = status

    # n. auto-reindex (non-fatal).
    _reindex_guarded(space_id, result)
    return result


def _resolve_existing_endpoint(
    client: WikiClient,
    space_id: str,
    name: str,
    name_to_id: dict[str, str],
    kind_by_id: dict[str, str],
) -> str | None:
    """Resolve a relation-endpoint name to an EXISTING object id (entity or
    concept) for cross-batch / resume relations whose endpoint was written by a
    prior run. Returns the id or None; caches a hit into name_to_id/kind_by_id so
    the unresolved-warning check and _write_bidirectional_relations see it.
    """
    if not name:
        return None
    key = normalize_title(name)
    if key in name_to_id:
        return name_to_id[key]
    for type_key, subj_kind in (("wiki_entity", "entity"), ("wiki_concept", "concept")):
        try:
            res = resolve_entity(client, space_id, type_key, name)
        except (httpx.HTTPError, KeyError, ValueError, TypeError):
            continue
        if res.get("action") == "update":
            tid = (res.get("target") or {}).get("id")
            if tid:
                name_to_id[key] = tid
                kind_by_id[tid] = subj_kind
                return tid
    return None


def _safe_load_pending(space_id: str, result: dict) -> list[dict]:
    """worklog.load_pending guarded — a work-log read failure never breaks a run."""
    try:
        return worklog.load_pending(space_id)
    except OSError as exc:
        result["warnings"].append(
            f"worklog_load_failed: {scrub_credentials(str(exc))}"
        )
        return []


def _safe_begin(space_id: str, subjects: list[dict], meta: dict, result: dict):
    """worklog.begin guarded. On failure, process all subjects in-process anyway
    (no drop) — only crash-resume is forfeited for this run."""
    try:
        return worklog.begin(space_id, subjects, meta=meta)
    except OSError as exc:
        result["warnings"].append(
            "worklog_begin_failed (crash-resume not guaranteed this run): "
            f"{scrub_credentials(str(exc))}"
        )
        return None, subjects


def _safe_mark_done(space_id: str, work_id, subject_id, result: dict) -> None:
    """worklog.mark_done guarded; no-op when ids are absent (durability disabled)."""
    if not work_id or not subject_id:
        return
    try:
        worklog.mark_done(space_id, work_id, subject_id)
    except OSError as exc:
        result["warnings"].append(
            f"worklog_mark_done_failed: {scrub_credentials(str(exc))}"
        )


def _safe_compact(space_id: str, result: dict) -> None:
    """worklog.compact guarded — a compaction failure never breaks a run."""
    try:
        worklog.compact(space_id)
    except OSError as exc:
        result["warnings"].append(
            f"worklog_compact_failed: {scrub_credentials(str(exc))}"
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _same_type_candidates(
    client: WikiClient, space_id: str, title: str, type_key: str
) -> list[dict]:
    """Re-fetch the same-type candidate set for an ambiguity re-check (AC-L2)."""
    try:
        results = client.search(space_id, query=title)
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        return []
    return [
        o for o in results
        if isinstance(o, dict) and o.get("type", {}).get("key") == type_key
    ]


def _flag_conflict_status(
    client: WikiClient, space_id: str, object_id: str, result: dict
) -> None:
    """Set wiki_status=needs-review (degrade+warn if the tag is absent)."""
    tag_id, degraded = _resolve_wiki_status_tag(client, space_id, "needs-review")
    if degraded or tag_id is None:
        result["warnings"].append("wiki_status_tag_not_found")
        return
    try:
        client.update_object(
            space_id, object_id,
            {"properties": [{"key": "wiki_status", "select": tag_id}]},
        )
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        result["warnings"].append("wiki_status_tag_not_found")
