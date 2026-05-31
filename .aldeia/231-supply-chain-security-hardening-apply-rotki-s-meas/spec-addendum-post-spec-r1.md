# Spec Addendum — post-spec council (R1)

**Source:** [`council-spec-r1.md`](council-spec-r1.md)
**Date:** 2026-05-30
**Target phase:** test / impl (applies to whichever phase implements the deliverables)
**Status:** Authoritative — the implementing phase MUST honor these items as spec requirements.

## Additional acceptance criteria for the next phase

1. **[Infra-A2 / QA-ADV-4] Green-suite precondition before the merge-gate lands (load-bearing).**
   Before or as `ci.yml` is introduced, confirm `uv lock --check` passes and `pytest` is green
   on **both** Python 3.11 and 3.13. Introducing CI to this no-CI repo makes these checks
   required on the next PR; a drifted `uv.lock` or a suite that is not green on both
   interpreters will immediately red-line `main`. This is the single most important
   impl-acceptance gate. If the suite is not currently green on both, fix that as part of this
   work (or document the gap explicitly) — do not land a permanently-red `main`.

2. **[CSO-ADV-1 / Infra-A1 / QA-ADV-3] AC5 Environment check must be a scriptable hard gate.**
   The fail-open `pypi` Environment verification (currently a `gh api` call whose output is read
   by a human) must be expressed as a `gh api repos/Aldeia-IT/anytype-llm-wiki/environments/pypi
   ... --jq` one-liner (plus the `deployment-branch-policies` call) that **exits non-zero**
   unless (a) a `required_reviewers` rule with ≥1 reviewer exists AND (b) a `v*` tag deployment
   policy exists. Place this in `docs/releasing.md` as a mandatory, copy-paste, ordered
   first-release step. A self-enforcing assertion step inside `release.yml` (hard-fail if the
   gate is open) is endorsed as further hardening.

3. **[CTO-ADV-1] Re-resolve the three *used* action SHAs + the hatchling pin at author time.**
   Re-resolve and verify (same `git ls-remote` / PyPI method the spec documents):
   `actions/checkout`, `astral-sh/setup-uv`, `actions/attest-build-provenance`, and the
   `[build-system] requires` `hatchling==` pin (the spec's `1.27.0` is explicitly illustrative —
   pin current-latest). Re-run `uv lock` and commit the updated `uv.lock` after the hatchling
   pin change. Do **NOT** add the two pins research.md lists but the authored workflows do not
   use (`pypa/gh-action-pypi-publish`, `actions/setup-python`) — their omission is deliberate
   (`uv publish` replaces the former; `setup-uv` manages Python).

4. **[QA-ADV-1/2/6] Durable static-assertion verification is the test scope.**
   The meaningful, re-runnable verification for this config/YAML/docs change is static, not
   unit-test-of-application-logic. Implement (as CI steps and/or a small `tests/test_ci_config.py`
   that parses the YAML and asserts invariants): `actionlint` on all three workflows; the AC2
   SHA-pin coverage grep returns zero unpinned actions; `ci.yml` has `enable-cache: true` while
   `release.yml`/`audit.yml` have `enable-cache: false` (AC3); the 3.11/3.13 matrix is present
   (AC7); `release.yml` contains `id-token: write` + `environment: pypi` and no `PYPI_TOKEN`
   secret exists (AC5); `docs/dependency-intake.md` contains its seven enumerated checklist
   sections (AC6, beyond mere file existence). Side-effect-only ACs (AC4 provenance, AC5
   Environment, AC8 version-guard mismatch) stay runbook/`workflow_dispatch --skip_publish`
   dry-run verified — do not attempt to unit-test OIDC/provenance/publish.

## Phase-exit / tracking actions (chair to action at phase exit; impl to confirm)

5. **[CPO-A3] File follow-up ticket(s) for deferred work** before this ticket closes: the
   bandit / pip-licenses / gitleaks OSS-hygiene scanner suite, and the SECURITY.md /
   responsible-disclosure artifact (due at first public tag). Ensures "deferred" is tracked,
   not silently dropped.

6. **[CPO-A2] Retitle the PR/ticket** to reflect the true scope — "establish CI + supply-chain
   hardening" rather than a small security tweak — so future audit/roadmap reviews read it
   correctly. Hygiene; no code impact.

## Rationale

Items 1–4 are genuine acceptance criteria for the implementing phase, not retrospective
commentary: each names a concrete, verifiable obligation that the spec body either leaves to
author-time (3), states as a manual/eyeball step that should be hardened into a real gate (2),
or does not fully cover for a greenfield rollout (1, 4). Item 1 is load-bearing because it is
the difference between landing working CI and red-lining `main` on day one. Items 5–6 are
phase-exit tracking obligations raised by the CPO to prevent scope-deferral drift and keep the
audit trail honest; they are recorded here so they survive into the next phase's Task Intake.
None of these reopen the spec design — the council APPROVED it unanimously with zero blocking
findings — they direct the implementation to execute the design's intent safely.
