# R1 DRY / Code-Duplication Review — wiki_query (v0.4.0)

**Verdict: APPROVED WITH CONDITIONS**

Scope: `git diff 6975fff HEAD`. Primary file: `src/anytype_llm_wiki/wiki/query.py`.

## Counts

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| MAJOR    | 0 |
| MINOR    | 2 |

Reused-helpers table verified: `_cmp_versions` / `_resolve_wiki_action_tag` / `_write_wikilog` (ingest), `read_patch_decision` / `scrub_credentials` / `strip_control_chars` (util), `_DETERMINISTIC_OPTS` / `_is_model_not_pulled` / `sanitize_name` (extraction) are all imported and called rather than re-implemented. The `semantic_search` → `indexer.semantic_search_core` extraction (server.py / indexer.py) is exemplary consolidation: the old inline Qdrant logic in `semantic_search` is fully removed and both the v0.1 tool and Tier-2 retrieval now share one core. No duplication there.

---

## MINOR-1 (DRY): `_object_deeplink` re-implemented locally

- **File:** `src/anytype_llm_wiki/wiki/query.py:259-260`
- **Duplicate of:** `src/anytype_llm_wiki/wiki/bootstrap.py:83-84`
- **Issue:** Byte-identical one-line function `f"anytype://object/{space_id}/{object_id}"`. The spec brief offered a circular-import justification, but it does **not** hold: `query.py:34` already does `from . import bootstrap as _bootstrap` and actively uses `_bootstrap._ROOT_COLLECTION_NAME`, `_bootstrap._found_schema_version`, and `_bootstrap._max_version` (lines 294-302). `bootstrap.py` imports nothing from `query.py`, so there is no cycle. This is needless duplication, not justified divergence.
- **Fix:** Delete the local def and call `_bootstrap._object_deeplink(space_id, oid)` at the four call sites (lines 637, 665, 693), or promote the helper to `util.py` and import it in both modules. Severity MINOR only because the body is trivial and stable (a fixed URI scheme), so drift risk is low.

## MINOR-2 (DRY): `_schema_version_from_objects` loop body duplicates `bootstrap._read_schema_version`

- **File:** `src/anytype_llm_wiki/wiki/query.py:281-302`
- **Duplicate of:** `src/anytype_llm_wiki/wiki/bootstrap.py:486-509`
- **Issue:** The N+1-avoidance rationale is **legitimate** — `_read_schema_version` calls `client.list_objects` internally, and `query.py` has already enumerated (`all_objects`) for counting/tiering, so re-calling it would mean a second full enumeration. That part is correctly divergence-justified. However, the *marker-scanning loop body* (collection name+type-key guard → `_found_schema_version`; wiki_log → `_max_version`; final `_max_version(collection, wikilog)`) is a near-verbatim copy. The only logic difference is type-key extraction: bootstrap uses inline `obj.get("type", {}).get("key")` vs query's more-robust `_type_of(obj)`.
- **Fix:** Extract the loop into a pure helper in `bootstrap.py` that operates on an already-fetched list, e.g. `def _schema_version_from_objects(objects): ...`, then have `_read_schema_version` call `_schema_version_from_objects(client.list_objects(space_id))`. `query.py` calls the same pure helper with its `all_objects`. This eliminates the duplicated body while preserving the single-enumeration benefit. Severity MINOR: it is a real copy, but the two copies are short and the divergence (avoid 2nd enumeration) is real.

---

## Assessed and NOT flagged (intended divergence / suppressed)

- **`_call_ollama_synthesis` (query.py:107-173) vs `extraction._call_ollama_prompt` (extraction.py:99-152):** Structurally parallel (timeout construction, generate→chat fallback, model/think resolution, `_DETERMINISTIC_OPTS`, `_is_model_not_pulled`), but the spec **intends** a new transport: it omits `format: json`, reads raw `response` / `message.content` prose via `_extract_prose` instead of `_parse_json_response`, returns prose error sentinels instead of `(parsed, resp)` tuples, and adds slow-synthesis logging. This is the intended Decision-3 divergence, not needless copy — correctly suppressed per the brief and the "intended spec divergences" suppression.
- **`config._positive_int` (config.py:45-58):** New shared int-env resolver used by all six new tiered-retrieval knobs. Existing config funcs use bespoke inline parsing, but they have different semantics (float clamping in `extract_timeout`, list parsing in fetch-extra-ports). This is a new consolidation helper, not a re-implementation of an existing one. No finding.
- **`_type_of` (query.py:274-278):** Handles both `type` as dict (`{"key":...}`) and as bare string; this is intentionally more robust than the scattered inline `obj.get("type", {}).get("key")` in ingest/remember/chunker. Those call sites are out of scope and not a query.py duplication. No finding (consistency-only).
- **`_now_iso` / `datetime.now(timezone.utc).isoformat()`:** query uses `.isoformat()` directly (line 886), matching ingest/remember; bootstrap's `_now_iso` uses a different `...Z` strftime format. These are not interchangeable, so not duplication. No finding.

## Summary Table

| Category | Status | Findings |
|----------|--------|----------|
| Function/Utility Duplication | Issues | 2 MINOR (`_object_deeplink`, schema-version loop) |
| Transport / LLM-call Duplication | Pass (intended divergence) | 0 |
| Config Duplication | Pass | 0 |
| Type/relation parsing | Pass (reuses `_parse_relation_elements`) | 0 |
| Reused-helpers table compliance | Pass | 0 |
