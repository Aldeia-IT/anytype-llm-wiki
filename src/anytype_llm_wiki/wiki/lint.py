"""wiki/lint.py — wiki_lint v0.5.0 structural health check.

A read-only, report-only diagnostic over a bootstrapped wiki space. It enumerates
the wiki ONCE, runs a battery of ten structural checks (asymmetric relations,
orphans, pipeline orphans, unresolved contradictions, staleness, oversized
descriptions, empty types, unreviewed/stale needs-review, and — opt-in — potential
duplicates), assembles a severity-ranked LintReport, and files a single ``wiki_log``
receipt. ``wiki_lint`` mutates nothing but its own WikiLog receipt.

Single-enumeration constraint (CTO-BLOCKING-1 / spec note G9): ``list_objects`` is
called EXACTLY ONCE; the same ``all_objects`` list feeds both the QA#25 schema gate
(``_schema_version_from_objects``, pure/no-I/O) and the check battery — the
``query.py:408`` pattern. Per-object ``get_object`` fetches (needed for the D1
``backlinks`` primary path) go through the shared per-run cache.

Performance: the advertised ≤60s / ≤500-object budget describes the DEFAULT
sweep-off path. The opt-in duplicate sweep (``include_duplicates=True``) embeds the
wiki and can exceed that budget; it is also hard-skipped above WIKI_LINT_MAX_OBJECTS.
"""

import logging
import time
from datetime import datetime, timedelta, timezone

import httpx

from . import config
from . import types_schema
from . import bootstrap as _bootstrap
from .. import indexer
from .ingest import _cmp_versions, _resolve_wiki_action_tag, _write_wikilog
from .query import _parse_relation_elements, _fetch_cached
from .remember import _resolve_select_tag
from .util import read_patch_decision, scrub_credentials, strip_control_chars
from ..anytype_client import AnytypeReadClient
from .wiki_client import WikiClient

logger = logging.getLogger(__name__)

_CONFIG_ERROR_PREFIX = "[CONFIG ERROR]"
_API_ERROR_PREFIX = "[API ERROR]"

# The four wiki CONTENT object types subject to the check battery.
_CONTENT_TYPES = ("wiki_entity", "wiki_concept", "wiki_comparison", "wiki_query")

# Severity total order (SF7). "all" includes informational (rank 0).
_SEV_ORDER = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
    "informational": 0,
}

# severity_threshold → minimum included rank. "low" EXCLUDES informational.
_THRESHOLD_MIN_RANK = {
    "all": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

# Duplicate band lower bound (fixed); upper bound is WIKI_LINT_DUPLICATE_MAX_SCORE.
_DUPLICATE_LO = 0.70

# WikiLog ingest-failure marker (mirrors ingest.py relation rollback note).
_FAILURE_MARKER = "relation_rollback"

_NEEDS_REVIEW = "needs-review"


# ---------------------------------------------------------------------------
# Shape helpers
# ---------------------------------------------------------------------------


def _type_of(obj: dict) -> str:
    t = obj.get("type")
    if isinstance(t, dict):
        return t.get("key", "")
    return t or ""


def _rel_key_for_type(type_key: str) -> str | None:
    """Relation property key carrying outbound 1-hop links for a content type."""
    if type_key == "wiki_entity":
        return "wiki_relations"
    if type_key == "wiki_concept":
        return "wiki_related"
    return None


def _prop(obj: dict, key: str) -> dict | None:
    """Return the first property dict on ``obj`` matching ``key`` (or None)."""
    for p in obj.get("properties", []) or []:
        if isinstance(p, dict) and p.get("key") == key:
            return p
    return None


def _outbound(obj: dict) -> list[str]:
    """Parse the type-appropriate outbound relation array → list of id strings."""
    rel_key = _rel_key_for_type(_type_of(obj))
    if rel_key is None:
        return []
    prop = _prop(obj, rel_key)
    if prop is None:
        return []
    return _parse_relation_elements(prop.get("objects"))


def _backlinks_inbound(obj: dict) -> tuple[bool, set[str]]:
    """D1 inbound resolution from the get_object ``backlinks`` field.

    Returns ``(primary_available, inbound_ids)``. A non-empty list backlinks is the
    PRIMARY path. Anything else (absent / empty / None / dict / scalar) → fallback
    needed (``(False, set())``); a malformed value must never raise (SF10).
    """
    bl = obj.get("backlinks")
    if isinstance(bl, list) and bl:
        return True, set(_parse_relation_elements(bl))
    return False, set()


def _parse_date(value) -> datetime | None:
    """Parse an ISO-8601 string to an aware UTC datetime; None on any failure."""
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _object_title(obj: dict) -> str:
    return strip_control_chars(str(obj.get("name", "")))[:200]


# ---------------------------------------------------------------------------
# LintReport scaffolding
# ---------------------------------------------------------------------------


def _empty_report() -> dict:
    return {
        "object_counts": {},
        "findings": [],
        "potential_duplicates": [],
        "summary": {},
        "elapsed_ms": 0,
        "wiki_log_id": None,
        "deeplink": None,
        "warnings": [],
        "notes": [],
        "status": "ok",
        "error": None,
        "error_category": None,
    }


def _finding(severity: str, check: str, obj: dict | None, space_id: str, detail: str) -> dict:
    oid = obj.get("id", "") if isinstance(obj, dict) else ""
    title = _object_title(obj) if isinstance(obj, dict) else ""
    return {
        "severity": severity,
        "check": check,
        "object_title": title,
        "object_id": oid or None,
        "deeplink": _bootstrap._object_deeplink(space_id, oid) if oid else None,
        "detail": detail,
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def wiki_lint(
    space_id: str,
    severity_threshold: str = "all",
    include_duplicates: bool = False,
) -> dict:
    """Run the structural health check over a bootstrapped wiki space.

    Sequential pipeline: QA#30 patch-decision pre-check (no network) → enumerate
    once → QA#25 schema gate (3 branches) → filter content objects + counts →
    resolve the needs-review tag → fetch each object (per-run cache, D1 backlinks)
    → run the ten-check battery → opt-in duplicate sweep → severity post-filter →
    summary → WikiLog receipt.

    The duplicate sweep is OPT-IN (``include_duplicates=True``) and can exceed the
    ≤60s budget the default path honors.
    """
    start = time.monotonic()
    report = _empty_report()

    def _finish(status: str) -> dict:
        report["status"] = status
        report["elapsed_ms"] = max(0, int((time.monotonic() - start) * 1000))
        return report

    # --- Step 0: QA#30 patch-decision pre-check (no network, before any client) ---
    decision = read_patch_decision()
    if decision is None or not (
        "patch_body_updates" in decision and "implementation_path" in decision
    ):
        report["error"] = (
            f"{_CONFIG_ERROR_PREFIX} patch_decision_missing_or_invalid: a valid "
            "patch-decision.md with patch_body_updates and implementation_path is required"
        )
        report["error_category"] = "config_error"
        return _finish("error")

    read_client = write_client = None
    try:
        read_client = AnytypeReadClient()
        write_client = WikiClient()
        # --- Step 1: enumerate ONCE (the only list_objects call) ---
        try:
            all_objects = write_client.list_objects(space_id)
        except (httpx.HTTPError, ConnectionError) as exc:
            report["error"] = scrub_credentials(
                f"{_API_ERROR_PREFIX} anytype_unavailable: object enumeration failed: {exc}"
            )
            report["error_category"] = "api_error"
            return _finish("error")

        # --- Step 2: QA#25 schema gate (mirror query.py) ---
        live = _bootstrap._schema_version_from_objects(all_objects)
        code = types_schema.WIKI_SCHEMA_VERSION
        if live is None:
            report["error"] = (
                f"{_CONFIG_ERROR_PREFIX} wiki_schema_missing: run wiki_bootstrap on "
                "this space first"
            )
            report["error_category"] = "config_error"
            return _finish("error")
        cmp = _cmp_versions(live, code)
        if cmp < 0:
            report["error"] = (
                f"{_CONFIG_ERROR_PREFIX} wiki_schema_outdated: space schema "
                f"{live} < code {code}; run wiki_bootstrap to upgrade"
            )
            report["error_category"] = "config_error"
            return _finish("error")
        if cmp > 0:
            report["warnings"].append(
                f"wiki_schema_newer: space schema {live} > code {code}; continuing"
            )

        # --- Step 3: filter content objects + counts + budget warning ---
        wiki_objects = [
            o for o in all_objects
            if isinstance(o, dict) and _type_of(o) in _CONTENT_TYPES
        ]
        # Budget warning counts the wiki CONTENT objects subject to the check
        # battery (the schema-marker collection is excluded — it is not linted).
        pre_filter_count = len(wiki_objects)
        counts: dict[str, int] = {}
        for o in all_objects:
            if not isinstance(o, dict):
                continue
            tk = _type_of(o)
            if tk.startswith("wiki_"):
                counts[tk] = counts.get(tk, 0) + 1
        report["object_counts"] = counts

        if pre_filter_count > 500:
            report["warnings"].append(
                f"lint_object_count_exceeded_budget: {pre_filter_count} objects found "
                "— lint may exceed 60s; consider archiving unused objects"
            )

        # --- Step 4: resolve the needs-review tag id ONCE (property-scoped two-step) ---
        needs_review_tag_id, _deg = _resolve_select_tag(
            write_client, space_id, "wiki_status", _NEEDS_REVIEW
        )

        # --- Step 5: fetch each wiki object (per-run cache, D1 backlinks) ---
        cache: dict[str, dict] = {}
        enum_map = {
            o["id"]: o for o in all_objects
            if isinstance(o, dict) and o.get("id")
        }
        fetched: list[dict] = []
        any_fetch_failure = False
        for o in wiki_objects:
            oid = o.get("id")
            full = _fetch_cached(read_client, space_id, oid, cache, enum_map)
            if full is None:
                report["warnings"].append(f"lint_object_fetch_failed: {oid}")
                any_fetch_failure = True
                continue
            fetched.append(full)
        by_id = {o["id"]: o for o in fetched if isinstance(o, dict) and o.get("id")}

        # --- Step 6: check battery ---
        findings: list[dict] = []
        now = datetime.now(timezone.utc)

        def _effective_source_ts(obj: dict) -> datetime | None:
            """Max wiki_ingested_at across the object's dereferenced wiki_sources."""
            prop = _prop(obj, "wiki_sources")
            if prop is None:
                return None
            best: datetime | None = None
            for sid in _parse_relation_elements(prop.get("objects")):
                src = _fetch_cached(read_client, space_id, sid, cache, enum_map)
                if not isinstance(src, dict):
                    continue
                ingested = _prop(src, "wiki_ingested_at")
                ts = _parse_date(ingested.get("date")) if ingested else None
                if ts is not None and (best is None or ts > best):
                    best = ts
            return best

        # Pre-fetch ingest-failure WikiLogs once for pipeline_orphan (D-cross-ref).
        failure_times: list[datetime] = []
        try:
            logs = write_client.search(space_id, "", filter={"type_key": "wiki_log"})
        except (httpx.HTTPError, ConnectionError, KeyError, ValueError, TypeError):
            logs = []
        for log in logs or []:
            if not isinstance(log, dict):
                continue
            action_prop = _prop(log, "wiki_action")
            action_name = ""
            if action_prop and isinstance(action_prop.get("select"), dict):
                action_name = action_prop["select"].get("name", "")
            notes_prop = _prop(log, "wiki_notes")
            notes = notes_prop.get("text", "") if notes_prop else ""
            if action_name == "ingest" and _FAILURE_MARKER in str(notes):
                ts_prop = _prop(log, "wiki_timestamp")
                ts = _parse_date(ts_prop.get("date")) if ts_prop else None
                if ts is not None:
                    failure_times.append(ts)

        for o in fetched:
            tk = _type_of(o)
            has_primary, inbound = _backlinks_inbound(o)

            # (a) asymmetric_relation (Critical)
            for target in _outbound(o):
                if has_primary:
                    reciprocal = target in inbound
                else:
                    t_obj = by_id.get(target) or _fetch_cached(
                        read_client, space_id, target, cache, enum_map
                    )
                    reciprocal = (
                        isinstance(t_obj, dict) and o["id"] in set(_outbound(t_obj))
                    )
                if not reciprocal:
                    findings.append(_finding(
                        "critical", "asymmetric_relation", o, space_id,
                        f"relation {o['id']} -> {target} is not reciprocated",
                    ))

            # inbound presence (for orphan / pipeline_orphan)
            if has_primary:
                has_inbound = bool(inbound)
            else:
                has_inbound = any(
                    o["id"] in set(_outbound(p))
                    for p in fetched if p is not o
                )

            # (b) orphan (High) — age-gated, entity/concept
            if tk in ("wiki_entity", "wiki_concept") and not has_inbound and not _outbound(o):
                ts = _effective_source_ts(o)
                if ts is not None and ts < now - timedelta(days=config.lint_orphan_grace_days()):
                    findings.append(_finding(
                        "high", "orphan", o, space_id,
                        "object has no inbound or outbound relations and its source "
                        f"is older than {config.lint_orphan_grace_days()}d",
                    ))

            # (c) pipeline_orphan (High) — timestamp heuristic; zero-relation AND
            # zero-backlink (parse-empty backlinks), near an ingest failure log.
            if not _outbound(o):
                bl = o.get("backlinks")
                backlinks_empty = not (isinstance(bl, list) and _parse_relation_elements(bl))
                if backlinks_empty:
                    ts = _effective_source_ts(o)
                    if ts is None:
                        ts = _parse_date(o.get("created_date"))
                    if ts is not None and failure_times:
                        window = config.lint_pipeline_window_seconds()
                        if any(abs((ts - f).total_seconds()) <= window for f in failure_times):
                            findings.append(_finding(
                                "high", "pipeline_orphan", o, space_id,
                                "zero-relation object created within "
                                f"{window}s of an ingest relation_rollback failure",
                            ))

            # (d) contradiction_unresolved (High) — active; wiki_entity only (SF9)
            if tk == "wiki_entity":
                contra_prop = _prop(o, "wiki_contradictions")
                contradictions = (
                    _parse_relation_elements(contra_prop.get("objects"))
                    if contra_prop else []
                )
                reviewed_prop = _prop(o, "wiki_last_reviewed")
                last_reviewed = reviewed_prop.get("date") if reviewed_prop else None
                if contradictions and not last_reviewed:
                    findings.append(_finding(
                        "high", "contradiction_unresolved", o, space_id,
                        f"{len(contradictions)} unresolved contradiction(s) — set "
                        "wiki_last_reviewed to resolve",
                    ))

            # (e) stale (Medium) — entity/concept
            if tk in ("wiki_entity", "wiki_concept"):
                ts = _effective_source_ts(o)
                lm = _parse_date(o.get("last_modified_date"))
                if ts is not None and lm is not None and lm < ts - timedelta(days=90):
                    findings.append(_finding(
                        "medium", "stale", o, space_id,
                        "last_modified predates the source ingest timestamp by > 90 days",
                    ))

            # (f)/(g) needs-review checks — entity/concept
            if tk in ("wiki_entity", "wiki_concept"):
                status_prop = _prop(o, "wiki_status")
                is_needs_review = False
                if status_prop and isinstance(status_prop.get("select"), dict):
                    sel = status_prop["select"]
                    sel_id = sel.get("id")
                    sel_name = sel.get("name")
                    if (needs_review_tag_id and sel_id == needs_review_tag_id) or (
                        sel_name == _NEEDS_REVIEW
                    ):
                        is_needs_review = True
                if is_needs_review:
                    findings.append(_finding(
                        "high", "unreviewed_needs_review", o, space_id,
                        f"object {o['id']} ({_object_title(o)}) is marked needs-review",
                    ))
                    ts = _effective_source_ts(o)
                    if ts is not None and ts < now - timedelta(
                        days=config.lint_stale_needs_review_days()
                    ):
                        findings.append(_finding(
                            "medium", "stale_needs_review", o, space_id,
                            f"object {o['id']} ({_object_title(o)}) has been "
                            f"needs-review for over {config.lint_stale_needs_review_days()}d",
                        ))

            # (h) oversized (Low)
            desc_prop = _prop(o, "wiki_description")
            desc = desc_prop.get("text", "") if desc_prop else ""
            if isinstance(desc, str) and len(desc) > config.lint_oversized_chars():
                findings.append(_finding(
                    "low", "oversized", o, space_id,
                    f"description is {len(desc)} chars (> {config.lint_oversized_chars()})",
                ))

        # (i) empty_type (Informational) — one per content type with zero objects
        present_types = {_type_of(o) for o in wiki_objects}
        for ct in _CONTENT_TYPES:
            if ct not in present_types:
                findings.append({
                    "severity": "informational",
                    "check": "empty_type",
                    "object_title": "",
                    "object_id": None,
                    "deeplink": None,
                    "detail": f"no objects of type {ct} found in this wiki",
                })

        # --- Step 7: opt-in duplicate sweep ---
        potential_duplicates: list[dict] = []
        if include_duplicates:
            if len(wiki_objects) > config.lint_max_objects():
                report["warnings"].append(
                    f"lint_sweep_skipped_object_cap: {len(wiki_objects)} objects exceed "
                    f"WIKI_LINT_MAX_OBJECTS={config.lint_max_objects()} — "
                    "potential_duplicates sweep skipped to stay within budget"
                )
            else:
                lo = _DUPLICATE_LO
                hi = config.lint_duplicate_max_score()
                seen_pairs: set[tuple[str, str]] = set()
                for o in fetched:
                    desc_prop = _prop(o, "wiki_description")
                    q = (desc_prop.get("text") if desc_prop else "") or o.get("name", "")
                    try:
                        cands = indexer.semantic_search_core(
                            q, space_id, list(_CONTENT_TYPES), 5
                        )
                    except Exception as exc:  # noqa: BLE001 — sweep is best-effort
                        report["warnings"].append(
                            scrub_credentials(f"lint_sweep_failed: {o.get('id')}: {exc}")
                        )
                        continue
                    for cand in cands or []:
                        cid = cand.get("object_id") if isinstance(cand, dict) else None
                        if not cid or cid == o["id"]:
                            continue
                        s = cand.get("score")
                        if not isinstance(s, (int, float)):
                            continue
                        if not (lo <= s < hi):
                            continue
                        pair = tuple(sorted((o["id"], cid)))
                        if pair in seen_pairs:
                            continue
                        seen_pairs.add(pair)
                        potential_duplicates.append({
                            "object_a": pair[0],
                            "object_b": pair[1],
                            "similarity_score": s,
                            "recommendation": "review for possible merge",
                        })
                        findings.append(_finding(
                            "informational", "potential_duplicate", o, space_id,
                            f"{o['id']} and {cid} are near-duplicates (score {s})",
                        ))
        report["potential_duplicates"] = potential_duplicates

        # --- Step 8: severity post-filter (findings[] only) ---
        min_rank = _THRESHOLD_MIN_RANK.get(severity_threshold, 0)
        filtered = [
            f for f in findings
            if _SEV_ORDER.get(f.get("severity"), 0) >= min_rank
        ]
        report["findings"] = filtered

        # --- Step 9: summary of FILTERED findings ---
        summary: dict[str, int] = {}
        for f in filtered:
            sev = f.get("severity")
            summary[sev] = summary.get(sev, 0) + 1
        report["summary"] = summary

        # --- Step 10: WikiLog receipt ---
        status = "partial" if any_fetch_failure else "ok"
        try:
            action_tag_id, _deg = _resolve_wiki_action_tag(write_client, space_id, "lint")
        except Exception:  # noqa: BLE001 — tag resolution must never abort the receipt
            action_tag_id = None
        wiki_log_id = _write_wikilog(
            write_client,
            space_id,
            subject=strip_control_chars("structural health check")[:50],
            created=0,
            updated=0,
            notes=scrub_credentials(
                f"lint: {len(filtered)} findings, status {status}"
            ),
            action_tag_id=action_tag_id,
            action_name="lint",
        )
        report["wiki_log_id"] = wiki_log_id
        report["deeplink"] = (
            _bootstrap._object_deeplink(space_id, wiki_log_id) if wiki_log_id else None
        )
        return _finish(status)
    finally:
        if read_client is not None:
            read_client.close()
        if write_client is not None:
            write_client.close()
