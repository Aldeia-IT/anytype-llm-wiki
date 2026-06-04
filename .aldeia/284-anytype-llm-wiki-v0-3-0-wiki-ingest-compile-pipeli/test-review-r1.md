# Test Review: anytype-llm-wiki v0.3.0 wiki_ingest compile pipeline Round 1

**Verdict: NEEDS CHANGES**

## Review Date
2026-06-03

## 1. Spec Coverage

Overall coverage is good. The debrief's traceability matrix maps each AC to at least one test, and the vast majority of assertions are substantive. Two gaps are flagged below.

**AC#3 (partial failure) — assertion is tautological (BLOCKING)**

`test_partial_failure_returns_partial_status` (line 244–245, `tests/wiki/test_ingest.py`) asserts only `isinstance(result, dict)`. The comment on line 244 explicitly says "Allow partial OR ok". This assertion passes regardless of whether `status: "partial"` is returned, whether a WikiLog entry is written, or whether the response is coherent. AC#3 requires all three: `status: "partial"`, a WikiLog entry, and `objects_created`/`objects_updated`/`warnings` fields. A dict-type check is tautological and cannot gate the criterion. Severity: **BLOCKING** (the test cannot detect a regression where `status: "error"` or `status: "ok"` is returned instead of `"partial"`).

**AC#13 v0.3.0 (bidi rollback) — assertion is tautological (BLOCKING)**

`test_bidi_relation_rollback_on_failure` (line 312–313, `tests/wiki/test_ingest.py`) asserts only `isinstance(result, dict)` and includes the comment "pass if no unhandled exception". AC#13 requires: both relation directions rolled back AND WikiLog records `relation_rollback` event. A no-exception check cannot distinguish between "rollback executed and WikiLog recorded" and "no relations were attempted at all". Severity: **BLOCKING**.

**AC#14 (schema newer than code → warn and continue) — not directly tested (SHOULD-FIX)**

The debrief acknowledges this and provides rationale. Coverage via `_max_version` unit tests and `_read_schema_version` tests is partial but does not assert `wiki_schema_newer` log-level warn output. Acceptable as-is given the rationale (requires synthetic version), but flag for awareness.

**AC#18 (partial-state idempotency) — disposition noted in debrief but absent from tests (SUGGESTION)**

Debrief correctly records this as out-of-scope per spec §12. No action required.

**All other ACs (1, 2, 4–12, 15–17, 19; AC-P1 through P9; AC-M1a/M2/M3/M4/M5; AC-T1 through T5; AC-L1/L2/AC-S1/AC-S2):** each has at least one test listed in the matrix and the test bodies assert the required behavior. Detailed verification below.

---

## 2. Edge Case Coverage

**PASSED** for chunker (AC-P1 through P9): empty property value, whitespace-only, missing `space_id`/`id`, oversized value, non-wiki properties, `wiki_excerpt` exclusion, body-present dedup guard — all covered.

**PASSED** for schema-marker read: `None` when absent, non-collection "Wiki" object ignored (G4 guard), stale collection masked by newer WikiLog (SF7).

**PASSED** for fetch: private RFC-1918 ranges (`10.x`, `172.16.x`, `127.x`), Anytype port 31012, redirect-to-private-IP, DNS-rebinding, file-fetch missing file, max-bytes limit.

**PASSED** for concurrent lock: same space rejected, different space succeeds. (See §4 regarding execution failure.)

**SHOULD-FIX: `test_partial_failure_returns_partial_status` is called with a URL source (not a file) without any mock for the fetch step** (line 243). The test calls `wiki_ingest(source="https://example.com/some-content", ...)` with `respx.post().mock` but the URL `GET` would hit `respx.get().mock(return_value=httpx.Response(200, json=_make_schema_ok_response()))` — this returns a schema marker JSON object as the URL's HTTP response body. When `wiki_ingest` is implemented, `fetch_url("https://example.com/some-content")` would receive a JSON blob rather than HTML, which is not a meaningful partial-failure stimulus. The partial-failure behavior is stimulated by POST failures but the test has not adequately isolated the fetch step. This is an edge-case design issue but subordinate to the tautological assertion finding above.

---

## 3. Assertion Correctness

**BLOCKING: `test_concurrent_ingest_same_space_rejected` and `test_concurrent_ingest_different_space_succeeds` — malformed tests that error on the test itself, not on unimplemented code**

The spec (§9.6, AC#5) requires `multiprocessing.Process` with a kernel-held flock. Both tests define the child-process target as a locally-scoped function (`hold_lock`, `hold_lock_space1`) nested inside the test method. On macOS, the default multiprocessing start method is `spawn`, which uses pickle to serialize the `Process` target. Python cannot pickle locally-defined closures (functions defined inside another function). The result is:

```
AttributeError: Can't get local object 'TestConcurrentIngestLock.test_concurrent_ingest_same_space_rejected.<locals>.hold_lock'
```

This error fires at `child.start()` — it is a structural defect in the test itself, not a failure of the production code. The tests error unconditionally regardless of whether `wiki_ingest` is implemented. They cannot detect the `ingest_in_progress` behavior they are supposed to gate.

The fix is to move `hold_lock` and `hold_lock_space1` to module-level (or to a dedicated `conftest.py` helper), where `spawn`-mode pickling can reach them. The `multiprocessing` requirement itself is correct per Mem0 learning — the mechanism just needs to be picklable.

Severity: **BLOCKING** (both AC#5 tests fail with an `AttributeError` in the test infrastructure before any production code is called, meaning AC#5 has zero CI coverage until fixed).

**BLOCKING: `test_reingest_reembeds_updated_facts` (AC-P7 live test) uses a substring fallback that violates addendum item 4 (QA-ADV-2)**

The retrieval assertion at line 941:
```python
entity_found = (
    (created_id and created_id in result_ids)
    or any(ENTITY_NAME in str(n) for n in result_names)
)
```

The second branch `any(ENTITY_NAME in str(n) for n in result_names)` is a substring scan across all result names. Addendum item 4 (QA-ADV-2) explicitly prohibits "a loose name-substring match that can pass spuriously." The spec says assertions MUST use `object_id`/`name` membership (exact equality in the results list), not substring containment. The `ENTITY_NAME` string `"BGE-M3 Test Entity For Update Path"` could spuriously match any result whose `object_name` contains that substring (e.g., a different version of the entity stored in the space).

By contrast, `test_create_side_named_entity_retrieval` (AC-P2) correctly uses:
```python
entity_found = (
    (created_entity_id and created_entity_id in result_ids)
    or (created_entity_name and created_entity_name in result_names)
)
```
which uses exact membership in the `result_names` list (not substring). The AC-P7 test should match this pattern: `created_id in result_ids or ENTITY_NAME in result_names` (not `any(ENTITY_NAME in str(n) ...)`).

Severity: **BLOCKING** (direct violation of addendum item 4, which is an authoritative hard requirement).

**PASSED** for all other assertions reviewed:
- AC-S1 uses a single coherent `assert (host present AND secrets absent)` compound expression. PASSED.
- AC-P9 seam test uses a single compound check: `heading == "Facts" AND wiki_facts_text in text`. PASSED.
- AC-L2 uses separate but necessary assertions (no `type_key` filter AND no wrong-type update). PASSED.
- All `WIKI_TEXT_PROPERTY_KEYS`/`WIKI_PROPERTY_HEADING` tests use exact equality. PASSED.
- `_read_schema_version` tests use exact `==` comparison. PASSED.

---

## 4. Test Validity (will they fail now?)

**PASSED** — all non-tautological tests fail against the current codebase for the correct reason:
- Tests importing `anytype_llm_wiki.wiki.ingest`, `anytype_llm_wiki.wiki.fetch`, `anytype_llm_wiki.wiki.extraction` fail with `ModuleNotFoundError` — the modules do not exist.
- Tests importing `WIKI_TEXT_PROPERTY_KEYS`, `WIKI_PROPERTY_HEADING` from `chunker` fail with `ImportError` — these constants are not yet added.
- Tests importing `_read_schema_version` from `bootstrap` fail with `ImportError`.
- The seam tests in `test_indexer.py` fail with `ImportError` on `WIKI_TEXT_PROPERTY_KEYS`.
- B1 guard `test_wiki_schema_version_is_030` fails because `WIKI_SCHEMA_VERSION == "0.2.0"` currently.

**Note on passing tests:** The four tests noted in the debrief as currently passing (`test_non_wiki_property_not_emitted`, `test_body_present_dedup`, `test_wiki_excerpt_excluded`, `test_empty_property_not_emitted`) do correctly pass against the current chunker because the current chunker returns `[]` for empty markdown — which is the expected behavior both now and after the property-chunk extension. These are valid regression guards, not false positives.

**Exception: the two concurrent-lock tests error (not fail) on the test code itself** — see §3 finding. This makes AC#5 currently uncovered by any executable test.

---

## 5. Convention Compliance

**BLOCKING: multiprocessing local-function pickling failure (same as §3 finding)**

The concurrent-lock tests violate the platform constraint for `spawn`-mode multiprocessing. Per the spec (§9.6, AC#5), the test MUST use `multiprocessing.Process` with a kernel-held `fcntl.flock`. The mechanism is correct but the implementation is broken on macOS (and any `spawn`-start-method platform). The worker function must be at module scope to be picklable.

**PASSED** — live marker registration in `pyproject.toml`:
```toml
markers = [
    "live: marks tests as requiring live Anytype + Qdrant + Ollama services (skip with -m 'not live')",
]
```
Compliant.

**PASSED** — `@pytest.mark.live` applied to live test classes in `test_ingest.py`; skip guard via `ANYTYPE_SPACE_ID` env var inside test body. Consistent with the `test_bootstrap.py` pattern.

**PASSED** — `respx` fixtures, `_make_obj`/`_make_wiki_obj` helpers, class grouping all follow existing project conventions.

**PASSED** — `tmp_path` used for temp directories (not `/Users/` paths). No hardcoded absolute paths under `/Users/`.

**PASSED** — `tests/test_indexer.py` seam test lives at the correct location (per addendum item 1 / CTO-R2-A1) where `_qdrant`, `list_objects`, `list_spaces`, `get_object`, `embed` are monkeypatchable.

**SHOULD-FIX: `test_extraction_endpoint_scrubbed_in_startup_log` takes `caplog` as parameter but does not use it** (line 228). The test instead uses a manually constructed `io.StringIO` + `logging.StreamHandler`. The `caplog` parameter is unused, creating a confusing test signature. While this is a cosmetic issue (the test logic using `log_stream` is sound), it should be cleaned up.

---

## 6. Test Isolation

**PASSED** for all chunker, bootstrap, and extraction tests — each test is self-contained with its own `FakeClient` or `respx.mock` decorator.

**PASSED** for schema-marker tests — each `TestReadSchemaVersion` test uses an independent `FakeClient` inner class with a fixed `list_objects` return.

**PASSED** for seam tests — `test_property_only_reindex_upserts_payload` uses `tmp_path` for state file and monkeypatches all external symbols. Isolated.

**PASSED** for `test_update_path_forces_reembed` — uses `tmp_path` for state file, seeds state with `_save_state`, monkeypatches `_qdrant` and `embed`. Isolated.

**NOTE: `test_concurrent_ingest_same_space_rejected` and `test_concurrent_ingest_different_space_succeeds` cannot be assessed for isolation because they fail before exercising the lock** — see §3/§5. Once the pickling issue is fixed, both tests use `tmp_path / "locks"` for the lock directory (via `WIKI_LOCK_DIR` monkeypatch), which ensures isolation between test runs.

---

## 7. Existing Test Impact

The new tests extend `tests/test_chunker.py`, `tests/test_indexer.py`, and `tests/wiki/test_bootstrap.py`. All existing tests in these files were verified to continue passing:

- **`tests/test_chunker.py`** existing tests (`TestSplitByHeadings`, `TestSplitLarge`, `TestChunkObject`) — all pass. The new tests import `WIKI_TEXT_PROPERTY_KEYS` which does not yet exist; that `ImportError` is isolated to the new test classes and does not affect the existing class imports or the module-level import of `chunk_object`. Verified: 13 existing tests pass, 0 regressions.

- **`tests/test_indexer.py`** existing tests (`TestEnsureCollection`, `TestState`, `TestReindex`) — all pass or skip as before. The new `check_services` autouse fixture replaces the old standalone `check_services` function but the skip logic is preserved. The existing `_requires_live = True` class attribute pattern is retained. Verified: 2 existing tests pass, 5 skipped (services not reachable), 0 regressions.

- **`tests/wiki/test_bootstrap.py`** existing tests — all pass. The new v0.3.0 classes are appended after the existing classes without modifying them. Verified: existing bootstrap tests pass, 0 regressions.

**One important impact finding:** The B1 guard test `test_wiki_schema_version_is_030` is a new test that currently fails because `WIKI_SCHEMA_VERSION == "0.2.0"`. This is the expected and correct behavior — it gates the prerequisite of Decision 2. The existing `TestBootstrapSchemaOutdated.test_bootstrap_upgrade_from_v020` test (pre-existing) uses `_ts.WIKI_SCHEMA_VERSION` dynamically (line 704), so it will continue to work once the version is bumped to "0.3.0". No pre-existing test hardcodes `"0.2.0"` as the current version in a way that would fail after the bump.

---

## Summary

Three BLOCKING defects require fixes before implementation can proceed:

1. **`test_concurrent_ingest_same_space_rejected` and `test_concurrent_ingest_different_space_succeeds`** (AC#5) fail with `AttributeError` before reaching any production code due to a `spawn`-mode pickle incompatibility with locally-defined process target functions. Both AC#5 tests must be refactored to use module-level worker functions.

2. **`test_partial_failure_returns_partial_status`** (AC#3) asserts only `isinstance(result, dict)` — a tautological assertion that cannot detect wrong `status` values, missing WikiLog entries, or incoherent response shapes. Must be strengthened to assert `status == "partial"`, WikiLog creation, and the required response keys.

3. **`test_reingest_reembeds_updated_facts`** (AC-P7 live test) uses `any(ENTITY_NAME in str(n) for n in result_names)` as a fallback — a substring scan explicitly prohibited by addendum item 4 (QA-ADV-2). Must use exact membership `ENTITY_NAME in result_names`.

Additionally, `test_bidi_relation_rollback_on_failure` (AC#13) asserts only `isinstance(result, dict)` and is tautological. This is also BLOCKING as it cannot gate the rollback-and-WikiLog-log requirement.
