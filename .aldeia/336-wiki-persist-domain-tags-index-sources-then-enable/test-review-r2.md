# Test Review: #336 wiki_domain_tags persistence + source indexing — Round 2

**Verdict: APPROVED**

## Review Date
2026-06-13

## Test Run Summary
```
33 failed, 664 passed, 37 skipped, 3 xfailed, 50 warnings
```
737 tests total (736 from R1 + 1 new `test_payload_schema_version_is_3`). All 33 failing tests are #336 tests failing for the right reasons. No pre-existing test regressed. The 3 xfailed are unchanged from R1 (2 pre-existing bootstrap tests + `test_wiki_query_out_of_taxonomy_filter_warns`).

---

## R1 Finding Resolution

### B1 — `test_semantic_search_default_excludes_wiki_source` — RESOLVED

**What changed:** The test was completely rewritten (`tests/test_indexer.py:1110-1170`). The new version:

1. Imports `anytype_llm_wiki.server` as `_server_mod` and monkeypatches `_server_mod.semantic_search_core` with a `fake_core` that captures the `types` argument. This is the correct namespace — `server.py` imports `semantic_search_core` at module level via `from .indexer import reindex, semantic_search_core`, so patching the server module's binding intercepts the call made by `semantic_search`.

2. Assertion (a): calls `semantic_search(query="test")` with no `types=` and asserts `default_types is not None` AND `"wiki_source" not in default_types`. This is exactly the dual check required by R1 — not just "a filter exists" but "wiki_source is absent."

3. Assertion (b): calls `semantic_search(query="test", types=["wiki_source"])` and asserts `"wiki_source" in explicit_types` — the explicit caller intent overrides the default.

**Failure reason pre-impl (correct):** `default_types is None` (server.py currently passes `types=None` straight through to `semantic_search_core`). `AssertionError: assert None is not None`.

**Satisfiable by correct impl:** Yes. The spec-faithful impl adds a guard in `server.py:semantic_search` that, when `types=None`, builds a default list of non-`wiki_source` types and passes it to `semantic_search_core`. That makes `default_types` non-None and not containing `wiki_source`.

**`test_no_filter_regression` still passes:** Confirmed. That test calls `_indexer.semantic_search_core(query="test")` directly — the OD-B guard in `server.py` is never involved, so `query_filter` remains `None` as expected. The seam conflict identified in R1 is fully resolved.

### B2 — `test_payload_schema_version_is_3` — RESOLVED

**What was added:** `tests/test_indexer.py:1173-1192` (new standalone test):

```python
def test_payload_schema_version_is_3():
    from anytype_llm_wiki import config as _config
    assert _config.PAYLOAD_SCHEMA_VERSION == 3, (
        f"PAYLOAD_SCHEMA_VERSION must be 3 after #336 (was 2 pre-impl); "
        f"got {_config.PAYLOAD_SCHEMA_VERSION}"
    )
```

**Failure reason pre-impl (correct):** `AssertionError: PAYLOAD_SCHEMA_VERSION must be 3 after #336 (was 2 pre-impl); got 2` — `config.py` currently has `PAYLOAD_SCHEMA_VERSION = 2`. Direct assertion on the live constant, not monkeypatched. GREEN after `config.py` is updated to `PAYLOAD_SCHEMA_VERSION = 3`.

### SF1 — OD-C SET semantics discriminator in AC-P2 / AC-P5 — RESOLVED

**What changed in `tests/wiki/test_ingest.py` (AC-P2):** The `existing_entity` fixture now includes a pre-existing `wiki_domain_tags` property with `multi_select: [{"id": "old-tag-id", "name": "old-tag"}]`. After the primary assertion (`found_domain_tag` checks `["tag-id-ai"]` is present), a new OD-C SET check asserts `"old-tag-id" not in` the PATCH's `multi_select`. A MERGE implementation would produce `["old-tag-id", "tag-id-ai"]` and fail this check; a SET implementation produces only `["tag-id-ai"]` and passes.

**What changed in `tests/wiki/test_remember.py` (AC-P5):** The search mock now returns `entity_with_existing_tags` (an entity with `wiki_domain_tags: [{"id": "old-rem-id", "name": "old-rem-tag"}]`). The same pattern: primary assertion checks new tag present, secondary OD-C assertion checks `"old-rem-id"` absent. MERGE fails; SET passes.

**Discriminator correctness:** The implementation is expected to write `multi_select` as a list of string IDs (from `_resolve_multi_select_tags` return value `["tag-id-ai"]`), consistent with the primary AC-P2/P5 assertions that check `p.get("multi_select") == ["tag-id-ai"]`. A MERGE would produce `["old-tag-id", "tag-id-ai"]` in the same format, which `"old-tag-id" in (p.get("multi_select") or [])` correctly catches.

**Failure reason pre-impl (correct):** Both update tests fail at the primary `found_domain_tag` / `found` assertion — the domain tag is not written at all yet. The OD-C SET assertion is only reached post-impl, where it will correctly discriminate.

---

## No New Problems Introduced

All 33 failures are #336 tests failing for the right reason:
- 6 chunker tests: correct inversions of old behavior (allowlist count, exact-set, excerpt in allowlist, source chunks, chunk payload fields)
- 9 indexer tests: missing params/behavior in `semantic_search_core`, `_chunk_to_payload`, `_ensure_payload_indexes`, plus B2
- 8 ingest tests: `_resolve_multi_select_tags` not importable, entity/source write behavior absent
- 5 query tests: Tier-1 filter functions not importable, `wiki_query` missing params
- 4 remember tests: domain_tags not in meta, entity write behavior absent, agent source excerpt empty, plus AC-S-AGENT

The rewrite of the B1 test does not affect `test_no_filter_regression` (passes, confirmed). The new B2 test is a clean standalone assertion. The SF1 additions are appended after the primary assertions and do not alter the primary failure mode.

## Summary

All three R1 findings (B1, B2, SF1) are genuinely resolved. The fixes are minimal and correct — each addresses exactly the gap identified. No new blocking issues or regressions were introduced. The test suite is ready to gate the implementation phase.
