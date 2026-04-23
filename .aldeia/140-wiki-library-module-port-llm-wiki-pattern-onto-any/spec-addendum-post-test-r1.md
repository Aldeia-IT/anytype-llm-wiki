# Spec Addendum — post-test council (R1)

**Source:** [`council-test-r1.md`](council-test-r1.md)
**Date:** 2026-04-23
**Target phase:** impl (v0.2.0)
**Status:** Authoritative — the impl phase MUST honor these items as spec requirements.

**Rationale:** The post-test council (R1) produced 0 BLOCKING findings and 15 advisories. Eight of them are cheap, actionable fixes that — per Jan's ticket directive (*"Since we're addressing the blocking issue in a spec re-run, fix the advisory findings as well!"*) — should land on the impl branch rather than being deferred to v0.2.0 tag time or silently carried. This addendum captures them as impl-phase opening acceptance criteria.

**Note on convention:** The items below use the form "the impl **must**…" because they now carry the weight of spec requirements. They join the 15 v0.2.0 ACs at `spec.md` lines 730–745 as the authoritative contract for impl completion.

---

## Additional acceptance criteria for the impl phase (v0.2.0)

### A. First-commits on impl branch — test-suite and packaging hygiene (must land before any `src/anytype_llm_wiki/wiki/` edits)

1. **[CSO R1-CSO-A4 + Infra + CTO]** `psutil>=5.9` must be moved from `[project.optional-dependencies].dev` to `[project].dependencies` in `pyproject.toml`. Doctor command calls `psutil.virtual_memory()` at runtime (spec lines 1165, 1633) to gate the 16 GB + ≥7B-model OOM-kill safety signal; consumers installing via `pip install anytype-llm-wiki` (no `[dev]` extras) must have psutil available. Keep it listed under `[project.optional-dependencies].dev` too for developer-install convenience. Rationale: packaging correctness + safety-signal continuity.

2. **[CSO R1-CSO-A1]** In `tests/wiki/test_bootstrap.py:609` (AC #9 `test_403_on_create_type_returns_config_error`), change the OR-disjunction assertion
   ```python
   assert "insufficient_token_scope" in result_str or "[CONFIG ERROR]" in result_str
   ```
   to conjunction:
   ```python
   assert "insufficient_token_scope" in result_str and "[CONFIG ERROR]" in result_str
   ```
   Rationale: spec line 739 requires BOTH the `[CONFIG ERROR]` severity prefix AND the `insufficient_token_scope` token. Same defect class as R1 SF-1 (AC #3 OR escape valve) that the test reviewer caught.

3. **[CSO R1-CSO-A2]** In `tests/wiki/test_bootstrap.py:630` (AC #9 `test_insufficient_scope_error_mentions_settings_api`), replace the two-substring check
   ```python
   assert "Settings" in result_str and "API" in result_str
   ```
   with the exact breadcrumb phrase:
   ```python
   assert "Settings → API" in result_str
   ```
   (the `→` escape form matches the R3-CSO-1 byte-stability pattern already used in `test_util.py`). Rationale: spec line 739 names the load-bearing "Settings → API" operator breadcrumb; independent "Settings" + "API" substrings do not enforce the breadcrumb's three-token ordering.

4. **[CSO R1-CSO-A3 — subsumed by item 5 below if the fixture-file path is taken]** In `tests/wiki/test_bootstrap.py:583` (AC #8 `test_readme_contains_gdpr_controller_statement`), change the OR-disjunction
   ```python
   assert "GDPR" in content or "controller" in content
   ```
   to conjunction (`and`). If item 5 below is implemented, this test can be removed entirely — the fixture-file verbatim assertion subsumes it.

5. **[CPO A-CPO-T2 + CSO R1-CSO-A3 cross-thread]** Create `tests/wiki/fixtures/readme_privacy_notice_verbatim.md` containing the full verbatim privacy-and-data-flow block from `spec.md` lines 645–656 — including the hosted-LLM ToS pass-through paragraph (spec line 652), the Qdrant/Ollama off-localhost embedding-inversion warning, the content-rights-and-PII paragraph, and the GDPR Art. 4(7) + LGPD Art. 5(VI) controller disclaimer (spec line 656). Replace the four loose substring tests in `TestBootstrapReadmePrivacyNotice` (`tests/wiki/test_bootstrap.py:555–595`) with a single assertion:
   ```python
   from pathlib import Path
   fixture = Path(__file__).parent / "fixtures" / "readme_privacy_notice_verbatim.md"
   assert fixture.read_text() in readme_text
   ```
   (keep at least one assertion that verifies the README exists and is readable, so a filesystem failure doesn't manifest as a confusing fixture-mismatch error). Rationale: AC #8 requires the verbatim 10-bullet block; current substring tests would pass on good-faith truncation; legal-compliance contract (GDPR + LGPD) must be structurally gated, not reliant on the pre-release checklist being walked manually.

6. **[Infra-A1]** In `tests/wiki/test_util.py:268` (concurrency-test handoff), replace the `time.sleep(0.3)` wait for the child process to acquire the lock with a deterministic handoff. The child at line 237 already puts `"acquired"` onto `result_queue`; the parent should block on that sentinel via `result_queue.get(timeout=5)` before attempting its own lock acquisition. Rationale: reduces CI flake vector on loaded runners; exercises the same kernel-held `fcntl.flock` semantics without the fixed-sleep race window.

### B. Impl-branch opening hygiene (first impl commits, but src-code edits may proceed in parallel)

7. **[Infra-A2]** Run `uv sync --extra dev` at impl-branch opening and commit the refreshed `uv.lock`. Four new dev deps were added to `pyproject.toml` in the test phase (`respx>=0.21`, `pytest-timeout>=2.2`, `freezegun>=1.5`, `psutil>=5.9`); `uv.lock` was not regenerated during the test phase per the lead's explicit deferral. This must be cleared before the v0.2.0 pre-release `uv lock --locked` gate (spec line 787). Note: after item 1 above moves `psutil` to `[project].dependencies`, the lockfile will reflect it as a runtime dep.

8. **[CPO A-CPO-T1 + QA A1]** The impl task file (or a one-paragraph note at the top of the impl execution plan) must explicitly state: *"Tests are the contract for two internal data-shape concerns where the spec is informal: (a) the `schema_upgrade` result section keys — `from`, `to`, `properties_added` — as asserted by `tests/wiki/test_bootstrap.py::TestBootstrapSchemaOutdated`; (b) the 12 doctor check-name strings as enumerated by `tests/wiki/test_doctor.py::EXPECTED_CHECK_NAMES` (lines 105–118). The implementation must match these names verbatim. If the impl prefers different names, the spec must be amended first — not the tests."*

### C. Impl-phase exit criteria (in addition to the v0.2.0 pre-release checklist at `spec.md:762–794`)

9. **[QA A3]** The impl phase's exit-to-Decide MUST acknowledge that `pytest -xvs` green is **not** sufficient for v0.2.0 tag. The pre-release checklist at `spec.md:762–794` (especially AC #6 p95 timing on Jan's Mac Mini M4 and AC #7 live `verify-anytype-writes.sh` against running Anytype) is co-gating and maintainer-measured. The impl lead's phase summary must record the state of each checklist item (done / deferred to tag time with rationale / not-applicable), not just the pytest result.

### D. Items carried to v0.3.0 test phase (not v0.2.0 impl scope — record in phase summary for next-phase handoff)

10. **[CSO R1-CSO-A5]** When v0.3.0 test writing begins (`wiki_ingest` / Qdrant / extraction call-paths exist), add an integration-tier test that forces a Qdrant 500, invokes `wiki_ingest` with `QDRANT_URL=https://host/path?api_key=SEKRET`, and asserts the resulting `[API ERROR]` string passes through `scrub_credentials` (SEKRET absent, host preserved). Same for `WIKI_EXTRACT_ENDPOINT` userinfo failure from the extraction call-path. The v0.2.0 unit test of `scrub_credentials` is the correct level for v0.2.0 scope; v0.3.0 needs the end-to-end gate.

11. **[CSO R1-CSO-A6]** At v0.3.0 spec/test time, add a source_ref redaction AC covering **file-path** sources (not just URLs) — e.g. `/Users/jane/Documents/internal-report.md` → basename (`internal-report.md`) or hash, never the full absolute path. This closes the R3-CSO-3 file-path-redaction concern that was deferred from the spec phase.

12. **[QA A2]** The v0.3.0 test-phase lead must audit the 3 `strict=False` xfail markers (AC #13/#14 for `wiki_ingest` / `wiki_query` / `wiki_lint`) at authoring kickoff. Recommended posture: flip to `strict=True` during v0.3.0 authoring so xpass fails loud, then remove the markers once the feature lands. Current `strict=False` was the correct v0.2.0 posture; silent-xpass is the v0.3.0 risk.

---

## Observations (not carried into this addendum — for audit only)

The council surfaced three observations that do not rise to impl-phase acceptance criteria:

- **[CTO]** `test_missing_space_returns_config_error` wraps its assertion in `if isinstance(result, dict):` — if impl raises instead of returns, the `[CONFIG ERROR]` check silently skips. R2 flagged this as not-a-regression (inherited from R1 pre-fix). No action required; impl may choose to return a dict per spec, in which case the test passes as expected.
- **[CTO]** Duplicate inheritance-hierarchy assertion in both `tests/test_anytype_client.py::TestBaseClientInheritance` and `tests/wiki/test_base_client.py::TestInheritanceHierarchy`. Belt-and-suspenders; defensible.
- **[CPO]** `test_exit_code_0_when_all_checks_pass` accepts exit code `0 OR 2` rather than strict `0`. Mild weakening of AC #10; impl should aim for exit code `0` on a clean Mac Mini M4 per spec wording.

---

## Sequencing for the impl lead

1. **Read this addendum during Task Intake** alongside `spec.md`.
2. **Commit items 1–7 first** as "impl(#140): test-gate strengthenings + packaging hygiene per post-test council R1 addendum" (or multiple atomic commits, one per item — preferred). These leave the failing-test suite in a stronger gating posture before any src-code work begins.
3. **Capture item 8 in the impl execution plan** or first commit message of src-code work.
4. **Implement the v0.2.0 src code** against the (now-strengthened) failing-test suite.
5. **At phase exit, item 9** — phase summary must enumerate pre-release-checklist state, not just pytest green.
6. **Items 10–12** — record in `phase-summary-review.md` (which the impl-phase lead writes at end-of-phase) so the v0.3.0 test-phase kickoff sees them.
