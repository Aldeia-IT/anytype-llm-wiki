# Consolidated Spec Review — Round 1: Supply-Chain Security Hardening (#231)

**Date:** 2026-05-30
**Reviewers:** chief-security-officer, infrastructure-lead, chief-technology-officer (parallel specialist team) + lead inline checks
**Source review files:** `review-security.md`, `review-infra.md`, `review-technical.md`

## Verdict: NEEDS REVISION
1 BLOCKING + 10 SHOULD-FIX must be addressed. All three specialists returned APPROVED WITH CONDITIONS individually; the BLOCKING (B1) was raised by infrastructure-lead and is genuinely release-breaking, so the consolidated verdict is NEEDS REVISION pending a fix round.

Per phase policy, ALL findings below (BLOCKING, SHOULD-FIX, and SUGGESTION) must be addressed by the fixer — accept, fix, or document a concrete rationale for deferral.

## Lead inline verification (spot-checks performed)
- **`--dev` bug confirmed:** `pyproject.toml` declares `dev` under `[project.optional-dependencies]` (an *extra*); there is no `[dependency-groups]` or `[tool.uv]` table. So `uv sync --frozen --all-extras --dev` is wrong — `--all-extras` already covers `dev`, and `--dev` targets a non-existent uv dependency-group. Appears at spec lines 118, 146, 441, 494. **Triple-confirmed** (all three reviewers independently).
- **B1 confirmed:** `version = "0.1.0"` is static (hatchling, no dynamic versioning); `release.yml` triggers on `v*`. A tag whose version differs from `pyproject.toml` publishes the wrong version or 400s on PyPI after attestation.
- **skip_publish gap confirmed:** `workflow_dispatch` + `skip_publish` is described only in the Test Plan (line 669), not in the authored `release.yml` (lines ~410–506).
- **SHA pins:** CTO grep-verified all 5 SHA pins are carried verbatim from `research.md` into `spec.md`, including the correctly-dereferenced annotated-tag commit SHA for `pypa/gh-action-pypi-publish`. Sound — no change needed.

---

## BLOCKING

### B1 — Tag version vs `pyproject.toml` version unreconciled (infra)
`release.yml` triggers on `v*`, but the published artifact version comes solely from the static `version = "0.1.0"` in `pyproject.toml` (hatchling, no dynamic versioning). Pushing `v0.2.0` against a stale manifest silently publishes `0.1.0`, or 400s on PyPI **after** the provenance attestation step — a partial, irreversible release (PyPI is immutable).
**Fix:** Add a tag-vs-manifest guard step before `uv build` that fails if the `v<X.Y.Z>` tag does not match `project.version` — OR adopt tag-driven/dynamic versioning (`hatch-vcs`). Specify which, with the exact guard command. Document the failure as a hard gate (release aborts before any publish/attest side effect).

---

## SHOULD-FIX

### SF-1 — Drop the `--dev` flag; standardize one canonical install/test command (security, infra S4, tech — triple-confirmed)
`uv sync --frozen --all-extras --dev` is wrong (see inline verification). Drop `--dev` everywhere (lines 118, 146, 441, 494). Pick ONE canonical command for install (`uv sync --frozen --all-extras`) and ONE for tests, and make CI, `release.yml`, and the CONTRIBUTING.md update all agree. This resolves the spec's own Open Question #2 (lines 760–762) — resolve it, don't leave it open.

### SF-2 — Release-path lockfile check missing (infra S3)
`uv lock --check` runs only in the merge-gate. Tags can be pushed to commits that bypassed the merge-gate, so a release could build from a drifted lockfile. Add the install-free `uv lock --check` step to the release job before build.

### SF-3 — Tag-gate prose overpromises vs implemented workflow (tech SF-2)
Spec prose (line ~102) claims the tag-gate runs "static security analysis, license check," but the authored `release.yml` runs only `uvx pip-audit`. Reconcile: either implement bandit/pip-licenses in the workflow, or correct the prose + diagram to state only `pip-audit` runs. Prose, diagram, and workflow must agree. (Prior council guidance treats bandit/pip-licenses/gitleaks as tag-gating OSS hygiene — adding them is in-scope-adjacent; decide explicitly and state it.)

### SF-4 — `skip_publish` / `workflow_dispatch` escape hatch not in the real workflow (infra S1)
The Test Plan's strategy for validating the publish path before a live PyPI publish depends on a `workflow_dispatch` + `skip_publish` input that `release.yml` never defines. Promote it into the authored `release.yml` so the publish path is actually testable pre-first-tag.

### SF-5 — Fail-open Environment control should be a hard prerequisite AC (security SF-4)
The entire defense against a malicious/erroneous tag triggering an unreviewed publish rests on the `pypi` GitHub Environment's required-reviewer + restricted-tag settings, configured out-of-band and unverifiable in-repo. Elevate to a hard prerequisite in the Implementation Plan with a verification step (`gh api` check that the `pypi` environment has required reviewers and a `v*` deployment-branch/tag rule). Note infra dependency: confirm the repo's GitHub plan tier supports Environment protection rules and restricted tag-creation (private-repo Environments require a paid tier; public OSS repos get them free — state which applies here).

### SF-6 — Audit perimeter gaps (security SF-2)
`pip-audit` runs `--no-dev` (dev/test deps that execute on the privileged release runner are never scanned) AND tag-gate-only scanning leaves a window where a vulnerable/malicious dependency can merge to `main` and sit undetected until the next tag. Either add a lightweight scheduled (weekly `cron`) `pip-audit` as a mitigation, or name this as an explicitly accepted residual risk in Security Considerations with the rationale.

### SF-7 — Build-backend dependencies not frozen or audited (security SF-3)
`uv build` resolves the `hatchling` build backend (and its transitive deps) fresh from PyPI at release time — these execute arbitrary code to produce the *attested* artifact, yet are not in `uv.lock`, not frozen, not audited. Either pin `[build-system] requires` to exact versions (and document the maintenance cost), or explicitly accept the risk in Security Considerations with rationale (build backend is a small, reputable, widely-used package).

### SF-8 — No partial-failure / recovery procedure (infra S2)
Per-file PyPI uploads are not transactional; a failure between attestation and publish (or mid-publish) can leave a partial release. PyPI immutability means the version is then burned. Document the recovery path (bump patch version + retag) in Operational Considerations.

### SF-9 — No Python version matrix (infra S5)
`requires-python = ">=3.11"` but the test job runs on a single non-deterministic interpreter. Add a min+max matrix (e.g., 3.11 and the current latest, 3.13/3.14) to the CI test job so "3.11+" is actually validated.

### SF-10 — Redundant `uv sync` before `uv build` in release job (tech SF-3)
The release `build-and-publish` job runs `uv sync` before `uv build`. `uv build` creates its own isolated build environment and does not need the project synced — this is wasted time and an unnecessary dependency-install surface on the most sensitive (OIDC/attestation) job, contrary to the spec's own least-privilege intent. Remove it (the install-free `uv lock --check` from SF-2 is the only pre-build step the release job needs).

---

## SUGGESTION (address or note rationale)

- **SG-1 (infra G1):** Add a committed `docs/releasing.md` runbook covering the one-time PyPI pending-publisher + GitHub Environment `pypi` setup, and the SF-8 recovery path. Gives SF-5 a documented home.
- **SG-2 (infra G3 / lead):** In the Test Plan, prefer `--dry-run` + `workflow_dispatch(skip_publish)` over `act`. `act` needs Docker, which contends with the 2GB Colima cap on the shared Mac Mini host. If full `act` is wanted, note it should run off the shared host.
- **SG-3 (security suggestions):** Consider documenting `gh attestation verify` usage in README as a consumer-facing verification snippet (already noted optional in spec — confirm it lands).
- **SG-4:** Carry over the remaining minor suggestions from the three specialist review files (`review-security.md` 6 suggestions, `review-infra.md` G2/G4, `review-technical.md` 4 suggestions) — fixer should read those files and address or briefly justify deferral of each.

---

## Cross-cutting notes
- **No host/resource impact:** infra-lead confirmed this is a GitHub-hosted-only change — zero steady-state load on the Mac Mini M4 32GB, no launchd/Docker/service changes. The spec's "negligible host impact" claim is accurate.
- **Scope discipline:** SECURITY.md is correctly treated as adjacent (prior council: tag-gating OSS hygiene) and not pulled into this spec's scope. Good. SF-3's bandit/pip-licenses question is the one place to decide explicitly whether to expand tag-gate scope.
- **Strategy is sound:** all three reviewers agree the merge-gate/tag-gate split, OIDC-no-secrets posture, full SHA pinning, and cache-free release builds are architecturally correct. The findings are corrections and honesty/completeness fixes, not a redesign.
