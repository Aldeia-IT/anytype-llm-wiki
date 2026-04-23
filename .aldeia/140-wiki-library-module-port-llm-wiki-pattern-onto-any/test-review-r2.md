# Test Review: wiki-library-module-port-llm-wiki-pattern-onto-any Round 2

**Verdict: APPROVED**

Branch: `test/wiki-library-module-port-llm-wiki-pattern-onto-any`
Commit reviewed: `ab25890`
Prior review: `test-review-r1.md` (commit `dfc8ae8`, verdict: NEEDS CHANGES)

## Review Date

2026-04-23

---

## R1 Finding Disposition

| Finding | Status | Evidence |
|---------|--------|----------|
| BLOCKING-B1 — AC #15 tautological QDRANT_URL test | **FIXED** | `TestBootstrapCredentialScrubbing` removed from `test_bootstrap.py`; `TestCredentialScrubbing` (10 methods) added to `test_util.py` calling `scrub_credentials` directly |
| BLOCKING-B2 — AC #11 tests gated by autouse service check | **FIXED** | `TestWikiBootstrapRegistered` removed from `test_server.py`; `tests/wiki/test_server_registration.py` created with no autouse fixture |
| SHOULD-FIX-1 — AC #3 weak OR assertion | **FIXED** | `test_missing_space_returns_config_error` now requires `[CONFIG ERROR]` only; no escape valve remains |
| SHOULD-FIX-2 — AC #13 missing schema_upgrade assertion | **FIXED** | 7 assertions added: presence, isinstance dict, `from`/`to`/`properties_added` keys, value checks against mock seed and `WIKI_SCHEMA_VERSION` |
| SHOULD-FIX-3 — Literal invisible chars in test_util.py | **FIXED** | All 10 non-ASCII dash codepoints replaced with `\uXXXX` escape sequences; byte-level scan confirms zero non-ASCII bytes in parametrize table lines |
| SHOULD-FIX-4 — check 6b absent from EXPECTED_CHECK_NAMES | **FIXED** | `"ollama_extraction_model_ram_fit"` added as entry 8; list now has 12 entries covering checks 1, 2, 3, 4, 4b, 5, 6, 6b, 7, 8, 9, 10 |

---

## Per-Finding Verification Detail

### B1 — AC #15 Credential Scrubbing

`tests/wiki/test_bootstrap.py` was searched for `TestBootstrapCredentialScrubbing` — not found (confirmed removed).

`tests/wiki/test_util.py` contains `TestCredentialScrubbing` at line 310 with 10 test methods: `test_scrub_credentials_importable`, `test_scrub_credentials_is_callable`, `test_qdrant_url_api_key_value_scrubbed`, `test_qdrant_url_api_key_query_param_scrubbed`, `test_qdrant_url_host_preserved`, `test_userinfo_password_scrubbed`, `test_userinfo_colon_password_at_combo_scrubbed`, `test_userinfo_host_preserved`, `test_plain_url_unchanged`, `test_returns_string`. All 10 call `anytype_llm_wiki.wiki.util.scrub_credentials` directly. The QDRANT_URL api_key case, userinfo case, host-preservation invariant, and return-type invariant are all separately asserted. No `wiki_bootstrap` call path is used. Non-tautological.

### B2 — AC #11 Registration Test Isolation

`tests/test_server.py` was searched for `TestWikiBootstrapRegistered` — not found. The file's module docstring was updated to explain the move. The module-level `autouse=True` `check_services` fixture remains in place for `TestSemanticSearch` and `TestReindexTool` — correct.

`tests/wiki/test_server_registration.py` exists and contains `TestWikiBootstrapRegistered` with two test methods (`test_wiki_bootstrap_is_registered_mcp_tool`, `test_existing_tools_still_registered`). The file has zero `autouse` fixture decorators (only a prose comment mentioning autouse in the module docstring). The tests import from `anytype_llm_wiki.server` and will fail with `ModuleNotFoundError: No module named 'anytype_llm_wiki.wiki'` pre-implementation (since `server.py` must import `wiki_bootstrap` to register it). They will FAIL, not SKIP.

### SF-1 — AC #3 [CONFIG ERROR] Assertion

Line 386-393 of `test_bootstrap.py`: the assertion is now:
```python
assert "[CONFIG ERROR]" in result_str, (
    f"Expected [CONFIG ERROR] in result for missing space, got: {result}"
)
```
No `or result.get("status") == "error"` disjunction present. The escape valve is gone. The assertion is inside a `if isinstance(result, dict)` guard which is fine — if `wiki_bootstrap` raises instead of returning a dict the test itself would not fail, but this pattern matches the existing `TestBootstrapUnreachable` style and was present in R1 as well (not a new weakness introduced by the fix).

### SF-2 — AC #13 schema_upgrade Section

Lines 689-715 of `test_bootstrap.py` add 7 assertions after `status == "ok"`:
1. `"schema_upgrade" in result`
2. `isinstance(upgrade, dict)`
3. `"from" in upgrade`
4. `"to" in upgrade`
5. `upgrade["from"] == "0.1.0"` (exact value matching the mock seed)
6. `upgrade["to"] == _ts.WIKI_SCHEMA_VERSION` (imported via `from anytype_llm_wiki.wiki import types_schema as _ts` immediately before the bootstrap call — correct placement inside the `respx.mock` context so the import fails pre-implementation)
7. `"properties_added" in upgrade` and `isinstance(upgrade["properties_added"], list)`

The import at line 682 is inside the test body (after the respx mock context manager is entered), so it will fail with `ModuleNotFoundError` before implementation, which is the required pre-implementation failure mode.

### SF-3 — Literal Non-ASCII Characters

Byte-level scan of all lines in `tests/wiki/test_util.py` containing both `BGE` and `M3` confirms zero non-ASCII bytes (all bytes <= 0x7F). The 10 rows (lines 42, 44, 46, 48, 50, 52, 54, 56, 58, 60) all use `\uXXXX` Python escape sequences as required by the file's docstring and CSO R3-CSO-1. The ASCII baseline row (row 1, `BGE-M3`), lowercase row (row 12), trim row (row 13), and whitespace-pad row (row 14) are unchanged ASCII-only.

### SF-4 — EXPECTED_CHECK_NAMES Count

`tests/wiki/test_doctor.py` lines 105-118: `EXPECTED_CHECK_NAMES` has 12 entries. `"ollama_extraction_model_ram_fit"` appears at line 113 as entry 8 (between `"ollama_models_pulled"` and `"wiki_lock_dir"`). The comment block at lines 99-104 explains the spec mapping and the name rationale. The `@pytest.mark.parametrize` at line 124 will generate 12 parametrized test instances.

---

## No-Regression Check

AC coverage: all 15 ACs remain covered. No test class addressing an existing AC was deleted without replacement. The fixer's net change is: 2 classes removed (replaced by stronger equivalents), 1 new file created, 2 existing tests strengthened in-place. The `test_bootstrap.py` total is 33 test methods (down from ~35 due to 2 tautological methods removed, up from replacements being added to `test_util.py`). The `TestBootstrapLiveAPI`, `TestBootstrapPatchDecisionScaffolding`, `TestBootstrapSchemaOutdatedV3Plus`, `TestBootstrapReadmePrivacyNotice`, and all other AC-covering classes are intact.

The `test_server_registration.py` tests will fail with `ModuleNotFoundError` pre-implementation (not SKIP), as required. The `test_server.py` live-service tests continue to SKIP when services are absent — unchanged behavior.

---

## New Findings

None. No new BLOCKING or SHOULD-FIX issues were introduced by the fixes. One observation for future awareness (not actionable now):

The `test_missing_space_returns_config_error` assertion is wrapped in `if isinstance(result, dict)` (line 386). If a future implementation raises an exception instead of returning a dict, the `[CONFIG ERROR]` check would be silently skipped. This is an inherited pattern from the pre-fix test (R1 did not flag it) and the test for this case was already APPROVED in R1 beyond the OR-escape-valve issue. Not a new finding.

---

## Summary

All 6 R1 findings (2 BLOCKING + 4 SHOULD-FIX) have been correctly and completely resolved in commit `ab25890`. The tautological QDRANT_URL test is replaced by a direct `scrub_credentials` unit test suite; the AC #11 tests now fail rather than skip in CI; the AC #3 assertion is strengthened; the AC #13 schema_upgrade contract is fully specified; all non-ASCII dash codepoints are in `\uXXXX` escape form; and the doctor check-6b entry is present in the parametrized list. No regressions were introduced. The test scaffolding is ready for implementation to proceed.
