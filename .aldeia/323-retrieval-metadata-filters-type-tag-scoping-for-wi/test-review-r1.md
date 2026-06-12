# Test Review: retrieval-metadata-filters-type-tag-scoping Round 1

**Verdict: APPROVED**

## Review Date
2026-06-12

## 1. Spec Coverage

Every AC in §12 has at least one genuine asserting test. Full traceability:

| AC | Test(s) | Assertion genuine? |
|---|---|---|
| F1 No-filter regression | `test_no_filter_regression` | Yes — asserts `query_filter is None`, collection name, limit, with_payload |
| F1b Default `wiki_query` passes full `_WIKI_TYPE_KEYS` | `TestWikiQueryTypeFiltering::test_wiki_query_default_passes_full_type_keys` | Yes — captures kwarg on monkeypatched core, asserts set equality with `_WIKI_TYPE_KEYS` |
| F2 Nested-should type filter shape | `test_type_filter_applied` | Yes — introspects `must` list for a `should`-bearing condition, asserts both type values present |
| F4 DatetimeRange applied | `test_date_range_filter_applied` | Yes — finds `FieldCondition(key="last_modified_date")` in `must`, asserts `isinstance(range, DatetimeRange)`, asserts `gte` and `lte` not None |
| F5 Combined AND | `test_combined_filter_and` | Yes — asserts both type and date conditions in `must` |
| F5b Empty list == no filter | `test_empty_list_types_is_no_filter` | Yes — asserts `query_filter is None` |
| F5c Zero results returns `[]` | `test_zero_result_filter` | Yes — asserts `out == []` |
| F6 ValueError from `semantic_search` | `test_invalid_date_raises_value_error` | Yes — `pytest.raises(ValueError, match="ingested_after")` |
| F6b Error dict from `wiki_query` bad date | `TestWikiQueryDateValidation::test_wiki_query_bad_date_returns_error_dict` | Yes — asserts `status=="error"`, `error_category=="config_error"` |
| F6c Empty type intersection error dict | `TestWikiQueryDateValidation::test_wiki_query_empty_type_intersection_error` | Yes — same pattern |
| F7a Indexes on reindex path | `test_reindex_creates_payload_indexes` | Yes — asserts `{type_key, space_id, last_modified_date} ⊆ created_indexes` and `source_type` absent |
| F7b No indexes on reembed hot path | `test_reembed_does_not_create_payload_indexes` | Yes — asserts `created_indexes == []` |
| F8 Chunker writes date (body object) | `TestChunkerLastModifiedDate::test_chunker_writes_last_modified_date` | Yes — asserts every chunk has `last_modified_date` equal to expected string |
| F9 Chunker property-only + absence | `TestChunkerLastModifiedDate::test_chunker_property_concept_date_and_absence` | Yes — asserts date present on dated object; asserts key absent on no-date object |
| F10 Tier-1 type predicate | `TestTier1Predicates::test_tier1_type_predicate` | Yes — imports `_passes_type_filter`, tests True/False cases |
| F10 Tier-1 date predicate | `TestTier1Predicates::test_tier1_date_predicate` | Yes — tests in-range, too-old, and no-date (missing field never matches) |
| F10b Mixed types silently narrowed | `TestWikiQueryTypeFiltering::test_wiki_query_mixed_types_silently_narrowed` | Yes — Tier-2 seam, asserts `captured["types"] == {"wiki_entity"}` with `wiki_source` dropped |
| F11a Schema bump forces full re-embed | `test_schema_version_bump_forces_full_reembed` | Yes — pre-seeds old version, asserts `objects_indexed==1`, upsert happened, version stamped to 2 |
| F11b No bump preserves incremental skip | `test_no_bump_keeps_incremental_skip` | Yes — asserts `objects_indexed==0` |
| F12 `reembed_object` writes date | `test_reembed_writes_last_modified_date` | Yes — asserts all payload dicts carry expected date string |
| CSO-5 Cross-tier equivalence | `TestCrossTierDateFilterEquivalence::test_cross_tier_date_filter_equivalence` | Yes — see §4 for detail |

PASSED

## 2. Edge Case Coverage

**Type filter:**
- Empty list (`types=[]`) → no filter: `test_empty_list_types_is_no_filter` ✓
- Single valid type: covered by `test_type_filter_applied` and Tier-1 tests ✓
- Non-wiki type in list → narrowed: `test_wiki_query_mixed_types_silently_narrowed` ✓
- All non-wiki types → error dict: `test_wiki_query_empty_type_intersection_error` ✓

**Date filter:**
- Both bounds: `test_date_range_filter_applied` ✓
- Lower bound only: `test_combined_filter_and` (ingested_after only) ✓
- Zero results: `test_zero_result_filter` ✓
- Malformed date, `semantic_search`: `test_invalid_date_raises_value_error` ✓
- Malformed date, `wiki_query`: `test_wiki_query_bad_date_returns_error_dict` ✓
- Missing date field never matches: `test_tier1_date_predicate` no_date case ✓
- Inclusive lower edge: CSO-5 edge_obj case ✓
- Timezone normalization (Z vs +00:00): CSO-5 ✓

**Payload / chunker:**
- Body object with date: `test_chunker_writes_last_modified_date` ✓
- Property-only object with date: `test_chunker_property_concept_date_and_absence` ✓
- Object without date property → key absent from chunk ✓

**Migration:**
- Schema bump with unchanged object → forced re-embed + version stamped ✓
- Same version → incremental skip preserved ✓

PASSED

## 3. Assertion Correctness

**Filter shape (pinned contract §6.1–6.2):** `test_type_filter_applied` correctly checks for the nested `Filter(should=[FieldCondition(MatchValue)])` shape, not `MatchAny`. The test introspects `hasattr(c, "should") and c.should` on the must-list entry, which correctly identifies a nested `Filter` object. The type-value assertion uses set-subset (`<=`) which is appropriate since the spec says the filter should contain exactly the passed types.

**DatetimeRange shape:** `test_date_range_filter_applied` correctly imports and asserts `isinstance(date_cond.range, DatetimeRange)`, ruling out `Range`. Both `gte` and `lte` not-None checks are exact per spec §6.2.

**Addendum CSO-5 exclusivity check:** `DatetimeRange` has a real `gt` field (verified via `DatetimeRange.model_fields`). The assertion `getattr(date_cond.range, "gt", None) is None` is non-tautological — if the impl incorrectly used `gt=` instead of `gte=`, `gt` would be non-None (a datetime object) and the assertion would fail correctly.

**Validation error messages:** `test_invalid_date_raises_value_error` uses `match="ingested_after"` which matches the spec-defined error template `"Invalid date format for ingested_after: ..."`. Correct.

**Migration version stamping:** `test_schema_version_bump_forces_full_reembed` reads back the written JSON and asserts `new_state["_payload_schema_version"] == 2`, matching the spec D3 contract exactly.

**Regression guards:** AC-F1b asserts `set(captured["types"]) == set(query_mod._WIKI_TYPE_KEYS)`, anchored to the live `_WIKI_TYPE_KEYS` constant. This guards the §8.1 `effective_types_set` refactor: if the impl forgets the default-types case, `types=None` would reach the core and the assertion would fail.

No incorrect expected values, wrong comparison operators, or tautological assertions found.

PASSED

## 4. Test Validity (will they fail now?)

Ran `uv run pytest tests/test_indexer.py tests/test_chunker.py tests/wiki/test_query.py -q`.

**Observed pytest summary:**
```
15 failed, 101 passed, 11 skipped in 0.95s
```

**All 15 new-behavior tests fail for the correct reasons:**

| Test | Failure mode | Correct? |
|---|---|---|
| `test_date_range_filter_applied` | `TypeError: semantic_search_core() got an unexpected keyword argument 'ingested_after'` | Yes — missing param |
| `test_combined_filter_and` | Same TypeError | Yes |
| `test_invalid_date_raises_value_error` | `TypeError: semantic_search() got an unexpected keyword argument 'ingested_after'` | Yes — missing param |
| `test_reindex_creates_payload_indexes` | `AssertionError: … got: []` | Yes — `_ensure_payload_indexes` not yet called |
| `test_schema_version_bump_forces_full_reembed` | `AttributeError: config has no attribute 'PAYLOAD_SCHEMA_VERSION'` | Yes — constant missing |
| `test_no_bump_keeps_incremental_skip` | Same AttributeError | Yes |
| `test_reembed_writes_last_modified_date` | `AssertionError: payload lacks last_modified_date` | Yes — `_chunk_to_payload` not yet extended |
| `test_chunker_writes_last_modified_date` | `AssertionError: Chunk dates: [None]` | Yes — chunker not yet extended |
| `test_chunker_property_concept_date_and_absence` | Same AssertionError | Yes |
| `test_wiki_query_bad_date_returns_error_dict` | `TypeError: wiki_query() got an unexpected keyword argument 'ingested_after'` | Yes — missing param |
| `test_wiki_query_empty_type_intersection_error` | `TypeError: wiki_query() got an unexpected keyword argument 'types'` | Yes — missing param |
| `test_tier1_type_predicate` | `ImportError: cannot import name '_passes_type_filter'` | Yes — function not yet added |
| `test_tier1_date_predicate` | `ImportError: cannot import name '_passes_date_filter'` | Yes — function not yet added |
| `test_wiki_query_mixed_types_silently_narrowed` | `TypeError: wiki_query() got an unexpected keyword argument 'types'` | Yes — missing param |
| `test_cross_tier_date_filter_equivalence` | `ImportError: cannot import name '_passes_date_filter'` | Yes — function not yet added |

No test fails due to a syntax error, a typo'd attribute, or an unsatisfiable mock. Every failure points directly at missing implementation.

**6 regression guards correctly pass:**

| Test | Why it passes | Genuine guard? |
|---|---|---|
| `test_no_filter_regression` | No-filter path already produces `query_filter=None` | Yes — guards against `must` accidentally getting a no-op entry after the filter refactor |
| `test_type_filter_applied` | Nested-should already implemented | Yes — guards the existing filter shape against accidental `MatchAny` substitution |
| `test_empty_list_types_is_no_filter` | Empty list is falsy, no filter clause added | Yes — guards the falsy-empty-list contract |
| `test_zero_result_filter` | Empty results already work | Yes — guards against any exception-on-empty regression |
| `test_reembed_does_not_create_payload_indexes` | `reembed_object` never called `create_payload_index` | Yes — guards the hot-path off-gate that the spec explicitly requires |
| `TestWikiQueryTypeFiltering::test_wiki_query_default_passes_full_type_keys` | `wiki_query` already hardcodes `types=list(_WIKI_TYPE_KEYS)` at line 449 | Yes — guards the §8.1 `effective_types_set` refactor won't regress default behavior; spec addendum [CTO-4/CSO-4] explicitly requires this as an exit criterion |

PASSED

## 5. Convention Compliance

This is a Python project. Applicable conventions:

- **No hardcoded `/Users/` paths:** confirmed absent from all three test files.
- **No hardcoded `/tmp/` paths:** all temp paths use pytest's `tmp_path` fixture.
- **Isolation via monkeypatch:** all external dependencies (`_qdrant`, `embed`, `embed_query`, `list_spaces`, `list_objects`, `get_object`, `semantic_search_core`, `synthesize`, `config.index_threshold`) are patched per-test and auto-restored.
- **No live service dependencies for new tests:** the autouse `check_services` fixture in `test_indexer.py` only skips tests marked `"live"` or in classes with `_requires_live = True`. All 21 new tests are top-level functions or in unmarked classes → run unconditionally in CI.
- **FakeQdrantClientWithSearch vs UserWarning:** the fake client's `create_payload_index` is a pure no-op that never emits a `UserWarning`, consistent with spec §6.3's guidance. No `filterwarnings` decorator needed (and correctly absent).
- **`_FakeQdrantForCrossTier` inline copy:** justified in debrief (self-contained file; test files are not importable as packages). The duplicate is minimal and maintains parity with the spec §10.1 shape.

PASSED

## 6. Test Isolation

**Order independence:** each test creates its own `FakeQdrantClientWithSearch` or `_FakeQdrantForCrossTier` instance and patches module-level symbols via `monkeypatch`, which auto-restores after each test. No shared mutable state between tests.

**Migration tests (`test_schema_version_bump_forces_full_reembed`, `test_no_bump_keeps_incremental_skip`):** both patch `config.INDEX_STATE_FILE` and `config.INDEX_STATE_DIR` to `tmp_path`, ensuring complete isolation from the machine's real state file. ✓

**`test_reindex_creates_payload_indexes` — SHOULD-FIX (not BLOCKING):**

This test patches `list_spaces → []` but does NOT patch `config.INDEX_STATE_FILE` or `config.INDEX_STATE_DIR`. After implementation, `reindex()` calls `_save_state()`, which calls `config.INDEX_STATE_DIR.mkdir(parents=True, exist_ok=True)` and then `config.INDEX_STATE_FILE.write_text(...)`. With `list_spaces → []` and no objects processed, the state written is `{"_payload_schema_version": 2}` (the version stamp after force_full detects a version bump). This writes to the real machine state file at `/Users/agent/.local/share/anytype-llm-wiki/state.json`.

This is inconsistent with the existing `test_property_only_reindex_upserts_payload` (which does patch the state file) and with all migration tests. In CI where no real state exists, the side effect is harmless but creates the directory and file unexpectedly. On a developer machine, it would mutate the production state file.

The fix is a two-line addition: `monkeypatch.setattr(config, "INDEX_STATE_FILE", tmp_path / "state.json")` and `monkeypatch.setattr(config, "INDEX_STATE_DIR", tmp_path)`.

This finding is **SHOULD-FIX** severity. The test will still produce the correct pass/fail verdict regardless of this side effect; it does not make the test vacuous or incorrect.

**`test_reembed_does_not_create_payload_indexes`:** `reembed_object` does not call `_load_state` or `_save_state`, so no state file concern. ✓

**`TestWikiQueryTypeFiltering` respx route ordering:** the catch-all `respx.get()` mock is registered before the specific `respx.get(url)` mock. Since `semantic_search_core` is monkeypatched to return `[]` (no candidates), no individual `get_object` calls are made on the Tier-2 path. The catch-all serves only the `list_objects` call. The specific GET mock is unreachable but harmless — it does not cause the test to pass vacuously, since the captured-types assertion depends on `semantic_search_core` being called, not on any specific GET response. ✓

**`TestWikiQueryDateValidation` tests:** both call `wiki_query` with a missing param, which currently raises `TypeError` at the function call. No network calls, no state writes. After impl, they call the real `wiki_query` which returns an error dict before constructing `AnytypeReadClient` / `WikiClient`. Isolation is preserved. ✓

## 7. Existing Test Impact

The diff against `e30b9a1` shows **zero deleted lines** across all three test files. All changes are purely additive. No existing test body, assertion, or import was modified.

Pre-existing behavior covered by existing tests that this spec changes:

**`test_type_filter_applied` (new, passes currently):** this is a _new_ test that was absent before this commit. It guards the already-implemented nested-should shape that `semantic_search_core` currently uses. After the spec's refactor, the filter shape is unchanged for this path, so no pre-existing test is obsoleted.

**Tier-2 `semantic_search_core` call in `test_retrieval_mode_boundary_matrix` (`tests/wiki/test_query.py:462`):** the existing test uses a fake `semantic_search_core` stub with signature `(query, space_id, types, limit=10)` — without `ingested_after`/`ingested_before`. After implementation, `semantic_search_core` gains these two new keyword params (with defaults), so the existing 3-positional-arg stub remains valid (Python allows calling a function with fewer kwargs than it accepts). No update required.

No other existing tests assert behavior that the spec is changing. The spec extends the function signatures additively (new optional params with `None` defaults), so all existing call sites remain valid.

PASSED

## Summary

All 21 new tests (15 failing + 6 regression guards) are correctly positioned: every failing test fails for the right reason (a missing implementation artifact, never a test-code defect), and every regression guard protects a genuinely load-bearing existing behavior. Filter shape assertions are pinned to the spec §6.1–6.2 contract (`Filter(should=[FieldCondition(MatchValue)])`, `DatetimeRange` not `Range`). The addendum's two exit criteria — genuine Tier-2 enumeration harness for AC-F1b/F10b, and cross-tier date-filter equivalence for CSO-5 — are both met with non-vacuous, independently asserting checks. The one SHOULD-FIX finding (`test_reindex_creates_payload_indexes` missing `INDEX_STATE_FILE` patch) does not affect the test's correctness or verdict, and can be addressed alongside or immediately after implementation.
