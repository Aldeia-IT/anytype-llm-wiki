# Test Review: 324-relationship-aware-retrieval-follow-anytype-relati Round 1

**Verdict: NEEDS CHANGES**

## Review Date
2026-06-12

## 1. Spec Coverage

AC1: PASSED — two tests cover the happy path (neighbor in sources_consulted) and the trim-all edge (SF-G). AC3 dedup is also tested within the AC1 class. AC11 (citation sanitization) is included in the same class.

AC2: PARTIAL — see Finding B1 below. The first assertion (`"wiki_sources" in _RELATION_KEYS`) gates correctly. The traversal assertion is soft (source_neighbor_obj is also a Tier-1 candidate, not a pure neighbor discovery).

AC3: PASSED — `test_sources_consulted_deduped_seed_and_neighbor` asserts `count <= 1` for the shared object. Valid forward-regression guard.

AC4: PASSED — `test_higher_rank_seed_neighbor_survives_trim` asserts n_rank0_id survives and n_rank1_id is dropped. However the test depends on correctly entering Tier-2 — see BLOCKING Finding B2.

AC5: BLOCKED — `test_cap_warning_and_d5_top_n_fetched` cannot enter Tier-2 due to BLOCKING Finding B2.

AC6: PARTIALLY BLOCKED — `test_fanout_debug_logged` and `test_fanout_info_warning_above_threshold` cannot enter Tier-2 due to BLOCKING Finding B2. `test_fanout_info_warning_absent_below_threshold` is a tautological pass (see Finding B3).

AC7: BLOCKED — `test_drew_from_excludes_neighbors` cannot enter Tier-2 due to BLOCKING Finding B2.

AC8: PASSED — existing `TestNeighborhoodCacheReplacement::test_shared_neighbor_fetched_once` covers this. It remains valid after D5 ordering.

AC9: PASSED — `test_synthesis_context_budget_trims_neighbors_first_d5_order` correctly sets `WIKI_INDEX_THRESHOLD=2` with 2 wiki objects in list_resp, triggering Tier-2. Assertions on n_a_id surviving and n_b_id dropped are correct. Fails for the right reason (D1 not implemented).

AC10: PASSED — `test_query_max_neighbors_config_rejects_zero_and_negative` correctly tests ImportError for missing `query_max_neighbors()`, then validates fallback for 0, -1, non-numeric, and a valid value. Clean test.

AC11: PASSED — `test_rejected_neighbor_name_redacted_in_sources` asserts `title == "[REDACTED]"` in the sources_consulted entry and the `synthesis_name_rejected` warning. Correct exact-string check.

AC12: BLOCKED — `test_partial_status_one_failed_one_succeeded_neighbor` cannot enter Tier-2 due to BLOCKING Finding B2.

## 2. Edge Case Coverage

PASSED for AC1, AC3, AC11 (dedup, trim-all, name rejection).
PASSED for AC10 (zero, negative, non-numeric, valid).
PARTIAL for AC2 — the traversal-only scenario (neighbor object absent from list_resp) is not tested.
BLOCKED for AC4, AC5, AC6, AC7, AC12 — edge cases untestable while Tier-2 routing is broken.
PASSED for AC8 (cache hit on repeated fetch of same neighbor).
PASSED for AC9 (D5 ordering within neighbors at trim boundary).

No significant missing edge cases beyond the Tier-2 wiring issue.

## 3. Assertion Correctness

PASSED — assertions are structurally correct for all tests that can reach the asserted code path.

Specific verifications:
- AC5 `"neighbor_fan_out_capped: 5 -> 2"`: correct ASCII `->` (not Unicode `→`). Spec D4 SG-1 is honored.
- AC6 `"neighbor_fanout: fetched="`: correct prefix match (does not hardcode N).
- AC11 `title == "[REDACTED]"`: exact-string comparison, correct.
- AC12 `status == "partial"`: correct string comparison.
- AC10 `query_max_neighbors() == 16`: correct integer comparison.
- AC9 D5 ordering: `n_a_id in source_ids` and `n_b_id not in source_ids` — correct identity assertions.

No tautological assertions were found in the RED-NOW tests (they would fail against any honest implementation before D1/D3/D4/D5/D6).

Finding B3 (below) identifies one tautological GREEN-NOW assertion.

## 4. Test Validity (will they fail now?)

BLOCKING Finding B2 applies to 6 RED-NOW tests (see below). These tests:
1. Set `WIKI_INDEX_THRESHOLD=1`
2. Use `stub_search` via `monkeypatch.setattr(_idx_mod, "semantic_search_core", ...)`
3. Set `list_resp = {"data": [_schema_obj()], "pagination": {"has_more": False}}`

The schema object has `type.key == "collection"`, which is NOT in `_WIKI_TYPE_KEYS`. Therefore `count = len(wiki_objects) = 0 < threshold = 1`. Tier-2 is never selected. `stub_search` is never called. The query returns the `_NO_SOURCES_ANSWER` early and the tests fail on the first real assertion — but they would continue to fail even after a correct implementation of D1–D6, because the mock wiring never delivers seed objects to the candidate-assembly loop.

These 6 tests will remain PERMANENTLY RED regardless of implementation:
- `TestFanOutCap::test_cap_warning_and_d5_top_n_fetched` (AC5) — test_query_fetch_paths.py:597
- `TestFanOutCap::test_partial_status_one_failed_one_succeeded_neighbor` (AC12) — test_query_fetch_paths.py:695
- `TestDeterministicTrimOrder::test_higher_rank_seed_neighbor_survives_trim` (AC4) — test_query_fetch_paths.py:782
- `TestFileBackSeedOnly::test_drew_from_excludes_neighbors` (AC7) — test_query_fetch_paths.py:887
- `TestFanOutDebugLog::test_fanout_debug_logged` (AC6) — test_query_fetch_paths.py:1009
- `TestFanOutDebugLog::test_fanout_info_warning_above_threshold` (AC6) — test_query_fetch_paths.py:1068

**Fix:** In each of these 6 tests, add at least one wiki-typed object to `list_resp["data"]` so that `count >= threshold`. For example, add the seed object(s) to list_resp as wiki_entity objects. The AC9 test (`test_query.py:2960`) correctly does this: `WIKI_INDEX_THRESHOLD=2` with 2 `wiki_entity` objects in `list_resp` → `count=2 >= threshold=2` → Tier-2 selected. Apply the same pattern to the 6 broken tests.

## 5. Convention Compliance

PASSED — all tests follow the project's Python conventions:
- Single `respx.get().mock(side_effect=dispatcher)` pattern used throughout `test_query_fetch_paths.py` (new tests).
- No hardcoded `/Users/` absolute paths in test bodies.
- `ALDEIA_DIR` derived from `os.path.abspath(__file__)` — portable.
- `autouse` env fixture (`set_anytype_env`) covers all cases.
- American spelling used throughout new classes (B4 compliant): `TestNeighborCitation`, `TestFanOutCap`, `TestDeterministicTrimOrder`, `TestFileBackSeedOnly`, `TestFanOutDebugLog`.

MINOR NOTE: `test_wiki_sources_relation_traversed` (test_query.py:2843) registers a specific `respx.get(url)` AFTER the catch-all `respx.get()`. Under respx 0.23.x, the catch-all wins and the specific route never fires. This is harmless in practice (source_neighbor_obj is in enum_map from list_resp so get_object is never called for it), but it is the exact antipattern documented in the test_query_fetch_paths.py file header. Does not cause test failure; no action required, but implementation context is worth noting.

## 6. Test Isolation

PASSED — each test uses `@respx.mock` decorator (fresh router per test), `monkeypatch` (auto-undone), and no shared mutable state between tests. Tests do not depend on execution order. Machine-specific state (no running services required; all HTTP is mocked). No shared temp directories.

## 7. Existing Test Impact

Only one existing test interacts meaningfully with spec-changed code:

**`TestContextBudget::test_synthesis_context_budget_trims_neighbors_first` (test_query.py:1613)**
- Current assertion: `len(sources) <= 2` where `sources = result["sources_consulted"]`
- Post-D1 semantic change: `sources_consulted` will include surviving neighbors, not just candidates. With cap=2 and 1 candidate + 3 neighbors in the test, `ordered` will be trimmed to 2 entries. The surviving 2 entries (sorted_candidates first) would be: 1 candidate + 1 neighbor (first neighbor in discovery order). So `len(sources) = 2` post-D1, which still satisfies `<= 2`.
- Verdict: assertion REMAINS VALID post-D1. The bound is still correct; only its semantic interpretation changes (as documented in spec B3). No update needed.

No other existing tests assert behavior that the spec changes in a way that would cause new failures.

---

## BLOCKING Findings

### B1 — AC2 traversal assertion is soft (SHOULD-FIX)

**File:** `tests/wiki/test_query.py:2808` (`test_wiki_sources_relation_traversed`)

**Problem:** `source_neighbor_obj` is included in `list_resp["data"]` with `type.key = "wiki_entity"`. In Tier-1, ALL wiki objects become candidates. Therefore `source_neighbor_id` appears in `sources_consulted` as a CANDIDATE, not as a neighbor discovered by `wiki_sources` traversal. The assertion `source_neighbor_id in source_ids` passes even if `wiki_sources` is added to `_RELATION_KEYS` but traversal code is broken — the object is reachable as a candidate independently of D3.

**Impact:** The first assertion (`assert "wiki_sources" in _RELATION_KEYS`) does gate the constant change. The test WILL fail pre-impl (correctly) and WILL pass post-impl (but for the wrong reason). This is a weak AC2 test that does not verify the traversal path is actually followed.

**Severity:** SHOULD-FIX (not BLOCKING because the constant guard is a meaningful gate and the test fails/passes correctly for the right spec change, even if the traversal assertion is soft).

**Fix:** Move `source_neighbor_obj` OUT of `list_resp["data"]` (so it is not a candidate). Place the test in `test_query_fetch_paths.py` using the dispatcher pattern, where `source_neighbor_id` is only reachable via a `get_object` call triggered by `wiki_sources` traversal. This makes the traversal assertion truly binding.

---

### B2 — 6 Tier-2 stub tests never enter Tier-2 (BLOCKING)

**Files and lines:**
- `tests/wiki/test_query_fetch_paths.py:636` — `TestFanOutCap::test_cap_warning_and_d5_top_n_fetched` (AC5)
- `tests/wiki/test_query_fetch_paths.py:722` — `TestFanOutCap::test_partial_status_one_failed_one_succeeded_neighbor` (AC12)
- `tests/wiki/test_query_fetch_paths.py:819` — `TestDeterministicTrimOrder::test_higher_rank_seed_neighbor_survives_trim` (AC4)
- `tests/wiki/test_query_fetch_paths.py:916` — `TestFileBackSeedOnly::test_drew_from_excludes_neighbors` (AC7)
- `tests/wiki/test_query_fetch_paths.py:1035` — `TestFanOutDebugLog::test_fanout_debug_logged` (AC6)
- `tests/wiki/test_query_fetch_paths.py:1090` — `TestFanOutDebugLog::test_fanout_info_warning_above_threshold` (AC6)

**Problem:** All 6 tests set `WIKI_INDEX_THRESHOLD=1` but `list_resp = {"data": [_schema_obj()], ...}`. The schema object has `type.key = "collection"`, not in `_WIKI_TYPE_KEYS`. So `count = 0 < threshold = 1`. Tier-2 is NOT selected. `stub_search` is never called. No candidates are found. `wiki_query` returns `_NO_SOURCES_ANSWER` with empty `sources_consulted` and empty `warnings`. Every subsequent assertion fails immediately with a result that will NEVER change regardless of how correctly D1–D6 are implemented.

**Confirmed by:** Running each test produces `object_count_at_decision: 0` in the result and an answer of `"No sources found in this wiki for that question."`.

**Fix for each affected test:** Add the seed object(s) to `list_resp["data"]` as `wiki_entity`-typed objects so `count >= threshold = 1`. Example for `test_cap_warning_and_d5_top_n_fetched`:

```python
# Before (broken):
list_resp = {"data": [_schema_obj()], "pagination": {"has_more": False}}

# After (correct):
list_resp = {"data": [
    _schema_obj(),
    {"id": seed_a_id, "name": "SeedA", "type": {"key": "wiki_entity"}, "properties": []},
    {"id": seed_b_id, "name": "SeedB", "type": {"key": "wiki_entity"}, "properties": []},
], "pagination": {"has_more": False}}
```

The dispatcher already handles `get_object` calls for these seeds and returns the properties (including `wiki_relations`), so adding them to `list_resp` merely satisfies the Tier-2 threshold gate. The same pattern is used correctly in AC9 (`test_query.py:2960`).

---

### B3 — `test_fanout_info_warning_absent_below_threshold` is a tautological GREEN-NOW (SHOULD-FIX)

**File:** `tests/wiki/test_query_fetch_paths.py:1132` (`TestFanOutDebugLog::test_fanout_info_warning_absent_below_threshold`)

**Problem:** This test also has `list_resp = {"data": [_schema_obj()], ...}` with `WIKI_INDEX_THRESHOLD=1`. It cannot enter Tier-2. The query returns early with empty `warnings`. The assertion `not any("neighbor_fanout: fetched=" in str(w) for w in warnings)` passes trivially because `warnings = []`. This is a soft pass: the test would also pass against an implementation that emits `neighbor_fanout: fetched=N` at the wrong threshold, or even always, because the query never reaches D6 code.

**Fix:** Apply the same fix as B2 (add wiki objects to list_resp) so that the test actually exercises the D6 threshold logic.

---

## Per-AC Coverage Table

| AC | Test(s) | Covered? | Adequate? |
|----|---------|----------|-----------|
| AC1 | `test_surviving_neighbor_in_sources_consulted`, `test_all_neighbors_trimmed_sources_seeds_only` | YES | YES — happy path + edge case |
| AC2 | `test_wiki_sources_relation_traversed`, `test_wiki_subjects_relation_traversed` | PARTIAL | WEAK — first assertion gates constant; traversal assertion is soft (source also a candidate) |
| AC3 | `test_sources_consulted_deduped_seed_and_neighbor` | YES | YES — asserts count <= 1 |
| AC4 | `test_higher_rank_seed_neighbor_survives_trim` | BLOCKED | NO — Tier-2 never entered (B2) |
| AC5 | `test_cap_warning_and_d5_top_n_fetched` | BLOCKED | NO — Tier-2 never entered (B2) |
| AC6 | `test_fanout_debug_logged`, `test_fanout_info_warning_above_threshold`, `test_fanout_info_warning_absent_below_threshold` | BLOCKED | NO — first two never enter Tier-2 (B2); third is tautological (B3) |
| AC7 | `test_drew_from_excludes_neighbors` | BLOCKED | NO — Tier-2 never entered (B2); filed_back=False on first assertion |
| AC8 | `test_shared_neighbor_fetched_once` (existing) | YES | YES — cache invariant is valid, remains green post-D5 |
| AC9 | `test_synthesis_context_budget_trims_neighbors_first_d5_order` | YES | YES — correct Tier-2 setup, asserts both seed survival and D5 neighbor ordering |
| AC10 | `test_query_max_neighbors_config_rejects_zero_and_negative` | YES | YES — tests ImportError, fallbacks, and valid value |
| AC11 | `test_rejected_neighbor_name_redacted_in_sources` | YES | YES — exact `[REDACTED]` and warning string check |
| AC12 | `test_partial_status_one_failed_one_succeeded_neighbor` | BLOCKED | NO — Tier-2 never entered (B2) |

## Summary

Six of fifteen tests (covering AC4, AC5, AC6, AC7, AC12) are permanently broken due to a repeated setup error: all use `WIKI_INDEX_THRESHOLD=1` with a `list_resp` containing only the schema collection object (no wiki-typed objects). The Tier-2 decision (`count >= threshold`) evaluates to `0 >= 1 = False`, so Tier-2 is never selected, `stub_search` is never called, and the query returns the no-sources early exit before any #324 behaviour is exercised. These tests will fail forever regardless of how correctly D1–D6 are implemented, making them BLOCKING spec gates that can never turn green. Additionally, one GREEN-NOW test (`test_fanout_info_warning_absent_below_threshold`) is tautological under the same broken setup. The fix for all seven cases is identical: add the seed objects to `list_resp` as `wiki_entity`-typed entries so that `count >= 1 = threshold`. The AC2 traversal assertion (SHOULD-FIX) is a softer issue where the source object is also a direct candidate, weakening the traversal-specific coverage.
