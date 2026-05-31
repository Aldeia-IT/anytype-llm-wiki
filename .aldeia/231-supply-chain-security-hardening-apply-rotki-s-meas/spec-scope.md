# Spec Scope: supply-chain-security-hardening

**Ticket:** Aldeia-IT/aldeia-box#231
**Source:** rotki security blog (2026-05-22) — apply their supply-chain hardening measures.

## Domains touched
- Infrastructure / CI-CD (GitHub Actions workflows — currently none exist)
- Security (supply-chain: lockfile pinning, SHA-pinned actions, cache-poisoning defense, provenance, OIDC)
- Conventions (dependency-intake review process; CONTRIBUTING.md)

## Estimated complexity: moderate
Greenfield CI: the repo has **no `.github/` directory at all**. So this spec both
establishes CI workflows from scratch AND bakes in the rotki hardening measures.
Single package ecosystem only — **Python/uv**. There is no Node/pnpm and no
Rust/cargo in this repo, so measures #2 (prefer pnpm) and the cargo half of #1 are
**Not Applicable** and the spec must say so explicitly rather than inventing
workflows for ecosystems that don't exist.

## Applicability matrix (rotki measures → this repo)
1. Frozen lockfile installs — **uv only**: `uv sync --locked` (or `uv sync --frozen`)
   in every CI job. pnpm/cargo N/A.
2. Prefer pnpm over npm — **N/A** (no Node ecosystem).
3. Cache-free release builds — **applies**: release/publish workflow uses
   `enable-cache: false` on `astral-sh/setup-uv`. Dev/test CI keeps cache.
4. SHA-pin all GitHub Actions — **applies** to all actions we add.
5. Build-provenance attestations — **applies where published**: PyPI sdist+wheel via
   `actions/attest-build-provenance`. PyPI publishing is roadmap (README "pip install",
   roadmap "npm / PyPI publishing") — not yet live, so this is the publish workflow
   we author now, gated to tags/releases.
6. OIDC Trusted Publishing — **applies where published**: `pypa/gh-action-pypi-publish`
   with `id-token: write`, no long-lived PyPI token. Tag/release-gated.
7. Dependency-intake review — **applies**: documented checklist in the repo
   (likely `docs/dependency-intake.md` + a pointer from CONTRIBUTING.md).

## Key prior learnings to inject (from Mem0)
- Council intent (#140/wiki port): minimal CI = pytest + `uv lock --locked` (lockfile
  consistency check) + pip-audit + gitleaks, landed so every PR diffs against a gated
  baseline. (mem0 3a9375f9)
- Supply-chain / security-license gates (pip-audit, bandit, gitleaks, pip-licenses) and
  OSS-hygiene artifacts are **TAG-gating, not MERGE-gating**. Merge-gate = fast tests +
  lockfile consistency; tag-gate = the heavier security/provenance/publish steps.
  (mem0 0ae961bc)
- SECURITY.md expected at first public tag; private disclosure channel. Adjacent —
  reference but do not duplicate scope. (mem0 c942da7e, c1e5e299)
- Git tag/push ceremonies themselves run in the watcher (unsandboxed bash); the
  workflow YAML lives in the repo and is triggered by tag push. (mem0 6f927d62)

## Files at risk of staleness / needing update
- No CLAUDE.md exists (note absence in worker prompts).
- `CONTRIBUTING.md` — add/point to dependency-intake checklist.
- `README.md` — install/publishing section; provenance verification note (where applicable).
- `.aldeia/context/technical.md` — may want a CI/supply-chain posture note (defer to impl).

## Open questions for research
- Does `uv sync --locked` vs `uv sync --frozen` differ for CI intent? Which to mandate?
- Current recommended pinned SHAs for: `actions/checkout`, `astral-sh/setup-uv`,
  `actions/attest-build-provenance`, `pypa/gh-action-pypi-publish`, `actions/setup-python`.
- Does `uv build` + `pypa/gh-action-pypi-publish` (OIDC) compose cleanly, or should we
  use `uv publish --trusted-publishing`? Which is the current best practice (2026)?
- How to keep SHA pins maintainable (Dependabot/Renovate with SHA pinning)?
- pip-audit vs `uv`-native audit — what's the current state?
