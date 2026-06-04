# Test Review: anytype-llm-wiki v0.3.0 wiki_ingest compile pipeline Round 2

**Verdict: APPROVED**

## Review Date
2026-06-03

## Scope of This Re-Review

This is a re-review targeting the five specific findings from R1:
- BLOCKING-1: pickling error in `TestConcurrentIngestLock` worker functions
- BLOCKING-2: tautological assertion in `test_partial_failure_returns_partial_status` (AC#3)
- BLOCKING-3: tautological assertion in `test_bidi_relation_rollback_on_failure` (AC#13)
- BLOCKING-4: substring scan in `test_reingest_reembeds_updated_facts` (AC-P7)
- SHOULD-FIX: unused `caplog` parameter in `test_extraction_endpoint_scrubbed_in_startup_log`

Items that passed R1 are not re-litigated. Regression check was also performed.

---

## BLOCKING-1: Pickling — RESOLVED

### Fix Verified

`_hold_lock_worker` was promoted to module scope in `tests/wiki/test_ingest.py` (lines 23–37).
The function:
- Accepts all state via `args=(q, space_id, lock_dir)` with no closure over test locals.
- Resolves `src/` via `os.path.abspath(__file__)` so the path computation survives `spawn`.
- Inserts `src/` into `sys.path` in the child process before importing `space_ingest_lock`.
- Is referenced by both `test_concurrent_ingest_same_space_rejected` and
  `test_concurrent_ingest_different_space_succeeds` as `target=_hold_lock_worker`.

Both tests were confirmed to **PASS** with `uv run pytest tests/wiki/test_ingest.py::TestConcurrentIngestLock -v`: 2 passed in 0.22s. No `AttributeError` or pickling failure.

### Judgment: Primitive-level coverage versus integration coverage for AC#5

AC#5 states: "Concurrent ingest against the same space is rejected with `[DATA ERROR] ingest_in_progress`; concurrent call against a different space succeeds."

The tests exercise `space_ingest_lock` directly, not `wiki_ingest`. The fixer correctly identifies that `space_ingest_lock` is already implemented in `src/anytype_llm_wiki/wiki/util.py` (lines 116–180) — it is not missing production code. The implementation raises `RuntimeError("[DATA ERROR] ingest_in_progress: ...")` on `fcntl.LOCK_EX | LOCK_NB` failure, and the test asserts exactly that message pattern.

**Is primitive-level coverage adequate?**

The spec (§9.6, line 1033–1036) states the test requirement specifically: "The concurrent-ingest test MUST use `multiprocessing.Process` to acquire the flock in a second process." It does not require testing `wiki_ingest` as the outer wrapper — it requires exercising the kernel-held flock mechanism. The primitive `space_ingest_lock` IS the mechanism. Testing it directly with `multiprocessing.Process` satisfies the intent: confirming the flock is kernel-held and not thread-bypassable.

An integration test that also exercises `wiki_ingest → space_ingest_lock` would be higher-fidelity, but the spec does not require it and the primitive test catches the core behavior: `[DATA ERROR] ingest_in_progress` on same-space concurrent acquire, no interference on different-space acquire. When `wiki_ingest` is implemented, it will call `space_ingest_lock` — if it fails to do so, the integration tests for AC#1 (create side) and AC#2 (idempotence) would surface that gap rather than the lock test.

**Finding: PASSED.** Primitive-level lock tests are adequate coverage for AC#5 given the already-implemented `space_ingest_lock`. The BLOCKING pickling defect is genuinely resolved.

---

## BLOCKING-2: AC#3 Tautological Assertion — RESOLVED

### Fix Verified

`test_partial_failure_returns_partial_status` was fully rewritten. The new test:

1. Writes a temp markdown file with two distinct entity sections (`# Entity Alpha`, `# Entity Beta`) via `tmp_path` — avoids the R1 edge-case finding about URL-source receiving schema-marker JSON.
2. Mocks POSTs: WikiLog creates (`type_key == "wiki_log"`) set `wikilog_created["yes"] = True`; first entity create (wiki type key) returns 201; second returns 500 (partial failure stimulus).
3. Asserts:
   - `result.get("status") == "partial"` — not `isinstance(result, dict)`.
   - `"objects_created" in result`
   - `"objects_updated" in result`
   - `"warnings" in result`
   - `wikilog_created["yes"]` is True — WikiLog entry created.

All four R1-required assertions are present and substantive. The test fails for the correct reason: `ModuleNotFoundError: No module named 'anytype_llm_wiki.wiki.ingest'` (confirmed with `uv run pytest tests/wiki/test_ingest.py::TestPartialFailure -v`).

**Finding: PASSED.**

---

## BLOCKING-3: AC#13 Tautological Assertion — RESOLVED

### Fix Verified

`test_bidi_relation_rollback_on_failure` was fully rewritten. The new test:

1. Writes a temp markdown file with two entity sections containing relation language.
2. Routes mock POSTs by `type_key`/URL path:
   - `type_key == "wiki_log"` → captures payload in `wikilog_payloads`.
   - `"relation" in path.lower() or type_key in ("relation", "wiki_relation")` → first call returns `{"id": "relation-dir1-001"}`; second returns 500 (rollback trigger).
   - All other objects → 201.
3. Mocks DELETE: appends URL to `rollback_calls`.
4. Mocks PATCH: appends URL to `rollback_calls` if `relation-dir1-001` in URL or payload.
5. Asserts:
   - `isinstance(result, dict)` (basic sanity — not the sole assertion).
   - `any(relation_dir1_id in call for call in rollback_calls)` — first-direction relation was rolled back via DELETE or PATCH-unset.
   - `any("relation_rollback" in _json.dumps(payload) for payload in wikilog_payloads)` — WikiLog records the rollback event.

Both rollback-direction assertions are present. The WikiLog scan uses `json.dumps(payload)` which covers the string anywhere in the serialized payload — appropriate given the implementation may embed it as a property key, value, or notes field. The test fails for the correct reason: `ModuleNotFoundError` (confirmed with `uv run pytest tests/wiki/test_ingest.py::TestBidirectionalRelationRollback -v`).

**Finding: PASSED.**

---

## BLOCKING-4: AC-P7 Substring Scan — RESOLVED

### Fix Verified

The assertion in `test_reingest_reembeds_updated_facts` was changed from:

```python
or any(ENTITY_NAME in str(n) for n in result_names)
```

to:

```python
or ENTITY_NAME in result_names
```

This is exact list membership (Python `in` operator on a list tests equality, not substring containment). Both branches of the `or` expression are now exact membership checks:
- `(created_id and created_id in result_ids)` — exact id membership in a list of ids.
- `ENTITY_NAME in result_names` — exact name equality membership in a list of names.

The assertion message was updated to note "exact id/name membership (QA-ADV-2)". This matches the pattern used by `test_create_side_named_entity_retrieval` (AC-P2).

**Finding: PASSED.** QA-ADV-2 violation is genuinely resolved, not cosmetically.

---

## SHOULD-FIX: Unused `caplog` in `test_extraction_endpoint_scrubbed_in_startup_log` — RESOLVED

### Fix Verified

The method signature was changed from:

```python
def test_extraction_endpoint_scrubbed_in_startup_log(self, monkeypatch, caplog):
```

to:

```python
def test_extraction_endpoint_scrubbed_in_startup_log(self, monkeypatch):
```

The test body continues to use a manual `io.StringIO` + `logging.StreamHandler` approach. The single coherent AC-S1 assertion (host present AND `KEY`/`SEKRET`/`user:KEY@`/`user:` absent) is unchanged. The test fails for the correct reason: `ModuleNotFoundError: No module named 'anytype_llm_wiki.wiki.extraction'`.

**Finding: PASSED.**

---

## Regression Check

`uv run pytest tests/ -q` result: **81 failed, 279 passed, 22 skipped, 3 xfailed**.

- The 279 passing count includes the 2 concurrent-lock tests that were erroring in R1. The 277 previously-passing tests all continue to pass — 0 regressions introduced by the fix.
- All 81 failures are `ModuleNotFoundError` (missing `ingest.py`, `fetch.py`, `extraction.py`), `ImportError` (constants not yet added to `chunker.py`), or assertion failures against unimplemented behavior (e.g., `chunk_object` does not yet produce property chunks). No failures stem from malformed test code.

**Finding: PASSED.** No regressions.

---

## Previously-Passing Items (No Regression)

Items that passed R1 were not re-litigated. Spot checks confirm no regression:
- Spec Coverage (items 1, 2, 4–12, 15–17, 19; AC-P1/P2/P3–P6/P8/P9; AC-M/T/L/S series): unchanged.
- Edge Case Coverage (chunker, schema-marker, fetch): unchanged.
- Test Isolation: all tests remain independently runnable with `tmp_path` isolation.
- Convention Compliance: `@pytest.mark.live` marker usage, `respx` fixtures, no hardcoded user paths — unchanged.
- Existing Test Impact: no pre-existing tests broken.

---

## Summary

All five R1 findings (BLOCKING-1 through BLOCKING-4, SHOULD-FIX) are genuinely resolved. The fix is substantive in each case: worker functions are now module-level and both lock tests pass; AC#3 and AC#13 tests now assert the specific required behaviors rather than mere `isinstance(dict)` checks; AC-P7 uses exact list membership per QA-ADV-2; `caplog` unused parameter is removed. The previously-passing 277 tests continue to pass, and the 81 failing tests all fail for the correct reason (unimplemented production modules). No BLOCKING or SHOULD-FIX findings remain.
