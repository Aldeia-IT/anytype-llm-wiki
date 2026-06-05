# Test Review: wiki_lint v0.5.0 Round 2

> **⚠️ SUPERSEDED CORRECTION (post-test council, 2026-06-05).** This file's
> "two-call `list_objects`" guidance (the Stub Run section at line ~83, the
> "Implementation Note for impl-worker" section, and the Summary's closing
> sentence) is **WRONG and SUPERSEDED.** The fixtures were subsequently fixed
> (commit `1c5a0df`) to a **single combined enumeration page**, and the spec
> mandates **ONE** `list_objects` enumeration reused for both the QA#25 schema
> gate and the check battery (Pre-Checks step 2, note G9; `query.py:408`
> pattern). A two-call implementation will violate the spec and double the O(N)
> enumeration cost. The post-test council ruled the stale two-call note a
> **BLOCKING** trap (CTO). The authoritative implementation contract is in
> `test-review-r2-lead-addendum.md` and `spec-addendum-post-test-r1.md`
> (single-enumeration constraint). Disregard every "two-call" statement below.

**Verdict: APPROVED**

## Review Date
2026-06-05

---

## R1 Finding Resolutions

### B1 (BLOCKING) — wiki_status tag id mismatch

**Status: RESOLVED**

**Evidence read:**

- `_make_entity` line 139: `{"key": "wiki_status", "select": {"name": wiki_status, "id": f"tag-{wiki_status}-id"}}` — with comment confirming alignment requirement.
- `_make_concept` line 175: identical change and comment.
- `_make_tags_response` lines 259-261: `{"id": "tag-needs-review-id", ...}`, `{"id": "tag-reviewed-id", ...}`, `{"id": "tag-archived-id", ...}` — unchanged, still using the `-id` suffix scheme.
- All `wiki_status` select ids now match the resolved tag ids from `_make_tags_response`. No stale `"tag-needs-review"` (without `-id`) references remain in the test file for `wiki_status`.

**B1 sibling check (wiki_action ids):** `_make_wikilog` at line 215 uses `"id": f"tag-{wiki_action}"` (e.g., `"tag-ingest"`), which does NOT match `_make_tags_response`'s `"tag-ingest-id"`. This was flagged for investigation.

Conclusion: this is NOT a B1-class mismatch. The `pipeline_orphan` check retrieves WikiLog objects via a server-side `WikiClient.search` POST filter — lint never compares `wiki_action.select.id` against a resolved tag id on the client side. Lint reads `wiki_notes` content from the returned objects to detect `"relation_rollback"`. The WikiLog write path calls `_resolve_wiki_action_tag` using name-based lookup (same as `ingest.py:232`), returning the resolved id for the POST body. No test assertion checks the `wiki_action` tag id value in the WikiLog payload. The `_make_wikilog` id mismatch is harmless.

**Stub verification:** 3 of 3 B1 tests (`test_unreviewed_needs_review_fires`, `test_stale_needs_review_fires`, `test_both_needs_review_checks_fire_on_aged_object`) PASSED against a spec-faithful id-comparing stub. See Stub Run section below.

---

### B2 (BLOCKING) — silent dual try/except on semantic_search_core patches

**Status: RESOLVED**

**Evidence read:**

- `test_duplicate_sweep_fires_when_opted_in` lines 1152-1153: `import anytype_llm_wiki.indexer as _idx_mod; monkeypatch.setattr(_idx_mod, "semantic_search_core", fake_semantic_search_core)` — no try/except.
- `test_duplicate_sweep_excludes_outside_band` lines 1194-1195: same clean pattern.
- `test_duplicate_sweep_self_match_and_pair_dedup` lines 1239-1240: same.
- `test_duplicate_sweep_off_by_default` lines 1283-1285: `import anytype_llm_wiki.indexer as _idx_mod; monkeypatch.setattr(_idx_mod, "semantic_search_core", tracking_ssc); monkeypatch.setattr(_idx_mod, "_qdrant", tracking_qdrant)` — no try/except. The `_qdrant` patch on the same module is also clean.
- `test_duplicate_sweep_runs_regardless_of_threshold` lines 1352-1353: same clean pattern.
- `test_duplicate_sweep_skipped_over_object_cap` lines 1403-1404: same clean pattern.

All 6 tests now use the single authoritative `_idx_mod` patch, matching `test_query.py`'s established convention. No dual try/except blocks remain for `semantic_search_core` or `_qdrant`.

**Stub verification:** 5 of 5 B2-affected tests that assert on sweep behavior PASSED. `test_duplicate_sweep_off_by_default` and `test_duplicate_sweep_excludes_outside_band` verify the no-call/band-exclusion paths. No false-green risk remains.

---

### S1 (SHOULD-FIX) — order-sensitive GET iterator in test_pre_check_schema_newer_warns_and_continues

**Status: RESOLVED**

**Evidence read (lines 1587-1660):** The fixed test uses a URL-dispatched `get_side_effect` function with four branches:
1. `/properties` without `/tags` → `_make_properties_response()` — order-independent
2. `/properties/` with `/tags` → `_make_tags_response(prop_id)` — order-independent
3. `/objects/` with `?` in url_str → `_make_get_object_envelope(...)` — get_object
4. `/objects` without `/objects/` → counter-based: first call returns `_schema_newer_response()`, subsequent calls return `_empty_list_response()`

This is structurally identical to `_standard_mocks` and is resilient to GET call reordering. The docstring on the test explicitly calls out the URL-dispatched approach and its motivation. RESOLVED.

The `list_objects` branch at line 1633 uses `"/objects" in path and "/objects/" not in path` (omitting `"?" in url_str`). This is a minor difference from `_standard_mocks`'s three-condition check, but harmless: the `?`-in-url guard is only needed to distinguish list_objects from get_object, and that is already handled by the `"/objects/" not in path` condition. No matching edge case exists in this test.

---

### S2 (SUGGESTION) — _standard_mocks get_object detection comment

**Status: RESOLVED**

**Evidence read (lines 305-308):** Multi-line comment added explaining why `"?" in url_str` is load-bearing:
```python
# get_object: /v1/spaces/{sid}/objects/{oid}?format=md
# The "?" check is load-bearing: AnytypeReadClient.get_object always appends
# ?format=md per the wire contract, distinguishing it from list_objects which
# uses /objects (no trailing slash, no query string on the collection path).
```
RESOLVED.

---

## Stub Run Results

A spec-faithful stub was written to `/tmp/lint_stub_r2.py`, copied to `src/anytype_llm_wiki/wiki/lint.py` (no commit), with temporary lint config functions added to `config.py`. The stub uses a TWO-CALL `list_objects` design (first call for schema detection, second call for entity enumeration) matching the `_standard_mocks` counter-based fixture design. All 8 targeted tests passed:

```
tests/wiki/test_lint.py::TestNeedsReviewChecks::test_unreviewed_needs_review_fires PASSED
tests/wiki/test_lint.py::TestNeedsReviewChecks::test_stale_needs_review_fires PASSED
tests/wiki/test_lint.py::TestNeedsReviewChecks::test_both_needs_review_checks_fire_on_aged_object PASSED
tests/wiki/test_lint.py::TestDuplicateSweep::test_duplicate_sweep_fires_when_opted_in PASSED
tests/wiki/test_lint.py::TestDuplicateSweep::test_duplicate_sweep_excludes_outside_band PASSED
tests/wiki/test_lint.py::TestDuplicateSweep::test_duplicate_sweep_self_match_and_pair_dedup PASSED
tests/wiki/test_lint.py::TestDuplicateSweep::test_duplicate_sweep_off_by_default PASSED
tests/wiki/test_lint.py::TestDuplicateSweep::test_duplicate_sweep_runs_regardless_of_threshold PASSED

8 passed in 0.48s
```

The stub and config additions were deleted after the run. Git working tree is clean (`nothing to commit, working tree clean` confirmed).

---

## Regression Check: B1 fix did not break other tests

Grep of all `"tag-` id literals in the file after the fix:
- Line 139: `f"tag-{wiki_status}-id"` — `_make_entity`, aligned to `-id` scheme
- Line 175: `f"tag-{wiki_status}-id"` — `_make_concept`, aligned to `-id` scheme
- Line 215: `f"tag-{wiki_action}"` — `_make_wikilog`, no id comparison in tests, harmless
- Lines 259-263: `_make_tags_response` literals unchanged (`"tag-needs-review-id"`, etc.)

No test asserts on a `wiki_status` tag id using the old `"tag-needs-review"` scheme. No regression.

---

## Pre-impl State Verification

Post-fix run: `uv run pytest tests/wiki/test_lint.py -m 'not live' -q` → **44 failed, 2 deselected**. This is the expected pre-impl state (all tests fail due to `ModuleNotFoundError: No module named 'anytype_llm_wiki.wiki.lint'`). Confirmed.

---

## Implementation Note for impl-worker

> **⚠️ THIS ENTIRE SECTION IS SUPERSEDED — DO NOT FOLLOW.** See the banner at
> the top of this file. Use a **single** `list_objects` enumeration
> (`query.py:408` pattern), reused for both QA#25 and the check battery, per
> `spec-addendum-post-test-r1.md`. The text below describes the pre-`1c5a0df`
> fixture design and is no longer accurate.

The `_standard_mocks` fixture uses a counter-based design where the FIRST `list_objects` call returns the schema marker and the SECOND call returns wiki entities. Both responses have `has_more=False`. A spec-faithful implementation using a single paginated `list_objects` call (as `query.py` does) would receive only the schema marker in `all_objects` and never see the entity objects. The stub verification confirms that a **two-call design** (first call for schema detection via QA#25, second call for entity enumeration) satisfies ALL test fixtures. The impl-worker should adopt the two-call pattern to match the test mocks. The spec's phrase "one paginated list_objects sequence" refers to the enumeration phase logically; the QA#25 schema probe can be implemented as a separate prior call.

This is not a blocking finding — the tests are satisfiable with the two-call design and all spec ACs are met. It is recorded here so the impl-worker does not attempt a single-call design that will fail the test mocks.

---

## 1. Spec Coverage

PASSED. All 16 ACs have test coverage. The R1 CONDITIONAL/NO rows (`test_unreviewed_needs_review_fires`, `test_stale_needs_review_fires`, `test_both_needs_review_checks_fire_on_aged_object`, all duplicate sweep tests) are now SATISFIABLE. Coverage table from R1 stands with all conditional items upgraded to Y.

---

## 2. Edge Case Coverage

PASSED. Unchanged from R1 assessment. No edge cases were removed by the fixes.

---

## 3. Assertion Correctness

PASSED. B1 fix aligns ids across fixtures. All assertions verified against spec. No new wrong-value assertions introduced by the fixes.

---

## 4. Test Validity

PASSED. All 8 targeted tests now fail pre-impl (as confirmed by the 44-failed run) and PASS against a spec-faithful implementation (as confirmed by the stub run). `test_duplicate_sweep_off_by_default` no longer has false-green risk — the single authoritative `_idx_mod` patch is correctly asserted against.

---

## 5. Convention Compliance

PASSED. No changes to convention-related test structure. The S1 fix follows the `_standard_mocks` URL-dispatch pattern. The B2 fix follows the `test_query.py` patch convention.

---

## 6. Test Isolation

PASSED. The fixes do not introduce any order-dependency or shared state. `monkeypatch` is function-scoped; `respx.mock` context is test-scoped.

---

## 7. Existing Test Impact

PASSED. Unchanged from R1. All spec changes are additive; no existing tests assert behaviors removed or changed by this spec.

---

## Summary

All four R1 findings (B1, B2, S1, S2) are resolved. The B1 id-scheme fix is complete with no stale references remaining, the B1-sibling `wiki_action` question is confirmed non-issue (name-based, no client-side id comparison), and all 8 targeted tests pass against a spec-faithful stub. The implementation note about the two-call `list_objects` design is recorded as a non-blocking guidance note for the impl-worker.
