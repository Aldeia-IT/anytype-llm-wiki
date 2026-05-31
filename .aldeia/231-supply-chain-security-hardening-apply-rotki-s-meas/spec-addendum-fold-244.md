# Spec Addendum — fold #244 into #231 (interactive, pre-impl)

**Source:** Jan decision at Decide, 2026-05-31 (interactive lead session).
**Target phase:** impl
**Status:** Authoritative — supersedes the deferral in
[`spec-addendum-post-test-r1.md`](spec-addendum-post-test-r1.md) item 7 (ADV-7) and
[`spec-addendum-post-spec-r1.md`](spec-addendum-post-spec-r1.md) item 5.

## Decision

The two items previously deferred to follow-up ticket **#244** are folded back in:

- **OSS-hygiene scanner suite → now an IMPLEMENT deliverable of #231** (was: deferred /
  closure-gating only). Implement it in this phase.
- **SECURITY.md / responsible-disclosure artifact → NOT in #231's scope.** It is already
  delivered for this repo by **#234** (the anytype-llm-wiki v0.2.0 release collateral:
  `SECURITY.md`, GitHub Security Advisories + backup-email channel, 72h-ack / 14-day-triage,
  CRA Art. 14 context). **Do NOT create or duplicate `SECURITY.md` in #231.**

Consequence: **#244 is closed** (item 1 folded here, item 2 owned by #234). ADV-7's
"gates #231 closure" no longer applies — there is no longer a separate tracking ticket.

## New impl acceptance criteria

9. **[fold-244] Add the OSS-hygiene scanner suite to the TAG/audit path** (`release.yml`
   and/or `audit.yml`), consistent with #231's established convention — *security/license
   gates are tag-gating; the merge-gate stays fast (tests + lockfile consistency)*. Do **not**
   add these to the PR merge-gate (`ci.yml`); a cheap PR-time addition is optional, not required.
   Three scanners, each failing the workflow on findings:
   - **`bandit`** (Python SAST) — e.g. `uvx bandit -r src/`. A committed `.bandit` baseline/config
     is acceptable to suppress vetted false positives; document any suppressions.
   - **`pip-licenses`** (license compatibility) — fail on copyleft incompatible with the project's
     MIT license: **GPL / AGPL / SSPL / EUPL**. Pin/justify any allowlisted exceptions.
   - **`gitleaks`** (secret scanning) — `gitleaks detect` over the repo/history on the tag/audit run.
   Pin any new GitHub Actions to full commit SHAs (re-resolve at author time), matching the
   AC2 SHA-pin discipline already in the spec. Add static assertions for their presence to
   `tests/test_ci_config.py` (string-presence is sufficient here, mirroring the existing CI
   config tests) so the suite covers the new steps.

10. **[fold-244] Do not author `SECURITY.md` in this repo.** It exists via #234. If
    `release.yml`/`audit.yml` or docs want to reference a disclosure policy, link the existing
    `SECURITY.md` rather than re-stating it.

## Notes

- This does not reopen the spec design — it promotes already-scoped, already-bounded deferred
  work (spec-council advisory 4) into the current impl phase per Jan's call. The scanner set,
  rationale, and tag-gating placement were already vetted by the spec and test councils.
- Everything in `spec-addendum-post-test-r1.md` items 1–6 and item 8 (retitle) still applies.
  Only item 7 (ADV-7, the deferral) is superseded by this file.
