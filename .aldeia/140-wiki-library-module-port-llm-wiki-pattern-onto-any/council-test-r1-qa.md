# Council Test Review R1 — QA Director (Independent)

**Ticket:** #140 — Wiki Library Module: Port LLM Wiki Pattern onto Anytype
**Phase reviewed:** test (v0.2.0 failing-test scaffolding)
**Branch:** `test/wiki-library-module-port-llm-wiki-pattern-onto-any`
**Final commit under review:** `8f94d09` (post-R2 APPROVED, r1-fixer applied at `ab25890`)
**Review rounds (test phase):** 2 (R1 NEEDS CHANGES → fixer → R2 APPROVED)
**Reviewer:** QA Director, council-test-r1
**Date:** 2026-04-23

---

## Verdict

**SIGN OFF — advance to `impl`.**

0 BLOCKING, 3 ADVISORY (two for v0.2.0 impl-opening, one carried-forward v0.3.0 test-phase lead).

The test phase delivered what a post-test QA gate exists to verify: a substantive, spec-traceable failing-test scaffold that will produce a clean pre-implementation failure signal, and whose previously-caught "looks-right-but-doesn't-assert" defects have been independently re-verified as resolved. The R1→R2 cycle is textbook — two real BLOCKING defects of the class that routinely slip past self-review were caught by the test reviewer and correctly fixed. I do not find additional BLOCKING issues on my independent pass.

---

## Summary

The test scaffolding covers all 15 v0.2.0 acceptance criteria with at least one substantive test. The two R1 defects were precisely the class of defect that most threatens a failing-test phase's credibility: **tests that look like they exercise an AC but do not produce a pre-implementation failure, or pass against an unimplemented surface.** Specifically:

- **AC #15 QDRANT_URL scrubbing** (R1 BLOCKING-B1): R1 test forced a 500 from Anytype and asserted `QDRANT_URL` content absent from the error string — but `wiki_bootstrap` never reads `QDRANT_URL`, so the assertion was a tautology. Fixed by moving to a direct `scrub_credentials` unit test suite in `tests/wiki/test_util.py` that exercises the scrubber function itself. Verified independently: 10 test methods, direct import, host-preservation invariant asserted as a positive control.
- **AC #11 MCP registration** (R1 BLOCKING-B2): R1 test was in `tests/test_server.py` where a module-level `autouse=True` `check_services` fixture gates every test in the module on live Ollama/Qdrant — meaning CI (no live services) would silently SKIP the registration test rather than FAIL it. Fixed by moving the registration tests to `tests/wiki/test_server_registration.py`, a new file with zero autouse fixtures. Verified independently: I read the file end-to-end; there are no fixture decorators, only the two registration test methods, which will fail with `ModuleNotFoundError` pre-implementation.

The four SHOULD-FIX items were also fully resolved (AC #3 OR-escape valve removed; AC #13 `schema_upgrade` section contract fully asserted; non-ASCII dash codepoints converted to `\uXXXX` escapes per CSO R3-CSO-1; doctor check-6b added to `EXPECTED_CHECK_NAMES`).

Jan's ticket-feedback spirit ("fix the advisories as well") was applied: R1 did not produce any BLOCKING+defer combinations. The only items deferred from this review are the three prior-spec-council QA SHOULD-FIX items that legitimately belong to v0.3.0+/v0.5.0 scope — that's discipline, not laziness.

---

## AC Coverage Sanity-Check (spot-checked independently)

Rather than restate the 15-row coverage table from `test-review-r1.md §Per-AC Coverage Table`, I spot-checked three ACs at the file level to ensure the R2 verdict's claims hold under re-inspection.

### Spot-check 1 — AC #5 (custom `domain_tags` union-only re-bootstrap)

**Spec line 735** mandates a dedicated test that bootstraps with `["a", "b"]`, re-bootstraps with `["c"]`, and asserts the space ends up with `["a", "b", "c"]`.

**Test:** `tests/wiki/test_bootstrap.py::TestBootstrapCustomDomainTags::test_rebootstrap_with_new_tags_is_union_only` (line 466).

The test seeds the existing tags `a` and `b` via a mock GET response keyed on `"options" in url_str or "tags" in url_str`, invokes `wiki_bootstrap(domain_tags=["c"])`, and asserts: `a` in `tags_skipped`, `b` in `tags_skipped`, `c` in `tags_created`. This is exactly the union-only invariant and the assertions match the spec's prose literally. The first-call `test_custom_domain_tags_on_first_bootstrap` (line 439) asserts the inverse — that default tags do NOT appear when custom `domain_tags` is provided. Both halves of AC #5 are present and substantive.

### Spot-check 2 — AC #13 (schema `_outdated` with bootstrap exception)

**Spec line 1604** requires that bootstrap on an outdated schema returns `BootstrapResult` with `status: "ok"` **and** a `schema_upgrade` section listing the properties added.

**Test:** `tests/wiki/test_bootstrap.py::TestBootstrapSchemaOutdated::test_bootstrap_on_outdated_schema_returns_ok` (line 689 onward).

The test asserts seven properties in sequence:
1. `status == "ok"`
2. `"schema_upgrade" in result`
3. `isinstance(schema_upgrade, dict)`
4. `"from" in schema_upgrade`
5. `"to" in schema_upgrade`
6. `schema_upgrade["from"] == "0.1.0"` (matching the mock seed)
7. `schema_upgrade["to"] == WIKI_SCHEMA_VERSION` (imported from `anytype_llm_wiki.wiki.types_schema` — this import is inside the test body and will fail pre-implementation with `ModuleNotFoundError`, which is the required pre-impl failure mode)
8. `"properties_added"` present and is a list

A companion test (`test_bootstrap_on_outdated_schema_does_not_raise_schema_outdated_error`, line 718) asserts the bootstrap-specific exception to the `_outdated` rule — that `wiki_bootstrap` specifically must NOT raise `wiki_schema_outdated` (unlike the other wiki tools, which do). This matches spec line 1607 where bootstrap is named as the remediation tool.

The R1 SHOULD-FIX-2 complaint was that the `schema_upgrade` positive output contract was untested. It is now fully tested. The only post-impl follow-up is the observation in the test-writer debrief (and the phase summary) that the exact key names (`from`, `to`, `properties_added`) are inferred rather than spec-dictated — but the implementer can read the test and match those names, and if they choose different names the test will fail loudly, which is the correct failure mode. **Caveat (ADVISORY-A1 below):** the spec prose at line 1601 uses the key names `from` and `to` informally; worth tightening if we want zero implementer-side key-naming guesswork.

### Spot-check 3 — AC #15 (credential scrubbing, post-fix)

**Spec line 745** requires two distinct scrubbing cases — QDRANT_URL with `?api_key=SEKRET123`, and `WIKI_EXTRACT_ENDPOINT` with `api-user:api-secret@...` userinfo — each asserting the raw secret is absent from the error string.

**Tests:** `tests/wiki/test_util.py::TestCredentialScrubbing` (line 310).

Ten methods, all calling `anytype_llm_wiki.wiki.util.scrub_credentials` directly (no `wiki_bootstrap` call path):
- `test_qdrant_url_api_key_value_scrubbed`: asserts `SEKRET123` absent from the scrubbed result.
- `test_qdrant_url_api_key_query_param_scrubbed`: asserts `?api_key=` substring absent.
- `test_qdrant_url_host_preserved`: POSITIVE CONTROL — asserts `xyz.cloud.qdrant.io` is still present. This is important: without it, a broken implementation that returns the empty string for any credentialed URL would silently pass the two negative assertions. The positive control catches that.
- `test_userinfo_password_scrubbed`, `test_userinfo_colon_password_at_combo_scrubbed`, `test_userinfo_host_preserved`: the three-way slice on the userinfo case, with analogous positive control.
- `test_plain_url_unchanged`: invariant on URLs with no credentials.
- `test_returns_string`: return-type invariant.

The fix is strictly stronger than what R1 was asking for. The original R1 complaint was "the assertion will pass on an unimplemented scrubber" — the new test suite gates directly on the scrubber's behavior, with both positive and negative assertions on both the QDRANT_URL and userinfo cases. I would not have asked for anything more at this stage.

---

## xfail Strategy for AC #13/#14 (v0.3.0 activation)

**Scope:** 3 xfailed tests total —
- `TestBootstrapSchemaOutdatedV3Plus::test_wiki_ingest_raises_schema_outdated` (AC #13, v0.3.0 activation)
- `TestBootstrapSchemaOutdatedV3Plus::test_wiki_query_raises_schema_outdated` (AC #13, v0.4.0 activation)
- `TestBootstrapPatchDecisionScaffolding::test_wiki_ingest_returns_error_on_missing_patch_decision` (AC #14, v0.3.0 activation)

**Verification of `strict=False`:** All three use `@pytest.mark.xfail(reason="...", strict=False)` (confirmed by reading lines 753–755, 774–776, 813–815 of `test_bootstrap.py`).

**Assessment of the strict=False choice:** This is the correct setting for this specific transitional case.
- With `strict=True`, the test would be required to fail currently. If the v0.3.0 `wiki_ingest` module later lands and this test starts passing without its marker being removed, `strict=True` would produce an XPASS-as-failure — a signal that the marker needs to be removed.
- With `strict=False`, the test may either xfail or xpass freely. The v0.3.0 test lead must **actively audit** the xfail list to flip them.

The phase-summary Risks section item 1 acknowledges this: "When v0.3.0 test-writing begins, the 3 xfail tests ... need to flip from xfail to real assertions. The v0.3.0 test lead must audit them explicitly." This is a reasonable process commitment. The `strict=False` choice favors lenience at v0.3.0 module landing (implementation can proceed without failing on an orphaned xfail marker) at the cost of requiring an explicit audit step at v0.3.0 test-writing.

**My recommendation:** This is a defensible trade-off. **Would it be stronger to use `strict=True`?** Arguably yes — it turns xfail-audit from a process commitment into an automatic CI signal. However, changing it now would be out of scope for this review (R2 already approved `strict=False` and the council charter is not to re-litigate reviewed decisions). I log this as **ADVISORY-A2** for the v0.3.0 test-phase lead to consider a `strict=True` flip at that time.

---

## Prior-spec-council SHOULD-FIX Disposition

Three QA SHOULD-FIX items were carried forward from `council-spec-r3.md` (R3 QA Director assessment and council Findings §QA):

| ID | Item | Scope | Test lead's disposition | My assessment |
|----|------|-------|-------------------------|---------------|
| QA-SF-1 | Lock AC v0.3.0 #18 resume-vs-defer branch choice before test authoring | v0.3.0 test phase | Deferred to next test-phase lead | **Correctly deferred.** AC v0.3.0 #18 at spec line 838 already documents both branches with "Pick one in the v0.3.0 pre-release checklist." The `spec.md` line 869 v0.3.0 pre-release checklist names the choice as a deliverable. This belongs to the v0.3.0 test phase, not to v0.2.0. |
| QA-SF-2 | Add Test Plan bullet for bidirectional-rollback (AC v0.3.0 #13) | v0.3.0 test phase | Deferred to next test-phase lead | **Correctly deferred.** AC #13 applies to `wiki_ingest` (v0.3.0). No v0.2.0 test exists or should exist for this. |
| QA-SF-3 | v0.5.0 CLI `--json`/`--human` AC missing | v0.5.0 test phase | Deferred to next test-phase lead | **Correctly deferred.** v0.5.0 is the `wiki.lint` release; the CLI output-mode coverage belongs there. |

No v0.2.0-scoped SHOULD-FIX was silently dropped. The deferral record is accurate and the phase summary §Risks item 4 forwards it cleanly. I log this as **no finding**.

However, I note for the council chair: the phase summary should also flag for v0.3.0 test-phase lead that **QA-SF-1 should block v0.3.0 test authoring, not merely the v0.3.0 pre-release checklist.** The current spec prose leaves both possible, but the prior QA assessment (council-spec-r3-qa) was explicit that the branch choice must be locked **before test authoring begins** — because tests for the "resume" branch look materially different from tests for the "defer" branch. This is a sequencing detail, not a new finding; flagging it here for hand-off clarity.

---

## Regressions

### `check_anytype` fixture refactor — PASSED

The test-writer refactored `tests/test_anytype_client.py::check_anytype` from module-level `autouse=True` to a non-autouse fixture, with the three pre-existing live-API classes (`TestListSpaces`, `TestListObjects`, `TestGetObject`) each explicitly opting in via a class-level autouse wrapper:

```python
@pytest.fixture(autouse=True)
def _require_live_anytype(self, check_anytype):
    pass
```

I verified this pattern at lines 53–56, 71–73, 91–93 of `tests/test_anytype_client.py`. The new v0.2.0 mock-based classes (`TestAnytypeReadClientImport`, `TestAnytypeReadClientClassPath`, `TestModuleWrapperPath`, `TestImportRegressionIndexer`, `TestBaseClientInheritance`) correctly do NOT request the fixture and therefore are not gated by live Anytype availability. This is the correct pattern.

**Regression risk to v0.1.0 live-API behavior:** none. The three live test classes continue to skip when Anytype is unreachable (which is their intended behavior); the v0.2.0 mock classes fail loudly pre-impl (the required behavior). The fixture-scope change is surgical and asymmetric: less gating for the new classes, same gating for the old ones.

### Other regression vectors — PASSED

- `tests/test_server.py` remains gated by its `check_services` autouse fixture for `TestSemanticSearch` and `TestReindexTool` (the v0.1.0 live-service tests). Unchanged behavior. Confirmed.
- `tests/test_indexer.py`, `tests/test_chunker.py`, `tests/test_embedder.py` — untouched by this spec. No regression path.
- `tests/wiki/conftest.py` — zero autouse fixtures; all fixtures (`anytype_env`, `anytype_available`, `mock_anytype`) are opt-in via explicit request. No surprise coupling across wiki test files.
- The `from anytype_llm_wiki.anytype_client import list_spaces, list_objects, get_object` import at line 21 of `tests/test_anytype_client.py` — the regression-test approach in `TestImportRegressionIndexer` plus the spec's commitment at line 742 that module-level wrapper functions are preserved mean `indexer.py:11` (`from .anytype_client import get_object, list_objects, list_spaces`) will continue to work post-refactor. This is AC #12's third assertion path and is covered.

### Concurrency test mechanism — PASSED

Spec line 1913 explicitly requires `multiprocessing.Process` and explicitly rejects threads, async, or a mocked flock. Verified at `tests/wiki/test_util.py::TestSpaceIngestLockConcurrency::test_second_process_fails_with_ingest_in_progress` (line 250): the test uses `multiprocessing.Process(target=_try_acquire_lock, args=(lock_dir, space_id, result_queue))` and `multiprocessing.Queue` for synchronization. The `_try_acquire_lock` helper at line 230 acquires the real `space_ingest_lock` inside the child process (not a mock). This is the canonical pattern the spec requires.

The only residual risk is the `time.sleep(0.3)` hold for the child to acquire before the parent tries — potential flakiness on heavily loaded CI runners. R1 already flagged this as an acceptable trade-off against exercising the real kernel-held flock. I concur.

### Pre-impl failure signal quality — PASSED

Phase summary reports: 193 failed / 6 passed / 6 skipped / 3 xfailed / 208 total. The 193 failures are `ModuleNotFoundError: No module named 'anytype_llm_wiki.wiki'` or `ImportError: cannot import name 'AnytypeReadClient'`. R1 and R2 both verified this; 189 raw `def test_` occurrences across the changed files × parametrization expansion is consistent with 208 collected items.

I did not re-run pytest (the lead noted a sandbox block on `uv run pytest`; I have the same constraint); however, the R2 reviewer, the r1-fixer debrief, and the test-writer debrief all converge on this number, and cross-checking the test function count against the reported total leaves no inconsistency that would warrant escalation. I accept the pre-impl failure signal as clean.

---

## Findings

### BLOCKING

_None._

### ADVISORY

**ADVISORY-A1 — Spec prose for `schema_upgrade` key names is informal (impl-phase opening)**

**Category:** Test-to-spec coupling.
**Cheapness of fix:** one-line spec edit, or confirmed in impl-phase kickoff.

`test_bootstrap.py::test_bootstrap_on_outdated_schema_returns_ok` asserts the keys `from`, `to`, and `properties_added` on the `schema_upgrade` dict. The spec at lines 1601–1604 uses these names in prose (`from: "0.3.0"`, `to: "0.4.0"`) and at line 1604 describes "a `schema_upgrade` section listing the properties added" without naming the list key explicitly. If the implementer independently decides on `old_version`/`new_version`/`added_properties` (any reasonable developer rename), the test will correctly fail loud and force a conversation — but the conversation is better to have at impl kickoff than post-impl.

**Recommended action:** At impl-phase kickoff, the impl lead should ensure the spec's `schema_upgrade` key names (`from`, `to`, `properties_added`) are the contract. Either:
- Land a one-line edit in the spec at §Schema Compatibility line 1604 naming these keys as the contract, OR
- Have the impl lead treat the test as the contract (since R2 already approved it) and match it verbatim.

This is non-blocking: the test will fail loud on divergence, which is correct test-phase behavior.

**Spirit-of-Jan-feedback applicability:** Yes. This is cheap to address now. Recommended inline fix before impl begins.

---

**ADVISORY-A2 — Carry-forward to v0.3.0 test-phase lead: `strict=False` xfail audit discipline**

**Category:** Multi-version test-suite hygiene.
**Cheapness of fix:** process item, not a code edit.

The 3 xfail tests for AC #13 `wiki_ingest`/`wiki_query` and AC #14 `wiki_ingest` use `strict=False`. When v0.3.0/v0.4.0 modules land, these tests may start passing without the marker being removed — and `strict=False` will not fail them on xpass. The v0.3.0/v0.4.0 test-phase leads must explicitly audit the xfail list.

The phase summary §Risks item 1 already flags this. This advisory is a request to **additionally** record it as a v0.3.0 test-phase kickoff item (not just a "risk we should be aware of"). Alternatively, an even stronger fix: when v0.3.0 authoring begins, consider flipping these markers to `strict=True` for the duration of test writing so the CI signal is automatic.

**Spirit-of-Jan-feedback applicability:** Partial — the cheap-now version is to add this as an explicit line item on the v0.3.0 test-phase kickoff checklist (if such a doc exists) or in `CLAUDE.md` / `docs/test-phase.md` under multi-version suite discipline. Not a v0.2.0 blocker.

---

**ADVISORY-A3 — Test-phase deliverable coverage for pre-release-checklist-only items**

**Category:** Pre-release gate visibility.
**Cheapness of fix:** documentation pointer in the phase summary.

The v0.2.0 pre-release checklist at spec lines 762–794 enumerates ~25 items that are **not** covered by automated tests — positioning-verification.md, live `verify-anytype-writes.sh` execution, NOTICE file, `.bandit` baseline, CRA Art. 14 paragraph in SECURITY.md, README Trademarks footer, and so on. Many of these correspond to ACs that were scoped as "maintainer-measured-at-release-time" (AC #6 p95 timing, AC #7 live verification script).

This is by design — these are human-verified gates, not CI gates. But the phase summary does not enumerate which v0.2.0 ACs rely on maintainer-local verification vs. automated test. If the impl lead does not see this explicitly, there is a risk of "all tests green → ship" without running the pre-release checklist.

**Recommended action:** The impl-phase opening should have a line that says, in effect: "Acceptance is not `pytest -xvs` green alone. The v0.2.0 pre-release checklist at spec lines 762–794 must also be walked before the v0.2.0 tag. Specifically, AC #6 (timing p95) and AC #7 (live verification script) are maintainer-measured." The phase summary (or impl-phase kickoff) should flag this.

**Spirit-of-Jan-feedback applicability:** Yes — cheap to address at impl-phase opening.

---

## Message to Other Roles

**To the CPO (via council chair):** No acceptance-criteria-vs-user-need mismatch identified. All 15 v0.2.0 ACs trace back to either Must or Should MoSCoW items. Product-level fitness-for-purpose for v0.2.0 ("bootstrap + doctor + schema + verification script + OSS hygiene") is coherent.

**To the CTO (via council chair):** The BLOCKING-CTO-1 refactor (AC #12) is covered at all three paths — class (`AnytypeReadClient`), module-level wrappers, and `indexer.py` import regression — and the `_BaseAnytypeClient` transport-only contract is covered separately in `tests/wiki/test_base_client.py`. No CTO follow-up from a QA perspective.

**To the Infrastructure Lead (via council chair):** The kernel-held flock concurrency test (AC v0.3.0 #5, currently deferred) is correctly using `multiprocessing.Process` per spec line 1913. The `space_ingest_lock` utility is already being exercised in v0.2.0 by 10+ lock-payload tests covering directory creation (0o700), file mode (0o600), PID encoding, `source_ref` redaction (both query-string and userinfo), sequential reacquisition, cross-space concurrency, and the real two-process race. This is stronger lock-layer coverage than the spec's v0.2.0 MoSCoW strictly required and reduces v0.3.0 ingest implementation risk. No Infra follow-up.

**To the CSO (via council chair):** CSO R3-CSO-3 (source_ref redaction under lock payload) is covered in v0.2.0 by `test_source_ref_redaction_query_string_scrubbed` and `test_source_ref_redaction_userinfo_scrubbed` (visible at test_util.py lines 210–227). The CSO's R3 ADVISORY for a v0.3.0 AC still applies — the v0.2.0 scaffolding tests lock-layer redaction but the CSO asked for an ingest-layer AC. That is a v0.3.0 scope item, not v0.2.0. No CSO-gate issue for v0.2.0 advancement.

---

## Recommendation

**Advance to `impl`.**

**Conditions:** None are blocking. Three ADVISORY items for consideration at impl-phase opening:
1. (A1) Confirm `schema_upgrade` key-name contract at impl kickoff — either spec-edit or treat the test as the contract.
2. (A2) Carry `strict=False` xfail audit discipline into v0.3.0 test-phase kickoff docs.
3. (A3) Make explicit to the impl lead that green pytest is necessary but not sufficient — the v0.2.0 pre-release checklist at spec lines 762–794 is co-gating.

**Signal to the council chair:** I sign off on test-phase quality. The R1→R2 cycle surfaced real defects; they were correctly fixed; no new R3-round defects are warranted. I do not dissent from any R2 positive assessment and I add no new BLOCKING.

**Confidence:** High. The two most important properties of a pre-impl failing-test scaffold are (a) that it fails cleanly for the right reason, and (b) that each AC is exercised by a test that would fail on an unimplemented or incorrect implementation (no silent-pass tautologies). Both properties are satisfied.

---
