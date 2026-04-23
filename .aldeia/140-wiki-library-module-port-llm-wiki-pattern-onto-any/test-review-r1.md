# Test Review: wiki-library-module-port-llm-wiki-pattern-onto-any Round 1

**Verdict: NEEDS CHANGES**

Branch: `test/wiki-library-module-port-llm-wiki-pattern-onto-any`
Commit reviewed: `dfc8ae8`
AC coverage: 15/15 ACs have at least one test function named in the matrix; 2 of those tests have structural defects that make them invalid as spec gates.

## Review Date

2026-04-23

---

## 1. Spec Coverage

Coverage is present for all 15 ACs. The traceability matrix accounts for every criterion and identifies the xfail strategy for ACs #13 and #14 (v0.3.0+ modules) correctly.

**Partial gap — AC #15 (QDRANT_URL case):** The test `TestBootstrapCredentialScrubbing::test_qdrant_url_api_key_not_in_error_string` is mapped to AC #15 but is tautological (see item 3 below). Coverage of the QDRANT_URL branch of AC #15 is therefore not effective.

**Partial gap — AC #13 bootstrap exception:** The two tests in `TestBootstrapSchemaOutdated` assert `status='ok'` and that `wiki_schema_outdated` is absent, but do not assert the `schema_upgrade` section that the spec (line 1604) requires in the result. The exception path is partially covered; the positive output contract is untested.

All other ACs are covered with substantive test implementations.

---

## 2. Edge Case Coverage

PASSED with the following observations:

- `normalize_title` edge cases are well covered: empty string, whitespace-only, whitespace-collapse, NFC normalization, non-dash punctuation preservation.
- `space_ingest_lock` covers: directory creation, file modes (0o700 / 0o600), JSON payload keys, PID correctness, source_ref redaction (query-string and userinfo), sequential reacquisition, cross-space concurrency, and the multiprocessing concurrent-acquisition case.
- Bootstrap error paths cover: missing space (404), unreachable Anytype (ConnectError), 403 on type creation, Anytype 500 for credential scrubbing path.
- Doctor edge cases cover: missing API key, unreachable Anytype, non-empty WIKI_FETCH_EXTRA_PORTS, low-RAM + 7B model.

No significant missing edge cases identified that were not already delegated to later versions.

---

## 3. Assertion Correctness

### BLOCKING-B1: AC #15 QDRANT_URL test is tautological

**File:** `tests/wiki/test_bootstrap.py::TestBootstrapCredentialScrubbing::test_qdrant_url_api_key_not_in_error_string`

**Problem:** The test sets `QDRANT_URL=https://xyz.cloud.qdrant.io/collections/x?api_key=SEKRET123`, forces a 500 from Anytype (not from Qdrant), and then asserts `SEKRET123` and `?api_key=` are absent from the error string. Because `wiki_bootstrap` does not call Qdrant at all — bootstrap only talks to Anytype — the QDRANT_URL value will never appear in any bootstrap error string regardless of whether credential scrubbing is implemented. The assertion will pass on an implementation that performs zero scrubbing.

**Spec requirement (line 745):** "A forced `[API ERROR]` triggered by a Qdrant failure where `QDRANT_URL=...?api_key=SEKRET123` returns an error string containing neither SEKRET123 nor the raw `?api_key=...` query string." The spec means the error must arise FROM a Qdrant failure, not from an Anytype failure with QDRANT_URL set in the environment.

**Correct fix:** The test must trigger a code path that actually reads and potentially echoes QDRANT_URL — either by importing the `scrub_credentials` utility directly and asserting it scrubs the URL, or by finding a bootstrap code path that includes QDRANT_URL in an error context. Alternatively, import `anytype_llm_wiki.wiki.util.scrub_credentials` directly and assert that `scrub_credentials("https://xyz.cloud.qdrant.io/collections/x?api_key=SEKRET123")` returns a string containing neither `SEKRET123` nor `?api_key=`. The debrief says "Tests import `anytype_llm_wiki.wiki.util.scrub_credentials`" — the test does not do this; it calls `wiki_bootstrap` instead.

**Severity:** BLOCKING — the test will pass on unimplemented or incorrectly implemented scrubbing.

---

### BLOCKING-B2: AC #11 tests gated by module-level `autouse=True` service check

**File:** `tests/test_server.py::TestWikiBootstrapRegistered::test_wiki_bootstrap_is_registered_mcp_tool` and `test_existing_tools_still_registered`

**Problem:** The `check_services` fixture at line 29–32 of `test_server.py` is decorated `@pytest.fixture(autouse=True)` at module scope. In pytest, a module-scope autouse fixture applies to every test in that module, including those in classes defined after the fixture. `TestWikiBootstrapRegistered` is therefore implicitly gated by `check_services`: when Ollama and Qdrant are unreachable (the normal pre-implementation CI state), both tests are SKIPPED rather than FAILED.

The test writer's comment at line 97 says "This test does NOT use the check_services fixture" — this is factually incorrect for autouse fixtures and will mislead the implementer.

**Impact:** In CI (where services are absent), AC #11 has zero failing tests and the gate is entirely absent. The test will not fail when `wiki_bootstrap` is missing from `server.py`. This makes `TestWikiBootstrapRegistered` useless as a spec gate.

**Correct fix:** Move `TestWikiBootstrapRegistered` to a separate file (e.g. `tests/wiki/test_bootstrap_registration.py`) that does not share a module with the `autouse=True` service check, or change the fixture to non-autouse and have only the live-service test classes opt in via a class-level autouse wrapper (the pattern already used for `TestListSpaces`/`TestListObjects`/`TestGetObject`). The `test_anytype_client.py` file applied this exact pattern (module-level fixture refactored to class-level autouse wrapper) as noted in the debrief. The same fix was not applied to `test_server.py`.

**Severity:** BLOCKING — AC #11 will not produce a failing test in CI before implementation.

---

### Assertion correctness (non-BLOCKING)

**AC #3 / AC #4 weak OR assertions:** `TestBootstrapMissingSpace::test_missing_space_returns_config_error` asserts `"[CONFIG ERROR]" in result_str or result.get("status") == "error"`. The disjunction allows an implementation that returns `status: "error"` without the `[CONFIG ERROR]` string to pass this test. The spec (line 733) requires `[CONFIG ERROR]` explicitly. This is a SHOULD-FIX (see section below); the `status == "error"` fallback branch is an unnecessary escape valve.

**AC #13 schema_upgrade section absent:** `TestBootstrapSchemaOutdated::test_bootstrap_on_outdated_schema_returns_ok` asserts `result.get("status") == "ok"` but does not assert the `schema_upgrade` section. Spec line 1604 says bootstrap on an outdated schema "Returns `BootstrapResult` with `status: 'ok'` and a `schema_upgrade` section listing the properties added." The positive output contract is incomplete. SHOULD-FIX.

All other assertions reviewed are correctly formed and match the spec's expected outputs.

---

## 4. Test Validity (will they fail now?)

Confirmed: the debrief reports `193 failed, 6 passed, 6 skipped, 3 xfailed` and all 193 failures are `ModuleNotFoundError: No module named 'anytype_llm_wiki.wiki'` or `ImportError: cannot import name 'AnytypeReadClient'`. This is the correct failure mode.

**Exception — BLOCKING-B2:** `TestWikiBootstrapRegistered` does not appear in the 193 failing count because it is being SKIPPED by the `autouse` service check. It will not fail before implementation.

**Exception — BLOCKING-B1:** `TestBootstrapCredentialScrubbing::test_qdrant_url_api_key_not_in_error_string` will currently fail with `ModuleNotFoundError` (correct), but after implementation it will not catch a scrubbing defect for the QDRANT_URL path. The test validity issue is post-implementation, not pre-implementation.

The xfail strategy for AC #13/AC #14 is appropriate: `strict=False` means the tests are registered without blocking the v0.2.0 CI run.

---

## 5. Convention Compliance

This is a Python/pytest project. Conventions verified:

- `respx` used throughout for Anytype HTTP mocking. No live network calls in unit tests except in explicitly skip-gated live classes.
- `monkeypatch` used for env-var injection in all test functions requiring credentials.
- `tmp_path` used for all temp directories — no hardcoded `/Users/` paths in test files.
- `pytest.skip` with clear reason strings used for all live-API gating.
- `multiprocessing.Process` used for the `space_ingest_lock` concurrency test per spec Test Plan line 1913. Correct.
- `@pytest.mark.timeout(150)` on the AC #6 timing test per spec.
- `@pytest.mark.xfail(strict=False)` on AC #13 / AC #14 deferred tests. Correct.
- `tests/wiki/__init__.py` present. Mirror layout per spec line 1454 is satisfied for v0.2.0 scope.

**Violation — literal invisible chars in test_util.py (CSO R3-CSO-1):**

The file's own docstring at line 5 states "Uses `\\uXXXX` escape form (not literal invisible characters) per CSO R3-CSO-1." The actual parametrize string literals at lines 42–60 use literal characters (e.g. `\xad` SOFT HYPHEN, `‐` U+2010, etc.) not `\uXXXX` Python escape sequences. Representative lines:

```
("BGE\xadM3", True),    # line 42 — literal SOFT HYPHEN, not "­"
("BGE‐M3", True),       # line 44 — literal U+2010, not "‐"
```

The stated intent in the docstring and CSO R3-CSO-1 require `\uXXXX` form for diff-visibility and editor round-trip safety. The tests will function correctly at runtime but violate the stated convention. SHOULD-FIX.

---

## 6. Test Isolation

Each test class uses `monkeypatch` to set env vars in its scope and `tmp_path` for lock directories. No test depends on prior test execution order. The `autouse` env-var fixtures in `test_bootstrap.py`, `test_base_client.py`, `test_wiki_client.py`, and `test_doctor.py` are properly scoped and do not create shared mutable state.

The concurrent lock test (`TestSpaceIngestLockConcurrency`) uses `multiprocessing.Process` + `multiprocessing.Queue` for synchronization, avoiding shared in-process state. The `time.sleep(0.3)` hold for the child to acquire the lock is a potential flakiness source on heavily loaded CI runners, but this is a known limitation of the test mechanism and is an acceptable trade-off against testing a real `fcntl.flock` acquisition.

The `TestBootstrapLiveAPI` class gates on both `ANYTYPE_API_KEY` and `ANYTYPE_SPACE_ID` being set in the environment. No isolation issue.

PASSED.

---

## 7. Existing Test Impact

The test-writer correctly refactored `test_anytype_client.py` to change the `check_anytype` fixture from module-level `autouse=True` to a non-autouse fixture requested by each live-test class via a class-level autouse wrapper. This prevents the v0.2.0 mock-based tests from being skipped when Anytype is unreachable.

**One existing test class with a structural issue that must be addressed:**

The v0.1.0 `TestSemanticSearch`, `TestReindexTool` classes in `tests/test_server.py` continue to rely on the module-level `autouse=True` `check_services` fixture — this is unchanged from v0.1.0 and will remain correct for those classes. The problem is that `TestWikiBootstrapRegistered` was added to the same file without being isolated from this autouse fixture.

No other v0.1.0 test files are affected by the v0.2.0 changes. `tests/test_indexer.py`, `tests/test_chunker.py`, `tests/test_embedder.py` do not reference any functions being changed by this spec.

The `from anytype_llm_wiki.anytype_client import list_spaces, list_objects, get_object` import at line 21 of `tests/test_anytype_client.py` will currently fail with `ImportError` once `AnytypeReadClient` is introduced and the module-level wrapper functions are removed or renamed. The test-writer's regression-test approach in `TestImportRegressionIndexer` correctly covers this; the top-level module import at line 21 will continue to work if the wrapper functions are preserved per the spec.

---

## Summary

Two BLOCKING defects require fixes before implementation may proceed. First, `TestWikiBootstrapRegistered` (AC #11) will be silently SKIPPED rather than FAILED in standard CI because a module-level `autouse=True` service-check fixture in `test_server.py` gates the entire module; the test must be moved out of that module. Second, `test_qdrant_url_api_key_not_in_error_string` (AC #15) is tautological: `wiki_bootstrap` never reads `QDRANT_URL`, so the assertion that `SEKRET123` is absent from the error string will pass on any implementation regardless of whether scrubbing is implemented; the test must be rewritten to actually exercise the `scrub_credentials` function. Three SHOULD-FIX issues are present: the AC #3 `[CONFIG ERROR]` OR-assertion escape valve, the missing `schema_upgrade` section assertion in the AC #13 bootstrap exception test, the literal invisible characters in the dash-fold parametrize table (contrary to the file's own docstring), and the missing `ollama_ram_warn` / check-6b entry in `EXPECTED_CHECK_NAMES`. None of the SHOULD-FIX items prevent implementation from starting but must be resolved before the v0.2.0 tag.

---

## Per-AC Coverage Table

| AC # | Test file::class::function | Assertion quality |
|------|---------------------------|------------------|
| #1 | `test_bootstrap.py::TestBootstrapCreatesTypesAndProperties::test_creates_six_types`, `test_types_created_have_canonical_keys`, `test_creates_root_collection`, `test_creates_default_domain_tags`, `test_deeplinks_in_types_created` | GOOD — asserts count, canonical keys, collection ID, deeplinks |
| #2 | `test_bootstrap.py::TestBootstrapIdempotency::test_second_call_populates_types_skipped`, `test_second_call_skipped_entries_have_already_exists_reason`, `test_second_call_creates_no_duplicate_types` | GOOD |
| #3 | `test_bootstrap.py::TestBootstrapMissingSpace::test_missing_space_returns_config_error`, `test_missing_space_echoes_space_id` | SHOULD-FIX — first test uses OR assertion allowing `status=="error"` without `[CONFIG ERROR]` string |
| #4 | `test_bootstrap.py::TestBootstrapUnreachable::test_unreachable_anytype_returns_api_error` | GOOD |
| #5 | `test_bootstrap.py::TestBootstrapCustomDomainTags::test_custom_domain_tags_on_first_bootstrap`, `test_rebootstrap_with_new_tags_is_union_only` | GOOD — union semantic correctly tested: seeds ["a","b"] via mock GET, re-bootstraps with ["c"], asserts a/b in skipped and c in created |
| #6 | `test_bootstrap.py::TestBootstrapTiming::test_bootstrap_completes_within_timing_budget` | GOOD — `@pytest.mark.timeout(150)` enforces 5x budget |
| #7 | `test_verify_script.py::TestScriptExists`, `TestScriptExecutableBit`, `TestScriptShebang`, `TestScriptSyntax`, `TestScriptTrapBeforeProbe`, `TestScriptConditionalGuards`, `TestScriptStderrDiagnostics`, `TestScriptNoANYTYPE_OBJECT_ID` | GOOD — trap-before-probe line ordering, conditional guards, stderr routing, ANYTYPE_OBJECT_ID absence all asserted |
| #8 | `test_bootstrap.py::TestBootstrapReadmePrivacyNotice::test_readme_contains_privacy_notice`, `test_readme_contains_privacy_section_header`, `test_readme_contains_localhost_data_flow_statement`, `test_readme_contains_gdpr_controller_statement` | GOOD — static file checks; will fail until README updated |
| #9 | `test_bootstrap.py::TestBootstrapInsufficientTokenScope::test_403_on_create_type_returns_config_error`, `test_insufficient_scope_error_mentions_settings_api` | GOOD — mocks 403 on types endpoint, asserts `insufficient_token_scope` and "Settings" + "API" present |
| #10 | `test_doctor.py::TestDoctorImport`, `TestDoctorReturnShape`, `TestDoctorChecksPresent` (11 checks parametrized), `TestDoctorExitCodes`, `TestDoctorRamWarn` | SHOULD-FIX — check 6b (RAM WARN) tested in TestDoctorRamWarn but not present in EXPECTED_CHECK_NAMES parametrized list; the parametrized assertion will not enforce a named check entry for it |
| #11 | `tests/test_server.py::TestWikiBootstrapRegistered::test_wiki_bootstrap_is_registered_mcp_tool`, `test_existing_tools_still_registered` | BLOCKING — both tests will be SKIPPED in CI due to module-level autouse service-check fixture |
| #12 | `tests/test_anytype_client.py::TestAnytypeReadClientImport`, `TestAnytypeReadClientClassPath`, `TestModuleWrapperPath`, `TestImportRegressionIndexer`, `TestBaseClientInheritance`; `tests/wiki/test_base_client.py::TestBaseClientImport`, `TestBaseClientTransportContract`, `TestBaseClientHasNoReadOrWriteMethods`, `TestInheritanceHierarchy` | GOOD — all three paths (class, wrapper, indexer import) covered; inheritance chain asserted |
| #13 | `test_bootstrap.py::TestBootstrapSchemaOutdated::test_bootstrap_on_outdated_schema_returns_ok`, `test_bootstrap_on_outdated_schema_does_not_raise_schema_outdated_error`; `TestBootstrapSchemaOutdatedV3Plus` (xfail) | SHOULD-FIX — bootstrap exception (not returning schema_outdated error) correctly tested; `schema_upgrade` section in result not asserted |
| #14 | `test_bootstrap.py::TestBootstrapPatchDecisionScaffolding::test_read_patch_decision_function_exists`, `test_read_patch_decision_is_callable`; `test_wiki_ingest_returns_error_on_missing_patch_decision` (xfail) | GOOD — scaffolding assertions correct; activation gated on v0.3.0 |
| #15 | `test_bootstrap.py::TestBootstrapCredentialScrubbing::test_qdrant_url_api_key_not_in_error_string`, `test_wiki_extract_endpoint_userinfo_not_in_error_string` | BLOCKING (QDRANT_URL test) — QDRANT_URL test is tautological (bootstrap never reads QDRANT_URL); WIKI_EXTRACT_ENDPOINT test is acceptable (bootstrap may reference WIKI_EXTRACT_ENDPOINT in its error context) |
