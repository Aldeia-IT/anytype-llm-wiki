# Council Meeting — Post-test (Round 1, Test Phase Verification) — CPO

**Date:** 2026-04-23
**Ticket:** #140 — Wiki Library Module: Port LLM Wiki Pattern onto Anytype
**Reviewer:** Chief Product Officer
**Artifact under review:** v0.2.0 failing-test scaffolding at commit `8f94d09` (test-review R1 → r1-fixer → R2 APPROVED)
**Mandate:** Scope discipline, product-alignment AC spot-checks (especially #8, #9, #10), user-visible failure modes, over-specification risk, delivery-phase honesty handoff.

---

## Verdict

**SIGN OFF. No BLOCKING. Two ADVISORIES.**

The test phase did its job. Scope discipline is intact — v0.3.0+/v0.5.0 behavior is either (a) correctly deferred, (b) covered only by clearly-marked `strict=False` xfail scaffolds, or (c) exercised as pure unit tests on helpers that happen to ship in v0.2.0 but have no v0.2.0 callers (e.g. `space_ingest_lock`, `normalize_title`, `scrub_credentials` in `wiki/util.py`). The prior spec-council R3 CPO advisories (A18–A23) all remain landed in the spec and were NOT silently weakened by the test phase. The two R1 BLOCKING defects caught by the test reviewer (AC #15 tautological test, AC #11 autouse-skip) were precisely the class of defect I would expect product-sense review to catch, and were closed cleanly in R2.

Two ADVISORIES are forwarded below — neither blocks implementation; both are cheap to address pre-impl and would prevent foreseeable rework:

- **A-CPO-T1** — `schema_upgrade` key names (`from`/`to`/`properties_added`) inferred by the test and not mandated by the spec. This is acceptable as-is if we treat the test as the contract; it becomes a problem only if the impl lead picks different key names in good faith. Cheap fix: one-sentence spec amendment pinning the keys, OR a short note in the impl kickoff brief naming the test as the contract.
- **A-CPO-T2** — AC #8's verbatim-privacy-notice contract is partially under-tested. The test asserts a 12-word substring match (`"anytype-llm-wiki runs locally on your machine"`), the section header, a permissive `localhost or 127.0.0.1` check, and a `GDPR OR controller` disjunction. The spec requires the **full 10-bullet privacy notice including GDPR Art. 4(7) controller language and the hosted-LLM ToS paragraph** (lines 645–656 + 652 subsection). An impl that pastes only the first sentence and the "Privacy and data flow" header would pass the test but fail AC #8's "verbatim" intent. This is a real gap against a legal/product contract, not a test-hygiene nit.

Jan's ticket-feedback directive — *"Since we're addressing the blocking issue in a spec re-run, fix the advisory findings as well!"* — applies in spirit here. Both advisories are cheap to address pre-impl.

---

## Summary

From the product vantage, the test phase delivered the v0.2.0 scope faithfully and honestly:

- **All 15 v0.2.0 ACs have at least one substantive test.** The R2 fixer closed both BLOCKING defects (B1 QDRANT_URL tautology, B2 AC #11 autouse-skip) with the exact replacement mechanics I'd want to see — `scrub_credentials` called directly in `test_util.py` rather than via a false `wiki_bootstrap` path; `TestWikiBootstrapRegistered` moved out of the autouse-gated module into `tests/wiki/test_server_registration.py` where it will FAIL (not SKIP) in CI.
- **The 3 xfail scaffolds for v0.3.0+ behavior (AC #13 activation, AC #14 activation) are correctly marked `strict=False`.** This is the correct non-blocking handoff to v0.3.0 test-phase authorship. It neither over-reaches (which would over-constrain v0.3.0 impl choices) nor under-signals (the test file names flag the AC numbers so the v0.3.0 test lead will see them on audit).
- **193 failed / 6 passed / 6 skipped / 3 xfailed** — the shape matches what I would expect pre-impl. The 6 passed are v0.1.0 surfaces (semantic_search, reindex); the 6 skipped are live-API gated; the 3 xfailed are v0.3.0+ scaffolds. The 193 failures all surface as `ModuleNotFoundError` on `anytype_llm_wiki.wiki` or `ImportError` on `AnytypeReadClient` — that is the correct pre-impl signal.
- **The R3 CPO advisories (A18 PyPI, A19 15-min version-stamp, A20 README:3 reconciliation, A21 two-defaults RAM, A22 OQ #5, A23 Delivery Phases honesty) remain landed in the spec.** I spot-checked spec.md:690 (honesty note), spec.md:768 (positioning verification artifact), spec.md:769 (PyPI decision checklist), spec.md:770 (15-min version-stamp checklist), spec.md:1954 (OQ #5 closed), README.md:3 (tightened claim), README.md:7 (positioning-verification note). All present. The test phase did not touch these — which is correct; they are v0.2.0 pre-release checklist items, not pre-impl artifacts.

The test phase did not over-reach its mandate: no tests for v0.3.0+ ingest/query/lint behavior except the three correctly-marked xfail scaffolds. That discipline is exactly what CPO cares about at phase boundaries.

---

## Scope Discipline Check

**PASS.** Verified three ways:

1. **Deferral of QA SF-1/2/3 is honored.** The phase summary explicitly forwards QA SF-1 (v0.3.0 AC #18 resume-vs-defer lock), QA SF-2 (v0.3.0 bidirectional-rollback Test Plan polish), QA SF-3 (v0.5.0 CLI `--json`/`--human` AC) to future test-phase leads. No stealth tests for these behaviors exist in the v0.2.0 suite.
2. **v0.3.0+ surfaces are touched only through xfail scaffolds.** `tests/wiki/test_bootstrap.py::TestBootstrapSchemaOutdatedV3Plus` (lines 746–790) imports `wiki.ingest.wiki_ingest` and `wiki.query.wiki_query` — both guarded by `@pytest.mark.xfail(reason=..., strict=False)`. `TestBootstrapPatchDecisionScaffolding` (v0.3.0 activation path) similarly guarded. No other test file references v0.3.0+ modules except via xfail.
3. **v0.2.0 helpers with no v0.2.0 callers are tested in isolation.** `wiki/util.py` ships `normalize_title`, `space_ingest_lock`, and `scrub_credentials` in v0.2.0 with no v0.2.0 callers; the spec explicitly says v0.3.0 imports them. The test phase tests them as unit-level surfaces without routing through any v0.3.0 integration point. This is correct TDD discipline for a phased delivery — the APIs are frozen at v0.2.0 tag time so v0.3.0 can depend on them stably.

**No scope creep detected.** No new v0.2.0 ACs were invented by the test writer. No implicit API surface beyond what the spec names.

**Multi-version handoff is clean.** When v0.3.0 test-writing begins, the v0.3.0 test lead has exactly three things to audit:
- The 3 xfail tests (must flip from `strict=False` to real assertions).
- QA SF-1/2/3 (R3 spec-council carry-overs that this phase correctly deferred).
- Whether v0.2.0's `util.py` API surface needs extension (e.g. `space_ingest_lock` call-sites added in v0.3.0 `ingest.py`).

---

## Product-Alignment AC Spot-Checks

### AC #8 — README verbatim privacy notice

**Spec contract (line 738):** "README shows the exact privacy notice from this spec (verbatim)."

**Test implementation (`test_bootstrap.py::TestBootstrapReadmePrivacyNotice`, lines 540–585):** Four tests, all substring checks:
1. `"anytype-llm-wiki runs locally on your machine"` — 12-word first-sentence substring.
2. `"Privacy and data flow"` — section header.
3. `"localhost" in content.lower() or "127.0.0.1" in content` — permissive data-flow statement.
4. `"GDPR" in content or "controller" in content` — disjunction allowing just one of two required concepts.

**Gap.** The spec (lines 645–656) requires a **full 10-bullet block** including: the hosted-LLM-provider-terms paragraph (line 652, ~100 words), the Qdrant/Ollama off-localhost embedding-inversion-attack warning (line 653), the content-rights-and-PII paragraph (line 654), and the GDPR Art. 4(7) + LGPD Art. 5(VI) controller disclaimer (line 656). An implementer could paste only the section header and the first sentence and the test would pass. That is not "verbatim."

This is exactly the failure mode the phase summary's "Risks and Open Items #3" flags — but in reverse. The summary warns against **synonym drift breaking the test**; my concern is the opposite: the test is **too loose** to catch truncation. Both concerns point at the same root cause — substring checks are not the right tool for a "verbatim" contract.

**What's acceptable:** A literal `README_PRIVACY_NOTICE_VERBATIM` constant in the test (or a fixtures file) containing the full 10-bullet block, asserted via `assert README_PRIVACY_NOTICE_VERBATIM in content`. This costs one fixture file + one assertion swap. It turns the test into a true "verbatim" gate.

**Severity:** ADVISORY. The test is not a product-blocker — the impl lead will likely read the spec and paste the full block. But AC #8's "verbatim" language is a product/legal contract (GDPR + Legal Advisory #15 hosted-LLM ToS paragraph), and the test should enforce the contract it names. Flagged as A-CPO-T2.

### AC #9 — Settings → API wording

**Spec contract (line 739):** `wiki_bootstrap` with read-only token returns `[CONFIG ERROR] insufficient_token_scope: the configured ANYTYPE_API_KEY cannot create Types in this space. Regenerate with write scope via Anytype Settings → API.`

**Test implementation (`test_bootstrap.py::TestBootstrapInsufficientTokenScope`, lines 588–632):** Two tests:
1. `test_403_on_create_type_returns_config_error`: asserts `"insufficient_token_scope" in result_str or "[CONFIG ERROR]" in result_str` — disjunction.
2. `test_insufficient_scope_error_mentions_settings_api`: asserts `"Settings" in result_str and "API" in result_str` — conjunction of substrings.

**Assessment:** The second test is adequate for the user-facing deeplink intent (an operator must be told where in Anytype to go). The arrow character "→" (U+2192) is not required, which is pragmatic — ASCII-only environments or alternative renderings won't break the test. The first test's OR-disjunction is weaker than I'd prefer (an impl that emits `[CONFIG ERROR]` without `insufficient_token_scope` would pass), but this is a minor point — the spec mandates both and the impl lead will read the spec.

**Verdict:** Acceptable. Product intent (error must name the Settings location) is gated.

### AC #10 — Doctor UX (exit codes + 12 checks)

**Spec contract (line 740):** `doctor` exits `0` on fresh install; exits `1` with a named FAIL line on any missing dependency.

**Test implementation (`test_doctor.py`):**
- `TestDoctorChecksPresent` parametrizes over `EXPECTED_CHECK_NAMES` (12 entries: checks 1, 2, 3, 4, 4b, 5, 6, 6b, 7, 8, 9, 10). Each test asserts the named check appears in `run_doctor()["checks"]`. **All 12 names are invented by the test writer** — the spec names the checks functionally but not by key string. This is a latent over-specification risk; see A-CPO-T1 below.
- `TestDoctorExitCodes`:
  - `test_exit_code_0_when_all_checks_pass`: asserts `exit_code in (0, 2)` — accepts 2 (WARN) as well. Permissive but correct per spec's WARN-vs-FAIL exit-code model.
  - `test_exit_code_1_when_anytype_api_key_missing`: strict `exit_code == 1`.
  - `test_exit_code_1_when_anytype_unreachable`: strict `exit_code == 1`.
  - `test_exit_code_2_when_wiki_fetch_extra_ports_nonempty`: asserts `exit_code in (1, 2)` (permissive for the WARN path).

**Verdict:** AC #10 is adequately gated. The exit code contract matches the spec ("0 on fresh install, 1 with named FAIL line"). The named-FAIL line isn't explicitly asserted in string form, but since each check has a `name` + `status` field per `TestDoctorCheckShape` and the exit-code-1 tests specifically inspect which check failed, the contract is enforced structurally.

**One observation:** `test_exit_code_0_when_all_checks_pass` accepts `0 OR 2`. The spec AC says "exits 0 on a fresh install." Strictly read, this test permits an impl that emits `exit_code=2` on Jan's clean dev environment (e.g. if `WIKI_FETCH_EXTRA_PORTS` is unset but some other check WARNs). This is a minor weakening of the AC contract but not a product-blocker — an impl that WARNs on a fresh install is a UX oddity that QA or Jan will notice.

---

## Over-Specification Risk Assessment

### A-CPO-T1 — Invented key names become the contract

Two places the test phase invented key names that are not in the spec:

**`schema_upgrade` section keys (AC #13 bootstrap exception).** Spec line 1604: *"Returns BootstrapResult with status: 'ok' and a schema_upgrade section listing the properties added."* Spec line 1601 log example uses `action`, `from`, `to` keys for the info log — but the **result-object** key names are not pinned. The test (`test_bootstrap.py:689–714`) now asserts `schema_upgrade` contains `from`, `to`, and `properties_added` keys. The phase summary's "Area of residual uncertainty" section explicitly admits this.

**Doctor check names.** `EXPECTED_CHECK_NAMES` (test_doctor.py:105–118) has 12 invented snake_case names (`anytype_api_key`, `anytype_reachable`, `ollama_extraction_model_ram_fit`, etc.). The spec names the checks functionally but not by key string.

**Product-angle assessment:** This is low-consequence. These are internal data-shape contracts, not user-facing UX. The impl lead will read the tests AND the spec, and the test-as-contract pattern is idiomatic Python TDD. But it IS over-specification relative to what the spec requires — an impl worker could reasonably have chosen `schema_upgrade.previous_version`, `schema_upgrade.current_version`, `schema_upgrade.added_properties` and been spec-compliant; the test would have rejected that.

**Cheap fix:** Before impl kickoff, one of:
- **(a) Amend spec.** Add a one-sentence line at 1604 pinning the keys: *"The schema_upgrade section contains keys `from` (old version string), `to` (new version string), and `properties_added` (list of property keys)."* Same for doctor check-name enumeration in §Doctor Command.
- **(b) Impl kickoff brief names the test as contract.** A short note to the impl lead: "Tests are the contract for schema_upgrade keys and doctor check names. Read `tests/wiki/test_doctor.py::EXPECTED_CHECK_NAMES` and `tests/wiki/test_bootstrap.py::TestBootstrapSchemaOutdated`, and match those names verbatim."
- **(c) Do nothing.** The impl lead will run the tests, see the failures, and match the key names. This is what TDD expects. The cost is one round of impl-test feedback (~30 minutes of debugging time).

**My preferred path:** (b) — impl kickoff brief. Cheapest and clearest. Amending the spec risks re-opening scope discussion; doing nothing wastes half an hour of impl time.

**Severity:** ADVISORY. Not a product-blocker.

### Does the test suite over-specify other implementation details?

**No for error strings.** `[CONFIG ERROR]`, `[API ERROR]`, `insufficient_token_scope`, `wiki_schema_outdated`, `patch_decision_missing_or_invalid` are all spec-mandated prefixes/tokens. The tests enforce the spec, not invented strings.

**No for deeplinks.** "Settings" + "API" is the spec's deeplink requirement. Test matches.

**No for structured response shapes beyond `schema_upgrade` and doctor check names** (both flagged above). `BootstrapResult` has `status` + standard keys the spec does name.

**No for file paths.** `scripts/verify-anytype-writes.sh`, `README.md`, `.aldeia/140-.../patch-decision.md` are all spec-named.

The over-specification risk is narrow and contained to A-CPO-T1.

---

## Delivery-Phase Honesty and v0.2.0 Handoff

**The spec's §Delivery Phases honesty note (line 690) is intact.** v0.2.0 alone does not deliver the Karpathy-pattern premise — the test phase doesn't and can't change that. What the test phase DOES do is lock the v0.2.0 surface so v0.3.0 can build on top without fear of API churn:

- `_BaseAnytypeClient` transport contract is frozen (test_base_client.py).
- `AnytypeReadClient` refactor of `anytype_client.py` preserves `list_spaces`/`list_objects`/`get_object` module-level surface (BLOCKING-CTO-1 coverage at AC #12).
- `normalize_title`, `space_ingest_lock`, `scrub_credentials` APIs frozen (v0.3.0 will import them unchanged).
- Doctor's 12-check shape and exit-code semantics frozen.
- Schema registry (`WIKI_TYPES`, `WIKI_SCHEMA_VERSION`) frozen.

This is the right product outcome for v0.2.0: a "structurally shippable" tag whose honest user value is "schema scaffolding + preflight diagnostics." The test suite makes the scaffolding durable. When v0.3.0 lands and delivers the actual Karpathy-pattern premise, the v0.2.0 tests remain green without modification. That's the definition of a clean per-version handoff.

**Recommended v0.2.0 release framing (reiterating R3 advisory):** tag in git; do NOT publish to PyPI. PyPI publish first happens at v0.3.0 when `wiki_ingest` actually delivers user-observable value. The spec's v0.2.0 pre-release checklist (line 769) already defaults to this; I reaffirm it here.

---

## Findings

### BLOCKING

**None.**

The test-reviewer R1→R2 cycle closed the two defects that would have been BLOCKING from my seat (AC #15 tautology, AC #11 autouse-skip). No new BLOCKING from the product-alignment pass.

### ADVISORY

**A-CPO-T1 — `schema_upgrade` keys and doctor check-names are test-invented, not spec-mandated.**

- **Description.** Test hardcodes `from`/`to`/`properties_added` keys in `schema_upgrade` result section (AC #13) and 12 snake_case check names in `EXPECTED_CHECK_NAMES` (AC #10). Spec names the behavior but not these exact strings.
- **Impact on product/users.** None user-facing. Internal data-shape contract only. Risk is one round of impl-test debugging if impl lead picks different names in good faith (~30 min cost).
- **Recommended action.** Impl kickoff brief: *"Test files `test_bootstrap.py::TestBootstrapSchemaOutdated` (schema_upgrade keys) and `test_doctor.py::EXPECTED_CHECK_NAMES` (check-name strings) are the contract. Match those names verbatim in implementation."* One-paragraph addition to the impl lead's starter context. No spec amendment needed.
- **Severity.** ADVISORY. Cheap fix, non-blocking.

**A-CPO-T2 — AC #8 verbatim-privacy-notice test is too loose to catch truncation.**

- **Description.** `TestBootstrapReadmePrivacyNotice` asserts 4 substrings: first-sentence (12 words), section header, `localhost OR 127.0.0.1`, `GDPR OR controller`. Spec (lines 645–656) requires the full 10-bullet block including hosted-LLM-ToS paragraph, Qdrant/Ollama off-localhost warning, content-rights-and-PII paragraph, and the GDPR Art. 4(7) + LGPD Art. 5(VI) controller disclaimer. An implementer could paste only the first sentence and pass the test, violating the "verbatim" contract that is a legal/product gate.
- **Impact on product/users.** Legal-compliance contract (GDPR controller framing, Legal Advisory #15 hosted-LLM ToS paragraph) is not structurally gated. If impl truncates in good faith, the test misses it and the gap surfaces only at pre-release checklist review (spec line 789: "README updated with privacy notice, hosted-LLM ToS paragraph, Trademarks footer, and prerequisites") — much later in the cycle.
- **Recommended action.** One of:
  - **(a)** Add a `tests/wiki/fixtures/readme_privacy_notice_verbatim.md` fixture file containing the full 10-bullet block (spec lines 645–656 + 664–670 Trademarks + 672–680 Supply-chain), and replace the 4 substring tests with one assertion: `assert FIXTURE_CONTENT in README_TEXT`. Costs ~30 minutes test-phase rework.
  - **(b)** Accept the loose test and rely on the pre-release checklist (spec line 789) as the legal-compliance gate. Honest but less automation-friendly.
- **Severity.** ADVISORY. Does not block impl kickoff. Should be resolved before v0.2.0 tag. My preference: (a), because pre-release-checklist gates are easy to forget and automated gates are not. But this is a test-phase issue, not an impl-phase issue, and the test phase is already APPROVED — so addressing this means a small test-phase revision before the Decide gate.

---

## Cross-Council Notes

**To QA Director:** A-CPO-T2 is a product/legal contract misalignment with the test's assertion strength. Raising to you because the decision is squarely in your domain (how strictly should AC #8 be gated at test vs. pre-release-checklist layer). If QA agrees A-CPO-T2 is worth closing pre-impl, the fixture-file pattern in (a) above is my recommended approach. If QA agrees the pre-release-checklist is sufficient, we mark A-CPO-T2 as known-and-accepted and move on.

**To CTO:** A-CPO-T1's "test-as-contract" pattern is technically sound but worth naming explicitly in the impl kickoff brief so the impl lead doesn't debug through blind AssertionErrors. No structural concern from my side.

**To CSO:** No CSO-crossover from the product pass. The credential-scrubbing test (AC #15) is now correctly implemented via direct `scrub_credentials` unit tests in `test_util.py::TestCredentialScrubbing`.

**To Infrastructure Lead:** No infra-crossover from the product pass. The cross-host dedup probe and logrotate samples are pre-release-checklist items (spec lines 765, 713–714), not test-phase items.

---

## Open Questions to Impl Lead

One item the product-facing impl worker should know before starting:

**OQ — README prose sequencing vs. privacy-notice verbatim requirement.** AC #8 requires the verbatim spec privacy notice (lines 645–656) to land in README.md. README.md:3 positioning and README.md:7 positioning-verification note are already committed; the privacy block needs to be added at the spec-named position ("new section 'Privacy and data flow' (after 'How it works')"). The impl lead should:
- Paste the full block verbatim from spec lines 645–656.
- Add the hosted-LLM-ToS paragraph (spec line 778 pre-release checklist, same text as spec line 652).
- Add the Trademarks footer (spec lines 664–670).
- Add the Supply-chain posture section (spec lines 672–680).

All four blocks are pre-release-checklist items AND impl-phase deliverables. None are in the current README. Doing them all in one v0.2.0 README PR is cleanest.

Also: if A-CPO-T2 is accepted and the verbatim-fixture test is added, the impl will need to copy the exact bytes from the fixture into README to pass — so the fixture ordering should match the spec's ordering to avoid manual reconciliation.

---

## Recommendation

**Advance to the next SDLC phase (impl) per the R2 test-reviewer APPROVED verdict.**

From a product-strategy vantage, the test phase executed the v0.2.0 scope faithfully, maintained scope discipline at the v0.3.0+ boundary, and did not silently weaken the R3 CPO advisories that landed in the spec. The two BLOCKING R1 defects were closed cleanly. The two remaining ADVISORIES are cheap to address and should ideally be resolved pre-impl under Jan's "fix advisories too" directive, but neither blocks impl kickoff.

**Preferred disposition of the two ADVISORIES:**
- **A-CPO-T1:** Close in impl kickoff brief (no test or spec change needed). Total cost: one paragraph in the impl lead's starter context.
- **A-CPO-T2:** Close via a small test-phase revision (fixture-file approach). Total cost: ~30 minutes test-phase rework + one commit. If Jan or the Decide-gate owner prefers to defer this to the v0.2.0 pre-release checklist, that's defensible; my mild preference is to close it now because automated gates are cheaper than checklist gates.

**No dissent.** No BLOCKING findings.

---

## Sign-off statement

**Chief Product Officer signs off on the v0.2.0 test phase. Test scaffolding advances to impl.**

Two ADVISORY findings (A-CPO-T1, A-CPO-T2) are forwarded to the council chair for disposition per Jan's advisory-fix directive.
