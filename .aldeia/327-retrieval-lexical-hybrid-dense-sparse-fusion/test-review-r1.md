# Test Review: retrieval-lexical-hybrid-dense-sparse-fusion Round 1

**Verdict: NEEDS CHANGES**

## Review Date
2026-06-26

## 1. Spec Coverage

Overall coverage is thorough. All 18 checklist items from §12 (AC-H1 through AC-H-REG1, AC-EVAL) and the three addendum-mandated tests (QA-3, QA-4, CSO-1) have corresponding tests in the traceability matrix.

Every mapped test was verified against the spec's inline code (§11) and the actual implementation in the diff. The mappings are accurate. AC-H-REG1 (`test_no_filter_regression_unchanged`) correctly PASSES pre-implementation (it is a regression guard against `semantic_search_core` being modified, not a new-behavior gate); this is expected and documented in the debrief.

One finding on AC-EVAL coverage (see Section 3 below).

**PASSED** (coverage present for all ACs).

## 2. Edge Case Coverage

**Boundary conditions tested:**
- `limit=0` → `[]` (AC-H5, `test_hybrid_limit_zero`): PASSED
- Both-empty / one-empty RRF inputs (AC-H2, `test_rrf_fuse_both_empty`, `test_rrf_fuse_one_empty`): PASSED
- Empty scroll cold-start stays `None` (AC-H8): PASSED
- Empty scroll keeps prior index (AC-H8): PASSED
- BM25 raises → dense-only fallback (AC-H3): PASSED
- Qdrant outage on dense path propagates (AC-H13): PASSED

**Filter precedence conflicts tested:**
- BM25-only wrong-type chunk dropped (AC-H6): PASSED
- BM25-only matching `domain_tags` survives, non-matching dropped (AC-H6b): PASSED
- Date filter drops BM25-only, keeps dense (AC-H14): PASSED
- Cross-space BM25-only chunk excluded (CSO-1): PASSED

**Finding — SHOULD-FIX:** `test_hybrid_bm25_domain_tags_gate_real_build` (QA-4, `tests/test_indexer.py`): The "drop" assertion `assert "obj_fin" not in result_ids` is trivially true. The query is `"machine learning"` and the corpus entry for `obj_fin` is `"financial analysis report"` — none of the query tokens appear in that text, so BM25 scores `obj_fin` exactly 0 and `_bm25_search`'s `if score <= 0: break` clause drops it before it ever reaches the filter gate. The assertion would pass even if `_passes_inline_filters` were deleted entirely. The SURVIVAL assertion (`assert "obj_ml" in result_ids`) is genuine and tests the real path. But the gate-DROP half is not exercised through the real build path. The hand-fed version (`test_hybrid_bm25_only_domain_tags_gate`) does test drop behavior, but the point of QA-4 was to do so through real keying. The fix is to pick a query that scores `obj_fin` above 0 in BM25 (e.g., use a word that appears in both corpus entries, or add a separate point with matching text and wrong tags).

## 3. Assertion Correctness

**Assertions reviewed:**
- `test_rrf_fuse_order_and_scores`: asserts p2 (dual-list) tops output, no dups, scores descend — correct per §6.6.
- `test_hybrid_fusion_end_to_end`: pins `out[0]["score"] == pytest.approx(2 / 61, rel=1e-3)`. Verified: k=60, both lists have p_shared at rank 0 → 1/(60+0+1) + 1/(60+0+1) = 2/61. Correct.
- `test_hybrid_fusion_end_to_end`: asserts all `r["score"] < out[0]["score"]` for subsequent items. p_dense gets 1/(62) ≈ 0.0161, p_bm25 gets 1/(62) ≈ 0.0161, both less than 2/61 ≈ 0.0328. Correct (tied second/third).
- `test_no_filter_regression_unchanged`: asserts `query_filter is None` for a bare `semantic_search_core` call. Correct per D1/§5.5.
- `test_dense_search_with_ids_filter_equals_semantic_search_core` (QA-3): asserts structural parity of Qdrant `query_filter` between `semantic_search_core` and `_dense_search_with_ids` under types + space_id + source_type + domain_tags. The CaptureBoth client captures both `query_filter` objects. Assertion checks `must` list length, `space_id` FieldCondition value, types nested Filter `should` set, `source_type` MatchAny, and `domain_tags` MatchAny. This is a strong structural equality assertion. Correct.
- `test_bm25_cross_space_exclusion` (CSO-1): `obj_other` and `obj_target` BOTH have text "contradiction detection" so they score identically in BM25; only `obj_target` passes the `space_id="sp_A"` filter in `_bm25_search`. The assertion `"obj_other" not in result_ids` genuinely exercises the cross-space gate.

**Finding — BLOCKING:** `test_hybrid_recall_aggregate` (AC-EVAL, `tests/eval/test_retrieval_quality.py`, line 87):

```python
assert repro and repro["hr"] >= repro["dr"]
```

The spec addendum (item 2, CPO-1/QA-1/QA-2) is authoritative and explicitly mandates:

> "The repro-327 per-case assertion MUST show dense actually misses and hybrid recovers (i.e. `dense_recall < hybrid_recall`, not `>=`)"

The `>=` operator allows a tie (`hr == dr`) to pass, including the degenerate case where a no-op hybrid implementation returns exactly the same results as dense, producing `hr == dr == 0`. The addendum requires strict `>` (i.e., `repro["hr"] > repro["dr"]`), which would catch a no-op. As written, this assertion is too weak to prove the feature's reason for existing.

Required change: `tests/eval/test_retrieval_quality.py`, line 87:
```python
# Current (wrong):
assert repro and repro["hr"] >= repro["dr"]
# Required (correct per addendum):
assert repro and repro["hr"] > repro["dr"]
```

## 4. Test Validity (will they fail now?)

Ran: `uv run python -m pytest tests/test_indexer.py tests/wiki/test_query.py tests/wiki/test_query_fetch_paths.py tests/eval/ -m 'not live' -p no:cacheprovider -q`

Result: **48 failed, 103 passed, 10 skipped, 2 deselected** — matches the debrief exactly.

All 24 new `tests/test_indexer.py` tests fail for the correct reasons:
- `test_bm25_scores_keyword_match`: `ModuleNotFoundError: rank_bm25` (dependency not installed)
- AC-H2 tests (`_rrf_fuse`): `ImportError: cannot import name '_rrf_fuse'`
- All `hybrid_search_core` tests: `AttributeError: module has no attribute 'hybrid_search_core'`
- AC-H7/H8 tests (`_BM25Index`): `ImportError: cannot import name '_BM25Index'`
- AC-H9 (`_ensure_bm25_fresh`): `AttributeError: _build_bm25_index`
- AC-H10/QA-3/CSO-1 tests: `AttributeError: _read_bm25_corpus_version` or `_dense_search_with_ids`

All 24 retargeted tests in `test_query.py` + `test_query_fetch_paths.py` fail with `AttributeError: hybrid_search_core` because `query.py` still calls `indexer.semantic_search_core` (the call-site switch is implementation work).

Passing correctly:
- `test_no_filter_regression_unchanged` (AC-H-REG1): regression guard, expected PASS
- `test_no_filter_regression` (pre-existing #323 test): unaffected

AC-EVAL test is deselected with `-m 'not live'` as expected (0 selected from `tests/eval/`).

**PASSED** (all new tests are red for absent-symbol reasons; regression guard is correctly green).

## 5. Convention Compliance

This is a Python/pytest project (no bash tests involved). Checking Python-project conventions:

- `@pytest.mark.live` gate on live tests with deselect via `-m 'not live'`: PASSED
- Imports of new symbols inside test function bodies (not module-level), enabling collection before implementation: PASSED
- `monkeypatch` fixture used for all external dependencies (`_qdrant`, `embed_query`, `_read_bm25_corpus_version`): PASSED
- `tmp_path` fixture used for state file isolation in AC-H10 tests (no hardcoded `/tmp/` or `/Users/` paths): PASSED
- `FakeQdrantClientWithSearch.scroll` extended with the correct keyword-arg signature matching `_build_bm25_index`'s call shape (per §11.1/SG-7): PASSED

**Minor stale comments** (SUGGESTION, not compliance failures):
- `tests/wiki/test_query.py` line 455-478: comment block still says "semantic_search_core needs to be monkeypatched" and error message at line 478 says "indexer.semantic_search_core not importable"; the actual `setattr` at line 469 correctly targets `hybrid_search_core`.
- `tests/wiki/test_query.py` class `TestWikiQueryTypeFiltering` docstring (line 3202): still references "monkeypatch on query_mod.indexer.semantic_search_core"; actual code at 3224/3265 is correctly retargeted.
- `tests/wiki/test_query.py` line 3215: method docstring says "Captures the types kwarg on semantic_search_core" — should say `hybrid_search_core`.

These are documentation issues only; they do not affect test behavior.

**PASSED** (no BLOCKING convention violations).

## 6. Test Isolation

**Module-level state management:** Several tests directly mutate `ix._bm25_index` and `ix._bm25_built_version` (module-level singletons). This is by design (the spec §6.1 defines these as module-level state). Each test that depends on a specific state value resets it explicitly at the START of the test body (not relying on prior test state):

- `test_hybrid_fusion_end_to_end` (line 1331-1332): sets `ix._bm25_index = None; ix._bm25_built_version = -1`
- `test_hybrid_bm25_domain_tags_gate_real_build` (lines 1503-1504): same reset
- `test_build_bm25_empty_keeps_prior` (line 1550): sets `ix._bm25_index = prior` explicitly
- `test_build_bm25_empty_cold_stays_none` (line 1559): sets `ix._bm25_index = None`
- `test_ensure_bm25_fresh_rebuilds_on_version_change` (lines 1581-1582): resets both
- `test_bm25_cross_space_exclusion` (lines 1890-1891): resets both

Note: these direct assignments are NOT undone by `monkeypatch` cleanup. Tests that run AFTER a state-mutating test and have implicit state dependencies could theoretically be affected. However, cross-checking the test execution order shows no such implicit dependency: every test that uses `_bm25_index` or `_bm25_built_version` either (a) explicitly resets them first or (b) monkeypatches `_ensure_bm25_fresh`/`_bm25_search` to avoid touching module state at all.

**Other isolation checks:**
- `test_reindex_bumps_corpus_version` and `test_reembed_bumps_corpus_version` use `tmp_path` for `INDEX_STATE_FILE`: PASSED (no shared state file)
- `test_wiki_query_tier2_calls_hybrid` is a module-level function with `@respx.mock` decorator + `monkeypatch` fixture: PASSED (all external calls mocked, monkeypatches auto-reverted)

**PASSED** (no order-dependent or machine-state dependencies found).

## 7. Existing Test Impact

The retargeting of Tier-2 monkeypatches from `semantic_search_core` to `hybrid_search_core` affects pre-existing tests. These tests were correctly retargeted as part of the test-writer's work — they will fail RED after retargeting (because `hybrid_search_core` doesn't exist yet) and will go GREEN after implementation. This is the expected behavior.

**Verified retargeted sites (both files):**

`tests/wiki/test_query.py` (9 sites confirmed changed in diff):
- Line ~469: `TestRetrieval::test_retrieval_mode_boundary_matrix` — `_idx_mod.hybrid_search_core` ✓
- Line ~1012: `TestQdrantDownFallback::test_qdrant_down_boundary_matrix` — `_idx_mod.hybrid_search_core` ✓
- Line ~1059: `TestQdrantDownFallback::test_qdrant_down_below_threshold_falls_back_to_tier1` ✓
- Line ~1090: `TestQdrantDownFallback::test_qdrant_down_at_threshold_returns_api_error` ✓
- Line ~2372: `TestCompoundingBackstop::test_filed_query_retrievable_after_reindex` ✓
- Line ~2484: `TestTier2CandidateFetchFailure::test_tier2_candidate_fetch_failure_status_pinned` (skipped, skip decorator preserved) ✓
- Line ~2936: `TestContextBudgetD5Extension::test_synthesis_context_budget_trims_neighbors_first_d5_order` ✓
- Line ~3224: `TestWikiQueryTypeFiltering::test_wiki_query_default_passes_full_type_keys` ✓
- Line ~3265: `TestWikiQueryTypeFiltering::test_wiki_query_mixed_types_silently_narrowed` ✓

`tests/wiki/test_query_fetch_paths.py` (10 sites confirmed changed):
- Lines 260, 699, 793, 895, 997, 1121, 1182, 1245, 1413, 1503: all changed to `hybrid_search_core` ✓

**Out-of-scope sites correctly preserved on `semantic_search_core`:**
- `test_query.py` line 153: `TestWikiQueryImport::test_semantic_search_core_importable` — unchanged ✓
- `test_query.py` lines ~1810, ~1855: `TestNestedFilter::*` — call `semantic_search_core` directly ✓
- `test_query.py` line ~3369: `TestCrossTierDateFilterEquivalence` — calls `semantic_search_core` directly ✓
- `src/anytype_llm_wiki/wiki/lint.py:616` — still calls `indexer.semantic_search_core` ✓

No over-retargeting found.

**Recommended actions for affected pre-existing tests:**
All affected tests are correctly retargeted and will be GREEN after the implementation adds `hybrid_search_core`. No existing test asserts a value that the spec changes in a way that would require an UPDATE or DELETE. The only change is which symbol is monkeypatched.

**PASSED** (retargeting is correct and complete; no over-retargeting).

---

## Summary

The test-writer delivered a thorough test suite covering all 18 spec ACs plus the 3 addendum-mandated tests. All 24 new tests fail pre-implementation for the correct reasons (absent symbols), and the regression guard passes correctly. Two findings require changes:

**BLOCKING:** `test_hybrid_recall_aggregate` (`tests/eval/test_retrieval_quality.py:87`) uses `>=` for the repro-327 per-case assertion, but the authoritative addendum (item 2) mandates strict `>`. A no-op implementation where hybrid returns the same results as dense would satisfy `>=` but not `>`, defeating the purpose of the repro-327 individual gate.

**SHOULD-FIX:** `test_hybrid_bm25_domain_tags_gate_real_build` (`tests/test_indexer.py`, QA-4) — the "not in results" assertion for `obj_fin` is trivially true because `obj_fin`'s text ("financial analysis report") shares no tokens with the query ("machine learning"), so BM25 scores it exactly 0 and it never enters the filter gate path. The gate-DROP half is not exercised through the real build path. The gate-SURVIVAL assertion (obj_ml in results) is genuine.
