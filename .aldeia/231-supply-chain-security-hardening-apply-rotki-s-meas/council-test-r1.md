# Council Meeting — Post-test (Round 1)

**Date:** 2026-05-31
**Ticket:** #231 — Supply-Chain Security Hardening (apply rotki's measures)
**Phase reviewed:** test
**Client:** anytype-llm-wiki (open-source MCP server; Python/uv; public repo, MIT; owned by Aldeia IT)

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator / synthesis |
| QA Director | Yes | minimum — test coverage / AC traceability / next-phase routing is the core question for a test-phase review |
| Chief Technology Officer | Yes | test engineering quality + reviewer-diligence check (was the in-phase APPROVED a genuine verification?) |
| Chief Security Officer | Yes | supply-chain hardening is the ticket's core; the false-assurance boundary (static tests vs. side-effect controls) is a security call |
| Infrastructure Lead | Yes | greenfield CI bootstrap → day-one-red-main rollout risk is operational; also in-phase spec reviewer (R1/R2) |
| Chief Product Officer | Yes | scope discipline + deferred-work tracking (addendum items 5–6 phase-exit obligations) |
| Legal Counsel | No | spec council cleared legal with no material issues; the test phase adds no new legal surface (YAML/config/docs static assertions, no new dependencies, no data handling) |
| Client Advocate | No | anytype-llm-wiki is Aldeia's own internal/OSS tool, not an external client engagement; CPO covers reputation/community value (consistent with spec council) |

## Context Presented

The test phase produced one deliverable: **`tests/test_ci_config.py`** — a stdlib-only (pathlib + re,
no PyYAML) pytest module of 24 tests (21 active, 3 skipped) that statically asserts the spec's AC
invariants against the not-yet-created `.github/workflows/*`, `.github/dependabot.yml`, `docs/*`,
`pyproject.toml`, `CONTRIBUTING.md`, and `README.md`. All 21 active tests currently FAIL (exit 1) with
clean `AssertionError` messages (no collection/import errors) — the required pre-impl gate state.

The test scope deliberately follows **spec addendum item 4**: durable static-assertion verification is
the test scope; side-effect ACs (AC4 actual provenance attestation, AC5 live `pypi` Environment
protection, AC8 mismatch-fails-build) are explicitly `@pytest.mark.skip`-marked with runbook-pointer
rationale and left to the impl/release-runbook. The suite went through one in-phase review round
(APPROVED, 0 BLOCKING, 0 SHOULD-FIX, 2 SUGGESTIONS — one applied inline, one consciously deferred).

The chair independently reproduced the fail state (`21 failed, 3 skipped, exit 1`) and confirmed zero
hardcoded 40-char SHAs in the assertions before convening.

## Discussion

The council converged to a unanimous sign-off. No member raised a blocking concern. The cross-cutting
themes were all about **what the static suite structurally cannot enforce** and must therefore be
carried into impl-acceptance — not about defects in what was delivered.

- **Format-invariance verified (CTO, independently re-ran the suite).** Assertions use `@[0-9a-f]{40}`
  and `hatchling==\d+\.\d+` regexes, never the spec's illustrative literal SHAs/`1.27.0`. This is the
  "fail-forever" trap (a test that hardcodes example SHAs would red-line a correct impl that re-resolves
  SHAs at author time per addendum item 3) — the test-writer avoided it. CTO grepped: zero literal SHAs.
- **Reviewer diligence CLEARED (CTO).** The in-phase `test-review-r1.md` reproduces the exact run result,
  cross-references each assertion to a spec line, and honestly surfaces two real residual SUGGESTION-level
  risks (AC6 keyword soft-pass, AC1 both-jobs). That profile is a genuine verification, not a rubber-stamp.
- **False-assurance boundary drawn correctly (CSO).** The highest-consequence control — the AC5
  **fail-open** `pypi` Environment — and the other two side-effect controls are SKIP-marked (visible as
  3 SKIPs, not silent passes) with rationale naming `docs/releasing.md` as the real verification locus.
  A green suite cannot mislead a reader into believing AC5 is enforced. CSO calls this the single most
  important thing to get right, and it is correct and conspicuous.
- **Green-suite precondition is the load-bearing impl gate (Infra + QA + CSO + CPO all flagged it).**
  Once `ci.yml` lands, `uv lock --check` + pytest on **both** 3.11 and 3.13 become required on the next
  PR. The static suite cannot (and by design does not) assert the existing app suite is green on both
  interpreters; the worktree interpreter is 3.14 so it cannot be verified here either. Addendum item 1,
  spec-council advisory 2, and the phase summary's Risks section all carry it forward. It must be a
  **separately verified** impl-acceptance step — "21 static tests green" is necessary but NOT sufficient.
- **`uv lock` re-sync guidance corrected (QA, verified directly).** The phase-summary/debrief note
  "re-run `uv lock` after the hatchling pin change or it red-lines `main`" is **harmless but not
  load-bearing**: `hatchling` does not appear in `uv.lock` (0 references) — `[build-system] requires` is
  build-environment metadata outside the resolved graph, so pinning it does not alter `uv.lock` or break
  `uv lock --check`. The genuine day-one risk is the green-suite-on-both-interpreters gate, not the
  lockfile. The handoff note should be corrected so impl does not chase a non-issue.
- **`actionlint` gate not yet implemented (Infra, confirmed absent).** Addendum item 4 and spec-council
  advisory 6 name `actionlint` first; it was correctly left to CI (not the static suite), but it is not
  yet anywhere. Without it, structurally-broken-but-string-present YAML can pass the presence tests yet
  fail at GitHub parse time = day-one red. Recommend impl add an `actionlint` step (CI and/or test).
- **Scope discipline PASS; deferred-work tracking STILL OPEN (CPO, verified against the live repo).**
  The phase stayed exactly within addendum item 4 (~$4.50, 2 sub-agent invocations, 1 review round, no
  drift). But CPO verified that **no GitHub issues exist** for the deferred OSS-hygiene scanner suite
  (bandit / pip-licenses / gitleaks) or SECURITY.md / responsible-disclosure, and #231 is **not
  retitled**. These survived the spec→test boundary unactioned; they must not survive a third silently.

## Findings

### BLOCKING
None.

### ADVISORY

1. **[Infra/QA/CSO/CTO/CPO] Green-suite precondition is the top impl-acceptance gate (addendum item 1).**
   Before/as `ci.yml` lands, the impl must independently verify the **existing** app suite
   (`test_anytype_client`, `test_chunker`, `test_embedder`, `test_indexer`, `test_server`) is green on
   **both** Python 3.11 and 3.13, and `uv lock --check` exits 0. The static suite cannot enforce this.
   Impact: HIGH if dropped — red-lines `main` on day one. Carried into the post-test spec addendum.

2. **[QA] Correct the `uv lock` re-sync handoff note (refinement to addendum item 3).** `hatchling` is
   absent from `uv.lock`; the build-system pin change does not affect lockfile consistency. Re-running
   `uv lock` is harmless but not the day-one risk. Impl should still re-resolve the hatchling pin to
   **current-latest** at author time (the spec's `1.27.0` is illustrative and may be stale by 2026-05-31).

3. **[CSO] Tighten the AC2 SHA-pin regex to close a trailing-comment soft-pass.** Because the lookahead
   `(?!.*@[0-9a-f]{40})` scans the whole line, a tag-pinned action carrying a 40-hex string in `@<sha>`
   form inside its trailing comment (`uses: foo/bar@v4 # pinned-from @<sha>`) is not flagged. Low
   likelihood (spec convention comments with `# v6.0.2`, never `# @<sha>`), but anchoring the check to
   the `uses:` token (e.g. `\S+@[0-9a-f]{40}` before the comment) closes it. Strengthen in impl.

4. **[Infra/CSO] `actionlint` YAML-validity gate is not yet implemented.** Add an `actionlint` invocation
   (CI step and/or a test) per addendum item 4 / spec-council advisory 6, so a structurally-broken
   workflow is caught before it red-lines `main`. Impl deliverable.

5. **[CSO/QA/CTO/Infra] Carry the AC5 scriptable hard-gate forward (addendum item 2).** The exits-non-zero
   `gh api repos/.../environments/pypi … --jq` Environment check (required_reviewers ≥1 AND a `v*`
   deployment policy) is the only closure of the fail-open publish control and cannot be exercised by a
   unit phase. It must land in `docs/releasing.md` as a mandatory, ordered, copy-paste first-release step
   (a self-enforcing hard-fail step in `release.yml` is endorsed further hardening). QA notes there is
   currently no test asserting `docs/releasing.md` even exists — impl-reviewer to confirm manually.

6. **[QA/CTO/CPO] AC6 seven-section intake check uses weak keyword discriminators (`release`, `license`).**
   `SPDX-License-Identifier` or incidental "release workflow" prose could soft-pass. Accepted as-is (the
   addendum deliberately grants prose freedom; over-coupling heading wording is the worse error), but the
   impl-reviewer must manually confirm `docs/dependency-intake.md` substantively contains all seven
   **checklist sections**, not just keyword hits.

7. **[CPO] Deferred-work follow-up ticket(s) still unfiled (addendum item 5) — chair phase-exit action.**
   Verified live: zero issues exist for the bandit/pip-licenses/gitleaks scanner suite and
   SECURITY.md/responsible-disclosure. Chair files the consolidated follow-up ticket at this phase exit so
   "deferred" stays tracked, not dropped. Does not block the impl phase; gates **#231 closure**.

8. **[CPO] Ticket/PR retitle outstanding (addendum item 6) — chair/PR-open action.** #231 still reads
   "Supply-chain security hardening (apply rotki's measures)," understating the true scope (greenfield
   CI/CD foundation + hardening). Retitle the ticket; retitle the PR at PR-open. Hygiene, no code impact.

## Resolutions

No member withdrew a finding; there were no contradictions to resolve. The CTO explicitly cleared the
reviewer-diligence question (the in-phase APPROVED is a genuine, reproduced verification). The QA Director's
direct check refined (did not contradict) the addendum-item-3 handoff guidance — the `uv lock` re-sync is
a non-issue for lockfile consistency, and the council recorded the correction so impl does not waste effort
on it. The AC1 both-jobs concern from the in-phase review was confirmed already resolved (commit `917136d`
strengthened the assertion to `count >= 2`). All eight findings are ADVISORY; none gate the test→impl
transition.

## Recommendation

**Recommended target:** `impl`
**Confidence:** high
**Rationale:** The failing test suite is a clean, correctly-scoped, format-invariant contract that fails
now for the right reasons and hands the impl-worker an unambiguous gate. All five specialists signed off
with zero BLOCKING findings, the in-phase reviewer's diligence is cleared, and the false-assurance boundary
between static assertions and side-effect controls is drawn correctly and conspicuously. Per canonical phase
order (research → product → spec → test → impl), the next gate is `impl`. The eight advisories are
impl-acceptance refinements (1–6) and chair phase-exit obligations (7–8); the actionable next-phase items
are captured in `spec-addendum-post-test-r1.md` so they are honored regardless of routing, and the chair
actions items 7–8 at this exit.
**Dissent:** None.
