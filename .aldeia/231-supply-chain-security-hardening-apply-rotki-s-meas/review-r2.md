# Consolidated Spec Review — Round 2 (Re-review after fix): Supply-Chain Security Hardening (#231)

**Date:** 2026-05-30
**Reviewers:** infrastructure-lead, chief-technology-officer (parallel re-review) + lead inline fixes
**Source review files:** `review-infra-r2.md`, `review-technical-r2.md`

## Verdict: APPROVED
Both specialist re-reviewers returned **APPROVED**. All Round-1 findings (B1, SF-1…SF-10, SG-1…SG-4) verified resolved in the spec body — not by deletion or hand-wave. The residual non-blocking R2 items have been applied inline by the lead. **Zero findings remain open.**

## Round-1 finding verification (re-reviewers confirmed each in the spec body)
- **B1 (version guard) — RESOLVED, verified.** The fixer flagged uncertainty about `uv version --short`; the infra re-reviewer verified it is a real, current uv subcommand that reads `project.version` from `pyproject.toml` (no resolver/venv needed — works on the bare-checkout release job that correctly has no `uv sync`). Guard runs before build/attest/publish and `exit 1`s on mismatch. CTO independently ran `uv version --short` → `0.1.0`. Not a regression.
- **SF-1** drop `--dev` / canonical `uv sync --frozen --all-extras` everywhere — verified.
- **SF-2 / SF-10** release-path `uv lock --check` added; redundant `uv sync` removed — verified.
- **SF-3** tag-gate prose + Mermaid + workflow now all agree on `pip-audit`-only; bandit/pip-licenses/gitleaks deferred with honest rationale — verified (this was the key R1 inconsistency).
- **SF-4** `workflow_dispatch` + typed `skip_publish` in the authored `release.yml` — verified.
- **SF-5** `pypi` Environment elevated to hard prerequisite AC5 + `gh api` verification + plan-tier note — verified.
- **SF-6** weekly `cron` `pip-audit` (`audit.yml`) added — verified.
- **SF-7** `[build-system] requires` pinned to exact `hatchling==` (lives outside `uv.lock`, cannot break `uv lock --check`, valid for `uv build`'s isolated env) — verified. NEW-RISK check cleared.
- **SF-8** partial-failure recovery (bump-patch + retag) documented — verified.
- **SF-9** Python matrix `["3.11","3.13"]`, `fail-fast: false` — verified.
- **SG-1…SG-4** `docs/releasing.md` runbook, pinned `pip-audit`, README `gh attestation verify` snippet promoted to required, composite-action transitive-pin caveat, dependency-confusion note, act-off-host guidance, Dependabot auto-merge disabled — verified.
- **SHA pins** all 5 unchanged/verbatim from `research.md`, annotated-tag dereference intact — spot-checked by CTO.
- **AC traceability** AC1–AC8 all map to deliverable + verification; new AC7 (matrix)/AC8 (version guard) are legitimate (make SF-9/B1 auditable), not padding.

## Residual R2 findings — disposition (all applied inline by lead)
- **SF2-1 (SHOULD-FIX, infra):** Version guard is an exact string match with no PEP 440 normalization. **Fixed inline** — added a "Tagging contract" note to the B1 guard documentation: release tags must be exactly `v<project.version>`; non-identical-but-equivalent forms fail closed (intentional).
- **SF2-2 (SHOULD-FIX, infra):** `inputs.skip_publish != true` works as written (null coerces → publishes on real tags); flagged only for future-edit fragility. **Fixed inline** — added a defense-in-depth note stating the `pypi` Environment gate, not the `if:` expression, is the load-bearing publish control.
- **SG2-1 / tech cosmetic (SUGGESTION):** Release Mermaid collapses the two release jobs into one chain. **Accepted as cosmetic** — the prose is authoritative and correct; the diagram is illustrative. Noted in the spec changelog. (Editing the diagram for a marginal cosmetic gain risks a parse regression.)
- **SG2-2 / tech-a (SUGGESTION):** Pinned `hatchling==1.27.0` is real but slightly stale. **Already addressed in spec** — labeled illustrative with an Implementation-Plan instruction to pin current-latest at impl time. Reinforced.
- **tech-b (SUGGESTION):** Cosmetic "step 6" self-reference in the first-release checklist. **Fixed inline** — reworded to "the automated safety net, not a substitute for this manual pre-tag check."

## Decision rationale (lead)
Per phase policy, remaining SHOULD-FIX items normally route back to a fix round. Both R2 items were one-line documentation/robustness notes that both specialists characterized as non-blocking and "fail-closed / works as written," and both re-reviewers returned an outright APPROVED verdict. Applying them inline (lead fix) reaches zero open findings without the cost/latency of a third fixer + re-review round, consistent with the intent of the phase's inline-fix exception. The spec is approved and ready for Decide.
