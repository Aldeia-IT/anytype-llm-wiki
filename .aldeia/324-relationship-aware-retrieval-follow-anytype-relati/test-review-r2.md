# Test Review: 324-relationship-aware-retrieval-follow-anytype-relati Round 2

**VERDICT: APPROVED**

## Review Date
2026-06-12

---

## R1 Findings — Resolution Status

### B2 (BLOCKING) — 6 Tier-2 stub tests never entered Tier-2

**RESOLVED.**

All 6 tests now have wiki-typed seed objects in `list_resp` so that `count >= threshold`:

- `TestFanOutCap::test_cap_warning_and_d5_top_n_fetched` (AC5): `WIKI_INDEX_THRESHOLD=2`; `list_resp` contains both seeds as `wiki_entity` stubs (test_query_fetch_paths.py:636–641). Fails at line 679: `AssertionError: AC5: must contain 'neighbor_fan_out_capped: 5 -> 2' in warnings. Got: []` — correct D4 assertion, not an early exit.

- `TestFanOutCap::test_partial_status_one_failed_one_succeeded_neighbor` (AC12): `WIKI_INDEX_THRESHOLD=1`; seed added as `wiki_entity` stub (test_query_fetch_paths.py:729–733). Fails at line 780: `AssertionError: AC12: succeeded neighbor ... must appear in sources_consulted. Got: ['entity-seed-partial-001']` — correct D1 assertion.

- `TestDeterministicTrimOrder::test_higher_rank_seed_neighbor_survives_trim` (AC4): `WIKI_INDEX_THRESHOLD=2`; both seeds in `list_resp` (test_query_fetch_paths.py:831–836). Fails at line 890: `AssertionError: AC4: neighbor from seed-rank-0 ('entity-neighbor-rank0') must survive trim. sources_consulted: ['entity-seed-dt-a', 'entity-seed-dt-b']` — correct D1+D5 assertion.

- `TestFileBackSeedOnly::test_drew_from_excludes_neighbors` (AC7): `WIKI_INDEX_THRESHOLD=2`; both seeds in `list_resp` (test_query_fetch_paths.py:934–939). GREEN-NOW (PASSED) — correct per spec SG-2: pre-D2 neighbors are never in sources_consulted so drew_from already contains only seed ids. Forward guard, non-tautological (actually fires file-back as confirmed by `result.get("filed_back")` assertion at line 995).

- `TestFanOutDebugLog::test_fanout_debug_logged` (AC6 debug): `WIKI_INDEX_THRESHOLD=1`; seed added as `wiki_entity` stub (test_query_fetch_paths.py:1058–1062). Fails at line 1089: `AssertionError: AC6 / D6: logger.debug with 'neighbor_fanout:' must be emitted. DEBUG messages: []` — correct D6 assertion.

- `TestFanOutDebugLog::test_fanout_info_warning_above_threshold` (AC6 above): `WIKI_INDEX_THRESHOLD=1`; seed added as `wiki_entity` stub (test_query_fetch_paths.py:1119–1122). Fails at line 1148: `AssertionError: AC6 / SF-E: 'neighbor_fanout: fetched=N' must appear in warnings when fetching > synth_max_objects//2. Got warnings: []` — correct D6 assertion.

None of the 6 failure messages contain "No sources found in this wiki for that question." — confirming the early-exit trap is eliminated.

---

### B1 (SHOULD-FIX) — AC2 wiki_sources traversal assertion was soft

**RESOLVED.**

The fix splits AC2 into two tests:

1. `TestRelationKeySet::test_wiki_sources_relation_key_present` (test_query.py:2807): pure constant guard — asserts `"wiki_sources" in _RELATION_KEYS`. Fails correctly: `AssertionError: ... Got: ('wiki_relations', 'wiki_related', 'wiki_drew_from', 'wiki_subjects')`.

2. `TestWikiSourcesTraversal::test_wiki_sources_neighbor_only_reachable_via_traversal` (test_query_fetch_paths.py:1229): `source_neighbor_id` (`entity-wiki-source-binding-001`) is absent from `list_resp` entirely — it is reachable only via `get_object` traversal. `fetch_counts` is used to assert it was fetched. Fails correctly: `AssertionError: AC2: source_neighbor_id 'entity-wiki-source-binding-001' must be fetched via traversal ... fetch_counts: {'entity-seed-wksrc-binding-001': 1, 'properties': 1, 'tags': 1}`. The neighbor is not fetched at all because `wiki_sources` is not yet in `_RELATION_KEYS`. The traversal assertion is now genuinely binding.

The `sources_consulted` assertion at test_query_fetch_paths.py:1294–1298 further tightens the test: even if traversal fires (D3 done) but D1 is not done, the neighbor would be fetched but not cited — giving a second meaningful gate.

---

### B3 (SHOULD-FIX) — `test_fanout_info_warning_absent_below_threshold` was tautological

**RESOLVED.**

The test now has `WIKI_INDEX_THRESHOLD=1` with a seed in `list_resp` (test_query_fetch_paths.py:1181–1185) so Tier-2 is entered. The anti-tautology guard at line 1211 asserts:
```python
assert result.get("answer", "") != "No sources found in this wiki for that question."
```
PASSED with this guard in place, confirming the query ran through real code and not the early exit. The test parameters (1 neighbor, `WIKI_SYNTH_MAX_OBJECTS=4` → threshold=2, 1 <= 2) correctly mirror the above-threshold test (3 neighbors → 3 > 2 → warning expected). GREEN-NOW for the correct reason: D6 not yet implemented, so no spurious warning is emitted for 1 neighbor.

---

## 1. Spec Coverage

Full AC1–AC12 traceability confirmed. All changes align with the traceability matrix in the debrief.

| AC | Test(s) | RED/GREEN-NOW | Correct Reason |
|----|---------|---------------|----------------|
| AC1 | `test_surviving_neighbor_in_sources_consulted` | RED | D1 missing: neighbor not in sources_consulted |
| AC1 (SF-G) | `test_all_neighbors_trimmed_sources_seeds_only` | GREEN | forward guard: pre-D1 seeds-only holds trivially |
| AC1, AC3 | `test_sources_consulted_deduped_seed_and_neighbor` | GREEN | forward guard: dedup holds pre-D1 |
| AC2 (const) | `test_wiki_sources_relation_key_present` | RED | D3 missing: wiki_sources absent from _RELATION_KEYS |
| AC2 (traversal) | `test_wiki_sources_neighbor_only_reachable_via_traversal` | RED | D3 missing: neighbor never fetched via traversal |
| AC2 | `test_wiki_subjects_relation_traversed` | GREEN | wiki_subjects already in 4-key set |
| AC4 | `test_higher_rank_seed_neighbor_survives_trim` | RED | D1+D5 missing: rank-0 neighbor not in sources_consulted |
| AC5 | `test_cap_warning_and_d5_top_n_fetched` | RED | D4 missing: no cap warning |
| AC6 (debug) | `test_fanout_debug_logged` | RED | D6 missing: no logger.debug line |
| AC6 (above) | `test_fanout_info_warning_above_threshold` | RED | D6 missing: no INFO warning above threshold |
| AC6 (below) | `test_fanout_info_warning_absent_below_threshold` | GREEN | D6 not implemented; no spurious warning; non-tautological |
| AC7 | `test_drew_from_excludes_neighbors` | GREEN | forward guard (SG-2): pre-D2 neighbors never in filed path |
| AC8 | `test_shared_neighbor_fetched_once` | GREEN | inherited from #285 |
| AC9 | `test_synthesis_context_budget_trims_neighbors_first_d5_order` | RED | D1+D5 missing: rank-0 neighbor not in sources_consulted |
| AC10 | `test_query_max_neighbors_config_rejects_zero_and_negative` | RED | `query_max_neighbors` not yet in config.py |
| AC11 | `test_rejected_neighbor_name_redacted_in_sources` | RED | D1 missing: neighbor not cited at all pre-D1 |
| AC12 | `test_partial_status_one_failed_one_succeeded_neighbor` | RED | D1 missing: succeeded neighbor not in sources_consulted |

PASSED.

---

## 2. Edge Case Coverage

PASSED. All major feature edge cases are covered:

- AC1 SF-G (trim-all, seeds-only): tested.
- AC2 constant + binding traversal: tested separately, both gates needed.
- AC3 dedup: tested for seed-as-neighbor overlap.
- AC4 D5 boundary: seed-rank-0 vs. seed-rank-1 at trim boundary, explicit survive/drop assertions.
- AC5 exact cap: 5 distinct neighbors capped to 2, asserts both which ids are fetched and which are not.
- AC6 above/below threshold: mirror tests with 3 and 1 neighbor respectively.
- AC7 seed-only file-back: 2 seeds + 3 neighbors, asserts all 3 neighbor ids absent from drew_from.
- AC10 guard: zero, negative, non-numeric, valid value.
- AC11 name rejection: policy-rejected prefix triggers `[REDACTED]` title + warning.
- AC12 mixed-fetch (partial): one fail, one success, D5 ordering active.

---

## 3. Assertion Correctness

PASSED. All assertions cross-reference correctly with the spec:

- `"neighbor_fan_out_capped: 5 -> 2"`: exact ASCII `->` (not Unicode `→`). Correct per D4 SG-1.
- `"neighbor_fanout: fetched="`: prefix match (not hardcoded N). Correct per D6 SF-E.
- `title == "[REDACTED]"`: exact-string comparison. Correct per AC11 SF-B.
- `status == "partial"`: exact string. Correct per AC12 SG-5.
- `query_max_neighbors() == 16`: integer comparison. Correct per AC10 D4 default.
- `fetch_counts.get(n_a1, 0) == 1` and `fetch_counts.get(n_b1, 0) == 0`: identity assertions on which neighbors are fetched. Correct per AC5 SF-F.
- `source_neighbor_id in source_ids` combined with `fetch_counts.get(source_neighbor_id, 0) >= 1`: both gates required post-impl (D3+D1). Correct two-stage binding for AC2.

No tautological assertions found in RED-NOW tests.

---

## 4. Test Validity (will they fail now? will they pass post-impl?)

PASSED. 11 tests fail for the intended missing-implementation reasons:

- AC1, AC11, AC12: `sources_consulted` does not include neighbors (D1 missing).
- AC2 constant: `wiki_sources` absent from `_RELATION_KEYS` (D3 missing).
- AC2 traversal: `source_neighbor_id` never fetched because `wiki_sources` not traversed.
- AC4, AC9: neighbors absent from `sources_consulted` due to D1+D5 missing.
- AC5: no `neighbor_fan_out_capped` warning (D4 missing).
- AC6 debug: no `logger.debug` with `neighbor_fanout:` (D6 missing).
- AC6 above: no `neighbor_fanout: fetched=N` in warnings (D6 missing).
- AC10: `ImportError: cannot import name 'query_max_neighbors'` (config not implemented).

No fails-forever traps remain. Mentally running each against a spec-faithful D1–D6 impl:

- D1 adds neighbors to `sources_consulted` → AC1, AC11, AC12, AC4/AC9 (with D5) pass.
- D3 adds `wiki_sources` to `_RELATION_KEYS` → AC2 constant passes; with traversal code also following it, AC2 binding passes.
- D4 adds cap logic → AC5 passes (cap triggers, warning is emitted, only n_a1/n_a2 fetched).
- D5 orders neighbors by `(seed_rank, relation_priority, object_id)` → AC4 and AC9 D5 assertions pass.
- D6 emits `logger.debug` + conditional INFO warning → AC6 debug passes; AC6 above passes (3 > 2 triggers INFO warning); AC6 below remains GREEN (1 <= 2, no warning).
- D2 passes `filed_sources` to `_maybe_file_back` → AC7 GREEN remains GREEN (behavior preserved).
- `query_max_neighbors()` added to config → AC10 passes.

---

## 5. Convention Compliance

PASSED.

- Single `respx.get().mock(side_effect=dispatcher)` pattern throughout all new `test_query_fetch_paths.py` tests. No route-ordering dependency.
- `test_query.py::TestRelationKeySet::test_wiki_subjects_relation_traversed` uses catch-all `respx.get().mock(return_value=...)` correctly (subjects are in `list_resp` as candidates, no specific `get_object` route needed).
- `set_anytype_env` autouse fixture covers all new tests via the module-level fixture.
- `ALDEIA_DIR` derived from `os.path.abspath(__file__)` — portable.
- No hardcoded `/Users/` paths in test bodies.
- American spelling: `TestNeighborCitation`, `TestFanOutCap`, `TestDeterministicTrimOrder`, `TestFileBackSeedOnly`, `TestWikiSourcesTraversal` — correct per B4.
- No hardcoded absolute paths under `/Users/`.

---

## 6. Test Isolation

PASSED.

- All `test_query_fetch_paths.py` tests use `@respx.mock` (fresh router per test).
- All `test_query.py` tests use `@respx.mock` or plain (no mock for pure-import tests).
- `monkeypatch` ensures all env mutations and `setattr` patches are undone after each test.
- No shared mutable state between tests. `fetch_counts`, `patch_calls` are local per test.
- Tests do not depend on execution order.
- No running services required; all HTTP is mocked.

---

## 7. Existing Test Impact

Only one existing test required re-verification:

**`TestContextBudget::test_synthesis_context_budget_trims_neighbors_first` (test_query.py:1613)**

This test passes (PASSED in the run output). The existing `len(sources) <= 2` assertion remains satisfied pre-D1 (sources_consulted counts candidates only, so still 1 or 2). Post-D1 the count will include surviving neighbors but the assertion `<= 2` still holds at `synth_max_objects=2`. The spec-writer documented this as B3 in the spec; the test-writer created a companion `TestContextBudgetD5Extension::test_synthesis_context_budget_trims_neighbors_first_d5_order` that adds explicit D5 identity assertions. No existing test is invalidated.

No other existing tests cover spec-changed code paths in a way that would regress.

---

## Summary

All three R1 findings (B2 BLOCKING, B1 SHOULD-FIX, B3 SHOULD-FIX) are fully resolved. The 6 Tier-2 stub tests now enter Tier-2 and fail at the correct #324 implementation assertions. The AC2 traversal assertion is now genuinely binding (source absent from list_resp, reachable only via `get_object` traversal). The B3 absent-below-threshold test is non-tautological, protected by an anti-tautology guard and a correct parameter mirror of its above-threshold sibling. The test suite produces exactly 11 failed / 64 passed / 6 skipped as expected. No new findings of blocking or major severity were introduced.
