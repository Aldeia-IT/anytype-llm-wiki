# Test Review: #336 wiki_domain_tags persistence + source indexing — Round 1

**Verdict: NEEDS CHANGES**

## Review Date
2026-06-13

## Test Run Summary
```
32 failed, 664 passed, 37 skipped, 3 xfailed, 50 warnings
```
736 tests total. All 32 new #336 tests fail pre-implementation (confirmed). The 3 xfailed are: 2 pre-existing bootstrap tests (unrelated to #336) + `test_wiki_query_out_of_taxonomy_filter_warns` (correctly marked xfail per AC-V-WARN / D11 deferral). The debrief's stated counts (32 RED, 250 GREEN, 16 SKIPPED, 1 XFAILED) appear to count only within the new test sections rather than the full suite — this is a reporting discrepancy only and does not affect validity.

---

## 1. Spec Coverage

The traceability matrix covers every AC in §10 + §12 + addendum:

- AC-P1/P2 (ingest domain_tags create/update): `TestIngestDomainTagsPersistence` — present and failing for the right reason (AssertionError: `wiki_domain_tags` absent from captured create/PATCH props).
- AC-P3 (domain_tags in meta/worklog.begin): `TestRememberDomainTagsInMeta` — correct seam (spies on `worklog.begin` not `_apply_batch`), JSON round-trip exercised. Fails: `meta` keys are `['relations', 'source', 'subject']` (domain_tags missing).
- AC-P4/P5 (remember domain_tags create/update): `TestRememberWritesDomainTags` — fails for right reason (wiki_domain_tags absent from props).
- AC-S1 (`wiki_source` chunks via `wiki_excerpt`): `test_wiki_source_chunks_via_wiki_excerpt` — fails (0 chunks currently).
- AC-S2/S3 (chunk payload carries source_type/domain_tags): `test_chunk_payload_carries_source_type`, `test_chunk_payload_carries_domain_tags` — fails.
- AC-S4 (absent source_type → absent from payload): `test_chunk_payload_no_source_type_when_absent` — GREEN (legitimate regression guard; see item 4).
- AC-S-REUSE: `test_create_source_writes_source_type_on_reuse_path` — fails correctly (wiki_source_type absent from captured update props).
- AC-S-AGENT: `test_remember_agent_source_no_note_is_chunkable` — fails: excerpt is `''`.
- AC-PAYLOAD: `test_chunk_to_payload_propagates_and_omits` — fails: KeyError on `source_type`.
- AC-RESOLVER (a/b/c): `TestResolveMultiSelectTags` — fails: ImportError.
- AC-F-ST/DT/COMB: filter tests — fail: TypeError (`source_type`/`domain_tags` param not accepted).
- AC-F-REG: `test_no_filter_regression` — GREEN (inherited #323, must stay green).
- AC-V-SS: `test_invalid_source_type_raises_value_error`, `test_invalid_domain_tags_raises_value_error` — fails: TypeError.
- AC-V-WQ: `TestWikiQueryValidation336` — fails: TypeError.
- AC-V-ZERO: `test_unknown_filter_value_yields_zero_no_raise` (indexer), `TestWikiQueryUnknownFilterNoRaise` (query) — fails: TypeError.
- AC-V-WARN: `TestWikiQueryOutOfTaxonomyWarn` — xfail with rationale (acceptable per spec D11).
- AC-T1-DT/ST: `TestTier1DomainTagsPredicate`, `TestTier1SourceTypePredicate` — fails: ImportError.
- AC-T1-ST-NOOP: `test_wiki_query_source_type_is_noop` — fails: TypeError.
- AC-IDX (version mechanic): `test_schema_version_3_bump_forces_full_reembed` — GREEN (see item 4 below).
- AC-IDX (index fields): `test_reindex_creates_payload_indexes` (updated) — fails: `source_type`/`domain_tags` absent from created_indexes.
- §10.2b chunker inversions: all four applied correctly (count 8→9, exact-set, `test_wiki_excerpt_in_allowlist`, `TestWikiSourceChunksViaWikiExcerpt`).
- §10.2a indexer inversion: `test_reindex_creates_payload_indexes` — old "not in" assertion removed, new positive assertion added.
- Addendum CTO-A2: `TestImportRegressionForLintPy` — 2 GREEN guards + 1 RED.
- OD-B default-exclude: `test_semantic_search_default_excludes_wiki_source` — RED. **See BLOCKING finding below.**

**Summary:** All ACs are mapped and most tests fail for the right reason. Two ACs have quality issues identified under items 4 and 3.

**PAYLOAD_SCHEMA_VERSION = 3 constant gap:** The §12 checklist entry "PAYLOAD_SCHEMA_VERSION is 3" has no direct executable guard. `test_schema_version_3_bump_forces_full_reembed` monkeypatches the constant to 3 — it proves the mechanic but does NOT gate the constant itself. An implementation that changes only the other deliverables while leaving `PAYLOAD_SCHEMA_VERSION = 2` in `config.py` would pass every test. **This is a BLOCKING gap** (see item 4).

## 2. Edge Case Coverage

PASSED with minor gaps:

- Empty filter lists: AC-T1-DT/ST explicitly test `_passes_*_filter(obj, [])` → always True (empty filter = no filter). PASSED.
- Invalid inputs (empty strings in lists): AC-V-SS and AC-V-WQ cover `source_type=[""]` and `domain_tags=[""]`. PASSED.
- Unknown/valid-but-missing value: AC-V-ZERO covers structurally valid but semantically unknown domain tag → zero results, no raise. PASSED.
- Absent properties → absent from payload (not null): AC-S4 and AC-PAYLOAD both cover this. PASSED.
- Multi-tag ANY-overlap: AC-T1-DT tests single-match and no-match cases explicitly. PASSED.
- HTTPError degradation: AC-RESOLVER (c) tests this path. PASSED.

One gap: AC-RESOLVER (b) tests that a known name is NOT silently absorbed into an empty return when an unknown name is alongside it. The assertion `assert "tag-ai-001" in ids` guards against the tautological "always return []" implementation. PASSED.

## 3. Assertion Correctness

Mostly PASSED. One BLOCKING and one SHOULD-FIX:

**BLOCKING — OD-B test assertion is insufficient (and unsatisfiable — see item 4):**
`test_semantic_search_default_excludes_wiki_source` at `tests/test_indexer.py:1177` ends with:
```python
assert fake_core.query_filter is not None, (...)
```
This only checks that SOME filter was built — it does NOT assert that `wiki_source` is absent from the type conditions. An implementation that passes ALL types (including `wiki_source`) to the default call would satisfy this assertion while violating the spec requirement. The assertion should additionally verify `wiki_source` is absent from the type-scoped should-group in `fake_core.query_filter`.

**SHOULD-FIX — AC-P2/AC-P5: OD-C SET semantics not discriminated:**
`test_ingest_writes_domain_tags_on_update` (AC-P2) and `test_remember_writes_domain_tags_on_update` (AC-P5) both set up existing entities with NO pre-existing `wiki_domain_tags` property. As a result, SET and MERGE semantics are indistinguishable — both would produce `wiki_domain_tags: ["tag-id-ai"]` in the PATCH. The tests correctly verify the write occurs (spec requirement met), but a MERGE implementation would also pass. Recommendation: add `{"key": "wiki_domain_tags", "multi_select": [{"id": "old-id", "name": "old-tag"}]}` to the existing entity's properties, and assert the PATCH contains ONLY `["tag-id-ai"]` (not `["old-id", "tag-id-ai"]`). This makes SET vs MERGE distinguishable.

**`test_wiki_property_heading_maps_all_eight_keys` docstring still says "8 keys":** The test logic (`for key in WIKI_TEXT_PROPERTY_KEYS`) is correct and will still pass post-implementation, but the docstring is now stale. Non-blocking.

All other assertions cross-reference correctly with spec. The chunker tests use exact-match on `heading == "Excerpt"`, payload tests use `all(c.get("source_type") == "document")`, filter tests inspect `FieldCondition.match.any` — all appropriate comparisons.

## 4. Test Validity (fail-first integrity)

**BLOCKING — `test_semantic_search_default_excludes_wiki_source` is unsatisfiable by a correct implementation:**

The spec (§11 Step 6 and addendum item 6) places the OD-B Option 2 default-exclusion guard in `server.py:semantic_search` ("when no types passed, default to the non-wiki_source type set"). The test calls `_indexer.semantic_search_core(query="test")` with NO types and asserts `fake_core.query_filter is not None`. A correct implementation (guard in `server.py`) would leave `semantic_search_core` unchanged — no-types call → `query_filter=None` — so `fake_core.query_filter is not None` would FAIL.

Alternatively, if the guard were placed in `semantic_search_core` itself (where the test targets), `test_no_filter_regression` would break (`call["query_filter"] is None` fails). The two tests are mutually exclusive at the `semantic_search_core` layer — any correct OD-B implementation that satisfies one breaks the other.

The fix: either (a) move the OD-B test to target `server.py:semantic_search` (monkeypatch `semantic_search_core`, call `semantic_search(query="test")`, inspect what `types` argument was passed), or (b) add a seam to `semantic_search_core` for a configurable default-types guard and update the no-filter regression test accordingly. The simpler fix is option (a) — redirect the test to the `server.py` seam per the spec's implementation plan.

Additionally, the test does NOT assert that `wiki_source` is absent from the filter's type conditions, which means even a partially-correct implementation (that builds a filter but still includes `wiki_source`) would satisfy the `is not None` guard. The corrected assertion must check type value exclusion explicitly.

**BLOCKING — `PAYLOAD_SCHEMA_VERSION = 3` constant has no fail-first guard:**

`test_schema_version_3_bump_forces_full_reembed` monkeypatches `config.PAYLOAD_SCHEMA_VERSION = 3`, so it passes right now despite `config.py` having `PAYLOAD_SCHEMA_VERSION = 2`. The §12 checklist item "PAYLOAD_SCHEMA_VERSION is 3" is a deliverable. An implementer who ships all other changes but forgets to change the constant from 2 to 3 in `config.py` would pass every test. A one-line guard is needed:

```python
def test_payload_schema_version_is_3():
    """#336 §12: PAYLOAD_SCHEMA_VERSION must be exactly 3 after #336 (config.py constant)."""
    from anytype_llm_wiki import config
    assert config.PAYLOAD_SCHEMA_VERSION == 3, (
        f"PAYLOAD_SCHEMA_VERSION must be 3 after #336 (was 2 pre-impl); "
        f"got {config.PAYLOAD_SCHEMA_VERSION}"
    )
```

This test is RED now (config has `2`) and GREEN after implementation — the definition of a correct fail-first guard. Add to `tests/test_indexer.py` alongside the existing schema-version tests.

**PASSED — `test_chunk_payload_no_source_type_when_absent` (AC-S4) is a legitimate regression guard:**
The test passes NOW because `chunk_object` currently does NOT add `source_type` to any chunk. When `source_type` IS absent from the input, it must remain absent from the output — that's the current behavior, and must remain so after implementation. The test-writer's justification (it stays GREEN post-impl, pinning the absence-means-absent contract) is correct. NOT a tautology.

**PASSED — `test_schema_version_3_bump_forces_full_reembed` (AC-IDX mechanic) is a legitimate guard:**
It monkeypatches the constant to 3 and verifies the reindex mechanic works. The mechanic already exists. The test is GREEN because it bypasses the non-implemented change. As noted above, a SEPARATE guard on the constant value is still needed.

**PASSED — `test_resolve_select_tag_still_importable_from_remember` and `test_lint_module_imports_cleanly`:**
Both are genuine regression guards (function currently exists in remember.py; lint.py currently imports it cleanly). Both must stay GREEN after the D1 refactor where remember.py re-exports the function. Legitimate.

## 5. Convention Compliance

This is a Python project. Conventions checked:

- Tests in `tests/` with class-based grouping: PASSED.
- `monkeypatch` (pytest fixture) used for injection: PASSED.
- `respx` for HTTP mocking: PASSED.
- `FakeQdrantClientWithSearch` reused from #323 pattern: PASSED.
- Temp directories use `tmp_path` (pytest) not `/tmp/` or `/Users/`: PASSED.
- No hardcoded absolute paths under `/Users/` in the test logic itself (only in debrief file, which is not a test): PASSED.
- `raising=False` used correctly when patching attributes that may not yet exist: PASSED.

One SHOULD-FIX: `test_create_source_writes_source_type_on_reuse_path` instantiates `FakeWikiClient` as a class inside the test method. `FakeWikiClient.update_object` signature uses `data` kwarg but the real `WikiClient.update_object` may have a different signature. This is test-internal and won't cause a false pass (the test fails for the correct reason), but it's worth verifying the real method signature post-implementation to ensure the fake matches.

## 6. Test Isolation

PASSED. Each test:
- Uses `monkeypatch` (pytest-scoped, auto-reset per test) for all state injection.
- Uses `tmp_path` (pytest-scoped) for state files.
- Uses `respx.mock` context managers (not shared state).
- No test depends on another's side effects or execution order.
- No global mutable state is modified without cleanup.

**One observation:** `test_remember_domain_tags_in_meta` spies on `worklog.begin` and calls `original_begin` — if `worklog.begin` has side effects (e.g., file writes), those could leak between tests. However, the test uses `monkeypatch.setattr` which auto-restores, so the spy is scoped. The `try/except` around `original_begin()` suppresses worklog errors. Acceptable.

## 7. Existing Test Impact

**AC-F-REG (`test_no_filter_regression`) is at risk from OD-B Option 2 if the default-exclusion guard lands in `semantic_search_core`:**

- **File:** `tests/test_indexer.py::test_no_filter_regression`
- **Current assertion:** `assert call["query_filter"] is None` when `semantic_search_core(query="test")` is called with no params.
- **Why at risk:** If OD-B Option 2 adds a hardcoded default-types guard in `semantic_search_core` (which is what `test_semantic_search_default_excludes_wiki_source` implicitly requires), this test will fail post-implementation.
- **Recommended action:** This is the core contradiction described in item 4. The resolution is to fix `test_semantic_search_default_excludes_wiki_source` to test the `server.py` seam instead, leaving `test_no_filter_regression` unchanged. If the implementer correctly places the guard in `server.py` (as specced), `test_no_filter_regression` remains GREEN unchanged.

**The four inverted chunker tests:**

| Old test | New test | Status |
|----------|----------|--------|
| `test_wiki_text_property_keys_has_eight_entries` | `test_wiki_text_property_keys_has_nine_entries` | Correctly replaced |
| `test_wiki_text_property_keys_exact_set` | Updated with `wiki_excerpt` | Correctly updated |
| `test_wiki_excerpt_not_in_allowlist` | `test_wiki_excerpt_in_allowlist` | Correctly inverted |
| `test_wiki_excerpt_excluded` (class `TestWikiExcerptExcluded`) | `TestWikiSourceChunksViaWikiExcerpt` | Correctly replaced |

All four are cleanly handled; no old version remains to fail on the new implementation.

**`test_wiki_property_heading_maps_all_eight_keys`:** Survives unchanged (iterates over `WIKI_TEXT_PROPERTY_KEYS`; adding `wiki_excerpt` to both the allowlist and the heading map means the loop still passes). Docstring says "8 keys" but test logic is correct. Not a blocking issue.

No other existing tests are at risk from #336 changes.

---

## Summary

There are two BLOCKING findings that prevent approval:

1. **`test_semantic_search_default_excludes_wiki_source` is unsatisfiable by a correct implementation** (tests the wrong layer — `semantic_search_core` — when the spec places the OD-B guard in `server.py:semantic_search`) AND its core assertion is insufficient (only checks `query_filter is not None`, not that `wiki_source` is absent from type conditions). The test conflicts with `test_no_filter_regression` at the `semantic_search_core` level. Fix: redirect to the `server.py` seam and strengthen the assertion to verify `wiki_source` exclusion.

2. **No fail-first guard for `PAYLOAD_SCHEMA_VERSION = 3`** (the test monkeypatches around the constant, making it possible to ship without bumping it). Fix: add `test_payload_schema_version_is_3` that directly asserts `config.PAYLOAD_SCHEMA_VERSION == 3`.

Additionally there is one SHOULD-FIX: AC-P2 and AC-P5 update-path tests do not discriminate SET from MERGE (no pre-existing tags in the existing entity), meaning a MERGE implementation passes. Add pre-existing `wiki_domain_tags` to the entity fixture to make the SET contract verifiable.

All other 30 new tests are well-structured, fail for the correct reasons, use appropriate assertion specificity, and test the real production seams rather than stubs. The AC-RESOLVER non-tautology guard, the AC-S4 regression guard, the AC-V-WARN xfail, and the CTO-A2 import-regression tests are all correctly implemented.
