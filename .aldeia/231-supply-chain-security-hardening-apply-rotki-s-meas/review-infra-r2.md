# Infrastructure Re-Review (Round 2) — Supply-Chain Security Hardening (#231)

**Reviewer:** infrastructure-lead
**Date:** 2026-05-30
**Spec:** `.aldeia/231-supply-chain-security-hardening-apply-rotki-s-meas/spec.md` (revised, commit 91fbfc4)
**Baseline:** `review-r1.md` (1 BLOCKING + 10 SHOULD-FIX + 4 SUGGESTION)
**Scope:** verify infra/CI-CD-relevant R1 fixes are correct; flag regressions.

---

## Verdict: APPROVED

All infra-relevant R1 findings are correctly resolved. No new BLOCKING issues. The
one item the fixer flagged as uncertain (B1's `uv version --short`) is verified correct.
Findings below are 2 SHOULD-FIX (documentation/robustness, non-blocking) and 2 SUGGESTION.

**Finding counts:** 0 BLOCKING, 2 SHOULD-FIX, 2 SUGGESTION.

---

## B1 — Version guard: VERIFIED CORRECT (fixer's uncertainty resolved)

The fixer flagged uncertainty about whether `uv version --short` exists in the runner's uv.
**Confirmed: `uv version --short` is a real, current uv subcommand.**

- Per uv CLI reference (docs.astral.sh/uv/reference/cli), `uv version` reads/updates the
  *project* version (i.e. `project.version` in `pyproject.toml`). The `--short` flag prints
  only the version number (no project-name prefix).
- This is the post-uv-0.7.0 behavior: before 0.7.0, `uv version` printed uv's own version;
  that moved to `uv self version`, freeing `uv version` for project-version management
  (uv issues #6298, #7609, #8755).
- `astral-sh/setup-uv@v8.1.0` installs a current uv (far past 0.7.0), so the subcommand is
  present on the runner. No regression — the guard mechanism is sound.
- `uv version` reads the manifest directly; it does NOT require a synced `.venv` or resolver
  run. This matters because the `build-and-publish` job has no `uv sync` (correctly removed
  per SF-10) — the guard still works on a bare checkout. Confirmed safe.

**Ordering / abort behavior — correct:**
- The `Verify tag matches pyproject version` step sits in `build-and-publish` BEFORE
  `Build distributions`, `Attest`, and `Publish`. A mismatch `exit 1`s the step, which fails
  the job before any artifact is built/attested/published. PyPI-immutability burn is avoided.
- `${GITHUB_REF_NAME#v}` correctly strips the leading `v` (`v0.2.0` -> `0.2.0`).
- The `if: ${{ github.event_name == 'push' }}` gate correctly skips the guard on
  `workflow_dispatch` dry-runs (no `v*` tag to compare). Sound.

B1 is correctly resolved.

---

## SHOULD-FIX

### SF2-1 — Version-guard tag-format edge case not handled (robustness)

The guard compares `${GITHUB_REF_NAME#v}` against `uv version --short` with a literal `!=`.
This is correct for the happy path, but two realistic tag shapes silently behave oddly:

- A non-version tag that still matches `v*` (e.g. `v-rc`, `vnext`, `vlatest`) reaches the
  guard. `${GITHUB_REF_NAME#v}` yields e.g. `-rc`, which won't equal the manifest version,
  so the guard fails closed (good) — but with a confusing error rather than "this isn't a
  release tag." Low risk, acceptable.
- A pre-release tag (`v0.2.0rc1`) vs a manifest at `0.2.0rc1`: `uv version --short`
  normalizes PEP 440 versions, so `1.0` could print as `1.0` while a tag `v1.0.0` would
  mismatch. The current static manifest (`0.1.0`) is fine, but the guard does no PEP 440
  normalization on the tag side.

**Operational impact:** Low. The guard fails closed in all ambiguous cases, so it cannot
cause a wrong-version publish — worst case is a release blocked with a terse error. No
stability risk.

**Recommended action:** Add one sentence to the §release.yml notes (or `docs/releasing.md`)
stating the guard is an exact string match and release tags must be exactly `v<project.version>`
with no pre-release/normalization mismatch. Optional hardening: echo a clearer message when
the stripped tag is empty/non-numeric. Non-blocking.

### SF2-2 — `inputs.skip_publish != true` evaluates true on real tag pushes (verify, document)

On a `push` (tag) event, `inputs.skip_publish` is null/unset. The expression
`${{ inputs.skip_publish != true }}` evaluates to `true` for null, so the publish step runs
on a real tag — which is the intended behavior, and the spec prose (§5) states this
correctly. This is CORRECT as written; flagging only because the boolean/null coercion is
the kind of thing that breaks silently if edited later.

**Operational impact:** None currently. The publish gate works. Risk is future-edit fragility.

**Recommended action:** Keep the explicit prose note already in §5 ("a real `v*` tag push
where `inputs.skip_publish` is null always publishes"). Optionally make the intent
self-documenting in the workflow with `if: ${{ inputs.skip_publish != true }}` plus a short
inline comment. The `environment: pypi` reviewer gate is the real backstop and applies to
the whole job regardless, so even a logic slip here cannot bypass review. Non-blocking.

---

## SUGGESTION

### SG2-1 — Mermaid release diagram collapses two jobs / two lock-checks into one chain

The release Mermaid (`RLC --> AUDIT --> GUARD --> BUILD --> ATTEST --> PUBLISH`) renders the
tag-gate as a single linear chain, but the authored workflow splits it into two jobs:
`audit` (RLC + AUDIT) and `build-and-publish` (`needs: audit`; RLC + GUARD + BUILD + ATTEST +
PUBLISH). The diagram shows only one `RLC` node though `uv lock --check` runs in BOTH jobs.
The prose (lines 173-176) clarifies this correctly, so there is no contradiction in intent —
only a diagram that under-represents the job boundary and the second lock-check.
**Action:** optionally add a `needs: audit` boundary and a second RLC node to the diagram for
fidelity. Diagram parses fine; cosmetic.

### SG2-2 — Pinned hatchling example (`1.27.0`) is now two minors stale

`[build-system] requires = ["hatchling==1.27.0"]` — `1.27.0` is real (released 2024-12-15)
but current latest is `1.29.0` (2026-02). The spec explicitly labels `1.27.0` as
"illustrative" and instructs the implementer to pin current-latest at authoring time, so this
is NOT a defect. Note for the implementer: pin `hatchling==1.29.0` (or whatever is current at
implementation), run `uv lock`, commit the updated `uv.lock`. The pin is well-formed
(`==` exact) and lives in `[build-system] requires`, which is NOT part of `uv.lock` — so it
cannot cause a `uv lock --check` failure (SF-7 NEW-RISK check: clear). `uv build` reads
`[build-system] requires` to provision the isolated build env; an exact pin there is valid
and standard. No `uv build` breakage risk.

---

## R1 finding-by-finding disposition (infra-relevant)

- **B1 (version guard):** RESOLVED. `uv version --short` verified real/current; runs before
  build/attest/publish in `build-and-publish`; aborts the whole release on mismatch; works
  without a synced venv. Correct.
- **SF-1 (`--dev` removed):** RESOLVED. Canonical `uv sync --frozen --all-extras` is
  consistent across ci.yml, release/audit usage, and the CONTRIBUTING edit spec
  (Impl step 9). `--dev` dropped everywhere. (Committed `CONTRIBUTING.md` still shows
  `--extra dev` — expected; this is a spec, the edit is specified not yet applied.)
- **SF-2 (release-path lock check):** RESOLVED. `uv lock --check` present in BOTH `audit`
  and `build-and-publish` jobs, and in `audit.yml`. Correct.
- **SF-10 (redundant `uv sync` removed):** RESOLVED. No `uv sync` before `uv build`;
  inline comment explains the isolated-build rationale. Correct.
- **SF-4 (`workflow_dispatch` + `skip_publish`):** RESOLVED. Present in the authored
  `release.yml` `on:` block with a typed boolean input defaulting to `false`, plus the
  guarded publish step. Correct.
- **SF-7 (hatchling pin NEW-RISK):** RESOLVED, no regression. Pin is well-formed `==`,
  hatchling version is real, lives outside `uv.lock` so no lock-consistency break, valid for
  `uv build`'s isolated env. Residual risk (transitive build deps unfrozen) is explicitly
  documented and accepted. Correct.
- **SF-9 (Python matrix):** RESOLVED. `strategy.matrix.python-version: ["3.11", "3.13"]` with
  `fail-fast: false`; `uv python install` + `--python ${{ matrix.python-version }}` on sync
  and run. Matrix syntax valid. Correct.
- **SF-5 (Environment prereq + `gh api` check):** RESOLVED. `environment: pypi` on the job;
  AC5 makes protection a hard prerequisite; `gh api .../environments/pypi` +
  `.../deployment-branch-policies` verification steps present in AC5, Operational checklist,
  and Test Plan; fail-open nature stated; public-repo plan-tier note correct. Operationally
  sound. (Overlaps CSO domain — defer auth/network-exposure judgment to CSO.)
- **SF-8 (partial-failure recovery):** RESOLVED. §Operational Considerations documents the
  four failure modes (guard fail / attest-ok-publish-fail / partial upload / burned version)
  and the bump-patch-and-retag recovery for an immutable PyPI. Correct and operationally
  realistic; correctly rejects a skip-existing flag.

## General checks

- **YAML semantics:** triggers (`push.branches`/`pull_request` on ci; `push.tags`/
  `workflow_dispatch` on release; `schedule`/`workflow_dispatch` on audit) are valid.
  `needs: audit` wiring correct. Permissions are least-privilege: top-level `contents: read`
  everywhere; elevated `id-token: write` + `attestations: write` scoped to `build-and-publish`
  only. No regressions.
- **SHA pins:** unchanged from R1 (CTO-verified verbatim); `audit.yml` reuses the same pinned
  checkout/setup-uv SHAs. Consistent.
- **Prose/diagram/workflow consistency:** tag-gate security scope reconciled to `pip-audit`
  only (SF-3) across prose, diagram, and workflow. No new contradictions found (the SG2-1
  diagram simplification is cosmetic, prose corrects it).
- **Resource/host impact:** GitHub-hosted-only; zero steady-state Mac Mini load; the
  `act`-on-Colima caveat (SG-2) is correctly host-aware (dry-run on the Mini, full run
  off-host). No launchd/Docker/service/backup changes. "Negligible host impact" claim stands.

---

## Sign-off

**APPROVED** from the infrastructure perspective. The blocking B1 guard is verified correct
(including the `uv version --short` mechanism the fixer was unsure about), no infra
regressions were introduced by the fix round, and the two SHOULD-FIX items are
documentation/robustness polish that fail closed and carry no deployment-stability risk.
They can be folded into implementation without another spec round. CSO should independently
confirm SF-5's Environment-protection and OIDC trust-boundary claims, which overlap the
security domain.
