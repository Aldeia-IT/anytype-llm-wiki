# Technical Re-Review — Round 2 (CTO): Supply-Chain Security Hardening (#231)

**Date:** 2026-05-30
**Reviewer:** chief-technology-officer
**Spec under review:** `spec.md` @ commit `91fbfc4` (revised)
**Baseline:** `review-r1.md` (B1, SF-1..SF-10, SG-1..SG-4)
**Mandate:** Verify disposition honesty + internal consistency + implementability after the fix round. Verification pass, not a re-review.

## Verdict: APPROVED

The fixer's claim of "all resolved, zero open" is **honest**. I independently located every claimed fix in the spec body (not just in the disposition table), verified the 5 SHA pins are still verbatim from `research.md`, confirmed the SF-3 prose/diagram/workflow now agree, and executed the load-bearing commands (`uv version --short`, `uv export`) to confirm B1/SF-5 steps are concrete. No BLOCKING or SHOULD-FIX findings remain. Two minor SUGGESTIONs below are non-blocking.

---

## 1. Disposition honesty — every R1 finding confirmed in the spec body

Each confirmed by locating the actual change, not trusting the disposition table (spec §"Round 1 Review Findings — Disposition", lines 1216–1254).

- **B1 (version guard)** — CONFIRMED. `release.yml` `build-and-publish` job has a `Verify tag matches pyproject version` step (lines 745–754) gated `if: github.event_name == 'push'`, running *before* `uv build` (line 759). AC8 (lines 621–627) traces it. Real fix, not hand-wave.
- **SF-1 (drop `--dev`)** — CONFIRMED. Canonical command is `uv sync --frozen --all-extras` (§1 lines 198–212); the bogus `--dev` flag is gone from ci.yml (line 669) and prose. The rationale (dev is a PEP 621 extra, no `[dependency-groups]`/`[tool.uv]` table) matches the actual `pyproject.toml` (verified: `dev` under `[project.optional-dependencies]` line 18-19, no `[tool.uv]` / `[dependency-groups]`).
- **SF-2 (release-path lockfile check)** — CONFIRMED. `uv lock --check` present in BOTH release jobs: `audit` (line 713) and `build-and-publish` (line 741), plus `audit.yml` (line 513). AC1 (lines 560–569) documents the both-jobs requirement.
- **SF-3 (prose/diagram/workflow reconciled)** — CONFIRMED, this is the key R1 inconsistency. See §2 below — all three agree on `pip-audit` only; bandit/pip-licenses/gitleaks deferred with rationale (lines 129–141, Deferred Items lines 1276–1282).
- **SF-4 (`workflow_dispatch` + `skip_publish`)** — CONFIRMED. Promoted into authored `release.yml` `on:` block (lines 689–694) and the publish step `if: inputs.skip_publish != true` (line 768). No longer Test-Plan-only.
- **SF-5 (Environment as hard prereq AC)** — CONFIRMED. Elevated to AC5 (lines 589–606) with concrete `gh api repos/.../environments/pypi` verification, fail-open framing (lines 418–449), and plan-tier note (public repo = free, lines 440–446). First-release checklist step 5 (lines 948–955).
- **SF-6 (audit perimeter / merge window)** — CONFIRMED. New `audit.yml` weekly cron `0 6 * * 1` full-tree `--all-extras` (§6a lines 485–520) PLUS named accepted residual risk (Security Considerations lines 904–917).
- **SF-7 (build backend not frozen)** — CONFIRMED. §3b (lines 281–310) pins `[build-system] requires = ["hatchling==1.27.0"]` with explicitly accepted residual (transitive build deps still fresh). Deliverable matrix row (line 552), Impl step 6 (lines 1143–1146).
- **SF-8 (partial-failure recovery)** — CONFIRMED. Operational Considerations (lines 962–983) documents the burned-version / bump-patch-and-retag path, with honest "PyPI is immutable, no skip-existing flag" reasoning.
- **SF-9 (Python matrix)** — CONFIRMED. `ci.yml` `strategy.matrix.python-version: ["3.11", "3.13"]` (line 654), `fail-fast: false`. AC7 (lines 614–619). Matches `requires-python = ">=3.11"`.
- **SF-10 (redundant `uv sync` removed)** — CONFIRMED. No `uv sync` in `build-and-publish`; explicit NOTE comment explains why (lines 756–758). Not "resolved by deletion of evidence" — the rationale (isolated build env) is sound.
- **SG-1 (`docs/releasing.md`)** — CONFIRMED. Deliverable row (line 554), Impl step 8 (lines 1151–1157).
- **SG-2 (dry-run over `act`; pin pip-audit; act off-host)** — CONFIRMED. `pip-audit@2.10.0` pinned (lines 519, 721); Test Plan prefers `workflow_dispatch` dry-run, `act` flagged for off-host due to Colima 2GB cap (lines 1011–1037).
- **SG-3 (README consumer snippet lands)** — CONFIRMED. Promoted optional→required, deliverable row (line 556), Impl step 10 (lines 1170–1177).
- **SG-4 (carry specialist suggestions)** — CONFIRMED. Each enumerated in the disposition table (lines 1238–1250: sec-SG-1..6, infra-G2/G4, tech-SG-1..4) with a where-pointer. Spot-checked tech-SG-3 (orphaned CACHE node) — now `CACHE --> LC` (line 169). Verified, not just claimed.

No finding is "resolved by deletion" or hand-wave. The disposition is complete and accurate.

## 2. SF-3 — no new contradiction (the specific R1 inconsistency)

Verified all three artifacts agree the tag-gate security scan is **`pip-audit` only**:
- **Prose:** §Design Principle scope decision (lines 129–141): "implements exactly ONE security-analysis tool: `uvx pip-audit`"; bandit/pip-licenses/gitleaks "deliberately deferred."
- **Mermaid diagram:** RELEASE subgraph (lines 157–170) contains exactly one audit node `AUDIT["uvx pip-audit"]` (line 160). No bandit/license/secret nodes.
- **Workflow:** `release.yml` `audit` job runs only `uvx pip-audit@2.10.0` (line 721). No other scanners.

Deferral rationale is honest (general OSS hygiene vs. rotki measures; minimize first-release surface; each adds human-triage failure mode). No scope creep. No new prose/diagram/workflow drift introduced by the edits — I also checked the merge-gate diagram subgraph matches `ci.yml` (lock-check → frozen install → matrix test) and the OIDC sequence diagram (lines 386–401) matches §5 prose.

## 3. AC traceability intact

- **AC1–AC8 all map** to deliverable + verification (Deliverables matrix lines 546–556; AC detail lines 558–627).
- **AC7/AC8 are legitimate, not padding.** AC7 (Python matrix) is the SF-9 deliverable; AC8 (version guard) is the B1 deliverable. Both are concrete, testable, and trace to real R1 findings. Adding them is the correct way to make those fixes auditable.
- **New deliverables present in the matrix:** `docs/releasing.md` (line 554), `pyproject.toml` build-system pin (line 552), `README.md` snippet (line 556), `audit.yml` (line 550). All accounted for.
- **Open Questions actually moved out.** OQ#1/2/3 are in a "None open" section (lines 1198–1212) with resolutions, and each resolution is reflected in the body (OQ#1 → docs/releasing.md, OQ#2 → --all-extras, OQ#3 → conditional pip fallback). Not merely relabeled — the substance migrated into §1, §Dependabot, Impl steps.

## 4. SHA pins unchanged — verified verbatim against research.md

Grepped `research.md` for all 5 SHAs (lines 619–623 table + usage examples). Spot-checked ≥2:
- `actions/checkout` v6.0.2 → `de0fac2e4500dabe0009e67214ff5f5447ce83dd` — matches spec lines 71, 224, 656, 704, 733, 509.
- `astral-sh/setup-uv` v8.1.0 → `08807647e7069bb48b6ef5acd8ec9567f424441b` — matches spec lines 72, 225, 268, 658, 706, 735.
- `actions/attest-build-provenance` v4.1.0 → `a2bbfa25...` — matches lines 73, 226, 322, 763.
- The annotated-tag dereference note for `pypa/gh-action-pypi-publish` (research line 622 "annotated tag, ^{} used") is preserved in spec (lines 77–79). Note: `pypa/gh-action-pypi-publish` and `actions/setup-python` SHAs appear in research but are NOT used in the authored workflows (both are rejected approaches — uv publish chosen over the pypa action; setup-uv manages Python). Correct and consistent.

The fix round did not alter any pin.

## 5. Implementability

- **Implementation Plan** (lines 1111–1194) is ordered and coherent: dir scaffold → workflows → pyproject pin → docs → CONTRIBUTING (correctly depends on docs paths, noted in Parallelization lines 1188–1194) → README → SHA-coverage grep → PR. No ordering contradictions introduced.
- **B1 guard executable — verified live.** `uv version --short` returns `0.1.0` (matches `pyproject.toml` line 3). `${GITHUB_REF_NAME#v}` shell strip is standard. The guard is concrete and runnable.
- **SF-5 verification executable.** The `gh api repos/.../environments/pypi` calls are well-formed; this is the right way to make a fail-open control verifiable.
- **Audit export executable — verified live.** `uv export --format requirements-txt --no-dev` and `--all-extras` both run (exit 0) on this repo; `requirements-txt` is accepted as the format alias. `uvx pip-audit@2.10.0 -r ...` is a sound pinned-tool invocation.

## 6. Scope

No scope creep. The only additions (audit.yml, build-backend pin, matrix, docs/releasing.md, README snippet) are direct R1-finding deliverables. Deferrals (bandit/pip-licenses/gitleaks, uv audit migration, Renovate, full build-env hash-locking, SECURITY.md) are enumerated in §Deferred Items (lines 1258–1287) each with honest rationale. The B1 "guard step vs hatch-vcs" choice is documented in Alternatives Considered (lines 1293–1300) with a defensible rationale (smaller, contained change).

---

## Remaining findings

### SUGGESTION SG-a — Implementer must pin the REAL latest hatchling, not the illustrative `1.27.0`
**Verified:** §3b line 295 pins `hatchling==1.27.0` with the parenthetical "1.27.0 is illustrative" (line 299), and Impl step 6 says resolve current latest at authoring time.
**Impact:** If the implementer copy-pastes `1.27.0` without checking, the pin could lag or (worse) name a nonexistent version, breaking `uv build`. Low risk because the step text is explicit, but the illustrative value in a code block invites copy-paste.
**Action:** Implementer resolves and verifies the actual latest hatchling (the same `git ls-remote`/PyPI check used for SHAs) before committing; re-run `uv lock` after. Non-blocking — spec already instructs this.

### SUGGESTION SG-b — Operational checklist step numbering (cosmetic)
**Verified:** First-release checklist (lines 940–957): step 6 reads "the B1 guard will abort ... this is the safety net, not a substitute for step 6" — the self-reference ("substitute for step 6") should read "step 4" (PyPI publisher) or be reworded.
**Impact:** None functional; minor reader confusion in the runbook summary.
**Action:** Fix the cross-reference when authoring `docs/releasing.md` (which is the authoritative copy per line 937). Non-blocking.

---

## Confirmation: resolved findings (one line each)
- B1 ✓ version guard before build, AC8. SF-1 ✓ `--all-extras`, no `--dev`. SF-2 ✓ lock-check in both release jobs + audit.yml. SF-3 ✓ prose/diagram/workflow agree on pip-audit only. SF-4 ✓ workflow_dispatch+skip_publish authored. SF-5 ✓ AC5 hard prereq + gh api verify. SF-6 ✓ weekly audit.yml + named residual. SF-7 ✓ build-system pin + residual. SF-8 ✓ bump-patch-and-retag recovery. SF-9 ✓ 3.11/3.13 matrix, AC7. SF-10 ✓ redundant uv sync removed. SG-1 ✓ docs/releasing.md deliverable. SG-2 ✓ pinned pip-audit, act off-host. SG-3 ✓ README snippet required. SG-4 ✓ specialist suggestions enumerated + addressed.

---

## Sign-off

**APPROVED.** The fix round is honest and complete — every R1 finding is materially addressed in the spec body, the SF-3 prose/diagram/workflow inconsistency is genuinely reconciled, the 5 SHA pins are unchanged and verbatim from research, AC traceability (incl. legitimate AC7/AC8) is intact, Open Questions are truly closed, and the B1/SF-5 verification steps execute against this worktree. No BLOCKING or SHOULD-FIX issues remain. The two SUGGESTIONs are implementation-time hygiene, not spec defects. This spec is implementable as written.

**Finding counts:** 0 BLOCKING, 0 SHOULD-FIX, 2 SUGGESTION.
