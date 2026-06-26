# Test Review: retrieval-lexical-hybrid-dense-sparse-fusion Round 2

**Verdict: APPROVED**

Both R1 findings (1 BLOCKING, 1 SHOULD-FIX) are resolved. The SUGGESTION was also applied.
No new problems were introduced.

## Review Date
2026-06-26

## R1 Finding Verification

### Finding 1 — BLOCKING: repro-327 strict gate (`tests/eval/test_retrieval_quality.py`)

**Status: RESOLVED.**

The diff at line 93 confirms the operator changed from `>=` to `>`:

```python
# After (correct):
assert repro and repro["hr"] > repro["dr"], (
    f"repro-327: hybrid recall must strictly exceed dense recall "
    f"(dense_recall < hybrid_recall required — a no-op tie is a failure)\n{rpt}"
)
```

The aggregate mean assertions at lines 87-92 correctly remain `>=` (tolerating ties across the full fixture set). Only the per-case repro-327 gate is strict. This is exactly the required change — nothing else was altered in the assertion logic or the aggregate path. The docstring was updated to explain both classes of assertion clearly.

### Finding 2 — SHOULD-FIX: QA-4 real drop path (`test_hybrid_bm25_domain_tags_gate_real_build`)

**Status: RESOLVED.**

`obj_fin`'s corpus text was changed from `"financial analysis report"` to `"machine financial analysis"`. Explicit BM25 scoring analysis confirms the fix is sound:

- Query tokens: `["machine", "learning"]`
- Corpus size N=3; all 3 documents contain "machine" → raw IDF("machine") = log(0.5/3.5) ≈ -1.945 (negative)
- BM25Okapi's `_calc_idf` floors negative IDFs at `epsilon * average_idf`. With the other 7 vocabulary terms each having IDF ≈ 0.511, average_idf ≈ 0.204, epsilon=0.25 → floor ≈ 0.051 (positive).
- "learning" does NOT appear in `obj_fin` → contributes 0 to `obj_fin`'s score.
- `obj_fin` BM25 score = 0.051 × (tf contribution for "machine") > 0.

`obj_fin` passes the `if score <= 0: break` guard in `_bm25_search` and reaches `_passes_inline_filters`. There its `domain_tags=["finance"]` does not intersect the query's `domain_tags=["ml"]`, so the filter gate drops it. If `_passes_inline_filters` were deleted, `obj_fin` (score > 0) would appear in results and `assert "obj_fin" not in result_ids` would FAIL — correctly catching the regression. The gate-DROP half is now genuinely exercised through the real build path.

The test still monkeypatches only `_qdrant` and `embed_query` (plus `_read_bm25_corpus_version` to prevent a version-file read). `_build_bm25_index` and `_bm25_search` run via the real code path. The survival assertion (`obj_ml in result_ids`) is unchanged and genuine.

### SUGGESTION: Stale comments in `tests/wiki/test_query.py`

**Status: RESOLVED.**

All four sites identified in R1 were updated, plus a fourth occurrence at line 3254 identified by the fixer:

1. Line 455: `"hybrid_search_core needs to be monkeypatched"` (was semantic_search_core)
2. Line 457: `"monkeypatch hybrid_search_core to return..."` (was semantic_search_core)
3. Line 462: function renamed `fake_hybrid_search_core` (was fake_semantic_search_core)
4. Line 478: error message updated to `hybrid_search_core` (was semantic_search_core)
5. Line 3202 class docstring: `"monkeypatch on query_mod.indexer.hybrid_search_core"` (was semantic_search_core)
6. Line 3215 method docstring: `"Captures the types kwarg on hybrid_search_core"` (was semantic_search_core)
7. Line 3254 method docstring: `"only wiki_entity passed to hybrid_search_core"` (was semantic_search_core)

No `setattr` call was changed — only comments and docstrings. The `setattr` on line 469 correctly targets `"hybrid_search_core"` and uses `fake_hybrid_search_core` as the handler (consistent).

## 1. Spec Coverage

No change from R1. All 18 ACs (AC-H1 through AC-H-REG1, AC-EVAL) and the three addendum-mandated tests (QA-3, QA-4, CSO-1) remain covered.

**PASSED.**

## 2. Edge Case Coverage

No change from R1. All boundary conditions, filter precedence conflicts, and empty/invalid-input cases remain covered. The QA-4 fix strengthens the domain-tags drop path without removing any existing cases.

**PASSED.**

## 3. Assertion Correctness

The repro-327 per-case assertion is now strict `>` as required by the addendum. The aggregate `>=` assertions are unchanged. All other assertions verified in R1 are unchanged.

**PASSED.**

## 4. Test Validity (will they fail now?)

Ran:
```
uv run python -m pytest tests/test_indexer.py tests/wiki/test_query.py tests/wiki/test_query_fetch_paths.py tests/eval/ -m 'not live' -p no:cacheprovider -q 2>&1 | tail -15
```

Result: **48 failed, 103 passed, 10 skipped, 2 deselected** — identical to the R1 baseline.

- `test_hybrid_bm25_domain_tags_gate_real_build` still fails: `AttributeError: <module 'anytype_llm_wiki.indexer'> has no attribute '_read_bm25_corpus_version'` (correct; absent-symbol failure, not a false pass).
- `test_no_filter_regression_unchanged` (AC-H-REG1) still passes (regression guard correctly green).
- No new collection errors introduced.
- No previously-failing test accidentally fixed.

**PASSED.**

## 5. Convention Compliance

No changes to convention compliance since R1. Comment/docstring updates in `test_query.py` are documentation-only; no structural or fixture changes were made.

**PASSED.**

## 6. Test Isolation

No new state-sharing or order-dependency introduced. The QA-4 fix changes only the corpus text in a local `pts` list; the explicit state resets at lines 1513-1514 (`ix._bm25_index = None; ix._bm25_built_version = -1`) remain in place.

**PASSED.**

## 7. Existing Test Impact

No change from R1. All retargeted sites confirmed correct in R1 remain correct. The fixer made no changes to `test_query_fetch_paths.py` or any previously-verified retargeting site. Remaining uses of `semantic_search_core` in `test_query.py` are all intentional (direct-call tests, import-check test, "must NOT be called" guard in `test_wiki_query_tier2_calls_hybrid`).

**PASSED.**

## Summary

Both R1 findings are resolved. The BLOCKING repro-327 assertion is now correctly strict (`>`), while the aggregate assertions remain `>=` as designed. The QA-4 filter-gate drop assertion is now genuine: BM25Okapi's epsilon floor for very-common terms ensures `obj_fin` scores > 0 for the query "machine learning", reaches the filter gate, and is dropped only by the domain-tags mismatch — meaning a deleted `_passes_inline_filters` would cause the test to fail. The stale comment/docstring cleanup is complete and no `setattr` targets were disturbed. The test suite count is stable at 48/103/10/2.
