# Security Review — Supply-Chain Hardening Spec (#231)

**Reviewer:** Chief Security Officer (council)
**Date:** 2026-05-30
**Artifact:** `.aldeia/231-supply-chain-security-hardening-apply-rotki-s-meas/spec.md`
**Scope:** Strategic supply-chain security posture of the spec (not line-by-line implementation).

---

## Verdict: APPROVED WITH CONDITIONS

The spec is strategically sound. It correctly identifies the rotki threat surface,
maps it to a Python/uv-only repo, and proposes a coherent merge-gate/tag-gate split with
OIDC trusted publishing (no long-lived secrets), full SHA pinning, cache-free release
builds, and provenance attestation. The threat model is largely complete and the
least-privilege permissions discipline is good.

Conditions for sign-off are two SHOULD-FIX items that, if shipped as-written, would cause
the release pipeline to either fail or silently under-cover the threat surface it claims
to close. None rise to BLOCKING because they are mechanical corrections, not architectural
flaws.

**Findings: 0 BLOCKING / 4 SHOULD-FIX / 6 SUGGESTION**

---

## SHOULD-FIX

### SF-1 — `uv sync --frozen --all-extras --dev` references a non-existent dependency group

**Spec sections:** §1 (line 141, 153-154), §release.yml (line 494), ci.yml (line 441),
Open Question 2 (lines 760-765).

The repo's `pyproject.toml` declares `dev` under `[project.optional-dependencies]`
(line 18-19) — i.e. `dev` is an **extra**, not a PEP 735 `[dependency-groups]` entry.
There is no `[dependency-groups]` and no `[tool.uv]` section in `pyproject.toml`
(verified). The `uv sync --dev` flag installs the `dev` **dependency-group**, which does
not exist here. Depending on uv version this is either a no-op (silently installing
nothing extra) or an error.

The intended effect (install pytest) is already covered by `--all-extras`, so `--dev` is
at best redundant and at worst breaks the install step that every gate depends on.

This matters for security because the *install command is the foundation the entire merge
and release pipeline stands on* — if it errors, no gate runs; if it silently does the
wrong thing, the spec's verification claims (AC1) are not actually exercised.

**Fix:** Drop `--dev` everywhere. Standardize on `uv sync --frozen --all-extras`. OR
migrate `dev` from `[project.optional-dependencies]` to `[dependency-groups]` (PEP 735)
and use `uv sync --frozen --all-groups` — but that is a larger change and should be its
own decision. Pick one and make it consistent across ci.yml, release.yml, CONTRIBUTING.md,
and resolve Open Question 2 in the spec rather than deferring it to the implementer.

### SF-2 — pip-audit audits only runtime deps, and the tag-gate is the *only* place deps are scanned

**Spec sections:** §release.yml audit job (lines 471-475), Research §Q7 (lines 519-531),
Merge-Gate vs Tag-Gate design principle (lines 93-107).

Two coupled concerns:

1. **Audit input excludes a layer.** The audit exports with `--no-dev`
   (`uv export --format requirements-txt --no-dev`). That is defensible for what ships in
   the wheel, but it means a vulnerable *dev/test* dependency (pytest plugins, transitive
   tooling) that executes inside the privileged release runner is never scanned. The
   release runner is exactly where `id-token: write` and `attestations: write` live — a
   compromised dev-time dependency running there is the higher-value target. Recommend a
   second audit pass over the full set, or at minimum a documented risk acceptance.

2. **Tag-gate-only scanning leaves a real merge window.** The design (correct per prior
   council guidance, mem0 0ae961bc) defers vuln/audit/secret scanning to tag time. The
   spec's own rationale (lines 105-107) acknowledges audits "require human triage." The
   accepted risk is: a PR introducing a vulnerable or malicious dependency **merges to
   `main` and sits there undetected until the next release tag**. For a low-frequency
   release cadence that window can be weeks. The dependency-intake checklist (§7) is the
   compensating control, but it is *manual and unenforced*. This is an acceptable tradeoff
   only if it is named as an explicitly accepted risk in the Security Considerations
   section — it currently is not.

**Fix:**
- Add a full-tree audit pass (without `--no-dev`) or justify the `--no-dev` scope in the
  Security Considerations section.
- Add an explicit "Accepted risk" note in §Security Considerations stating that
  dependency vulnerabilities introduced via PR are not detected until tag time, with the
  intake checklist as the named compensating control. Consider a lightweight
  `pip-audit` on a weekly `schedule:` cron (independent of release cadence) to shrink the
  window without blocking PRs — this is a cheap, high-value addition.

### SF-3 — `uv build` runs after a frozen sync but build isolation / backend trust is not addressed

**Spec sections:** §release.yml build-and-publish (lines 493-497), §4.

The release job runs `uv sync --frozen --all-extras` then `uv build`. `uv build` by
default builds in an **isolated** environment and fetches the build backend (`hatchling`,
per pyproject line 22-23) and its dependencies **from PyPI fresh**, governed by uv's
resolution — these build-time requirements are **not in `uv.lock`** and are therefore
**neither frozen nor audited**. This is a genuine gap in the "everything that touches a
release artifact is verified" claim: the build backend is unpinned and unscanned, yet it
executes arbitrary code to produce the very artifact being attested.

This is the Python analogue of the supply-chain surface the spec exists to close.

**Fix:** Document the build-backend trust assumption explicitly. Options, in order of
rigor: (a) pin build-system requires to exact versions in `[build-system] requires`
(e.g. `hatchling==X.Y.Z`) so the build dependency is at least version-locked and
reviewable; (b) note that `uv build` build-backend deps are resolved fresh and accept
that risk explicitly; (c) longer term, evaluate `--no-build-isolation` with a
pre-synced, locked build environment. At minimum the spec must acknowledge that
build-time dependencies are outside the lockfile/audit perimeter.

### SF-4 — GitHub Environment protection is the load-bearing control but is configured out-of-band and unverifiable in-repo

**Spec sections:** §5 GitHub Environment guardrail (lines 313-321), Operational
Considerations first-release checklist (lines 596-605), Security Considerations
(lines 566-571).

The entire defense against "a malicious tag push triggers an unreviewed publish" rests on
the `pypi` GitHub Environment having (a) required reviewers and (b) tag/branch restriction
configured in repo Settings. The workflow only declares `environment: pypi`; it cannot
enforce that the environment actually *has* protections. If the environment is created
without reviewers (or auto-created on first reference), `environment: pypi` becomes a
no-op label and any `v*` tag push from anyone with push access publishes to PyPI with the
OIDC identity — silently.

The spec correctly documents the manual setup, but treats a security-critical control as
an operational footnote. There is no in-repo verification or fail-closed mechanism.

Additionally: tag-protection in GitHub Environments historically gates by **branch**, and
tag-based deployment-branch policies have caveats. The spec says "Deployment branches:
restrict to protected tags matching `v*`" (line 318) — confirm this maps to a real,
currently-supported GitHub setting (deployment branch/tag policy with a `v*` tag rule) and
document the exact UI path, because if it silently falls back to "all branches" the gate
is open.

**Fix:**
- Elevate the environment-protection setup from "Operational Considerations" to a
  **hard prerequisite gate** in the AC: AC5 verification should include "confirm the
  `pypi` environment has at least one required reviewer AND a `v*` tag deployment rule"
  (verifiable via `gh api repos/{owner}/{repo}/environments/pypi`).
- Pair this with **GitHub repo setting "Require approval for all outside collaborators"**
  / restricted tag-creation protection so a malicious actor cannot create `v*` tags.
- State explicitly that environment protection is a fail-open control if misconfigured,
  and add the `gh api` verification command to the test plan.

---

## SUGGESTION

### SG-1 — Owner/repo naming consistency (Aldeia-IT vs aldeia-llm-wiki)

PyPI pending-publisher config (line 307) and provenance verify commands (lines 246-247,
393, 665-666, 728-729) use repo `Aldeia-IT/anytype-llm-wiki`. The git remote / actual repo
slug should be confirmed to match exactly (case-sensitive for the workflow filename and
exact for owner/repo in the trusted-publisher binding). A single-character mismatch
silently breaks OIDC validation at publish time. Add a verification step that the configured
PyPI publisher owner/repo/workflow/environment exactly match the live repo.

### SG-2 — Pin `pip-audit` version invoked via `uvx`

`uvx pip-audit` (line 475) resolves and runs the latest `pip-audit` from PyPI at release
time — itself an unpinned, network-fetched tool executing in the release context (though
in the lower-privilege `audit` job, not the publish job — good job separation). Pin it:
`uvx pip-audit@2.10.0` (or current) so the audit tool is reproducible and not itself a
moving supply-chain input. Same applies to any future `uvx bandit` / `uvx gitleaks` /
`uvx pip-licenses` steps the research mentions (Q7 lines 524-528).

### SG-3 — Transitive-action pinning of `pypa/gh-action-pypi-publish` is moot here (good), but note attest-build-provenance's transitive surface

The spec chose `uv publish` over `pypa/gh-action-pypi-publish`, eliminating that action's
transitive (internally-called) actions from the trust surface — a real security win, state
it as such. However `actions/attest-build-provenance@v4` is a composite/wrapper action
that internally invokes `actions/attest` and Sigstore tooling. Pinning the wrapper SHA does
**not** pin what the wrapper calls internally. This is an accepted, GitHub-maintained
transitive dependency, but the spec should note that SHA-pinning a composite action pins
only the top layer, not its internal `uses:`.

### SG-4 — 7-day cooldown is unenforced; name it as residual risk

§6 (lines 334-338) and the intake checklist rely on human discipline for the cooldown.
The spec is honest that Dependabot can't enforce it. Fine — but explicitly classify
"cooldown is convention, not control" as a residual/accepted risk. The Renovate
`minimumReleaseAge` alternative (deferred, lines 782-785) is the only enforcing option;
note that the accepted risk is reversible by adopting Renovate later.

### SG-5 — Dependabot PRs themselves are a write-path into the repo

Dependabot opens PRs against `main`. Those PRs run `ci.yml` (merge-gate), which does NOT
run audit/secret scanning (by design). A malicious or compromised dependency update could
merge after passing only tests + lockfile check. The spec advises human review (lines
588-590, 610-612) — good — but combined with SF-2 this is the same merge-window risk via a
second vector. Recommend Dependabot updates be subject to the same intake checklist /
cooldown discipline, and that auto-merge be explicitly disabled.

### SG-6 — Provenance covers GitHub attestations; PyPI-side attestations/index integrity not in threat model

§4/§5 note PyPI auto-generates Sigstore attestations for trusted-publishing uploads
(line 264-265). Good. But the consumer-side story (a downstream `pip install` user does
not verify provenance by default) is a known ecosystem limitation, not this repo's to
solve. Recommend the README snippet (step 7, lines 724-732) be promoted from "optional"
to "included," since publishing provenance nobody is told how to verify yields little
defensive value.

---

## Dimension-by-dimension assessment

- **Threat model completeness:** Strong. Tag-move (SHA pinning), cache-poisoning
  (cache-free release), token-theft (OIDC, no long-lived secret), lockfile tampering
  (`uv lock --check` + `--frozen`), and malicious-package intake (checklist) are all
  addressed. Gaps: build-backend deps outside the perimeter (SF-3); merge-window for
  vulnerable deps (SF-2). Dependency confusion is implicitly handled (single public index,
  no private index mixing) — worth one sentence to confirm no extra index URLs are
  configured.
- **SHA pinning rigor:** Correct. All five actions pinned to 40-char commit SHAs with
  version comments; the annotated-tag dereferencing for `pypa/gh-action-pypi-publish`
  (`^{}` commit `cef2210...`, not tag object `6733eb7...`) is handled correctly and is the
  detail most specs get wrong. Transitive composite-action caveat noted in SG-3. AC2 grep
  verification is sound.
- **OIDC / Trusted Publishing:** Trust flow is correct and minimally scoped.
  `id-token: write` is on the publish job only. Pending-publisher setup is accurate.
  Residual long-lived secret: none. The one soft spot is environment-protection
  enforcement (SF-4).
- **Permissions least-privilege:** Good. Workflow-level default `contents: read`;
  `id-token`/`attestations: write` scoped to `build-and-publish` job only; `audit` job
  inherits read-only. No `write-all`. The `audit` job correctly has no elevated perms.
- **Provenance attestation:** Correct binding artifact→source→workflow via Sigstore +
  GitHub OIDC; GitHub-hosted-runner requirement is noted (lines 238-240, 584-586);
  consumer verification documented with the per-file (no-glob) caveat.
- **Merge-gate vs tag-gate split:** Architecturally correct and aligned with prior council
  guidance. The deferred-audit window is a real accepted risk that must be named (SF-2).
- **Secrets handling:** No secrets stored or leaked. Test plan greps for
  `PYPI_TOKEN`/`password:` to assert zero secrets — good defensive verification. The
  `workflow_dispatch` dry-run mode (lines 669-672) introduces a conditional publish skip;
  ensure that conditional cannot be flipped to bypass the environment gate.
- **Dependency-intake checklist:** Adequate to catch typosquats/abandoned/malicious
  packages — covers maintainer health, release history, transitive impact, cooldown, and a
  decision record. Weakness is enforcement, not content (SG-4, SG-5).

---

## Sign-off

**APPROVED WITH CONDITIONS.** From a strategic supply-chain security standpoint the
architecture is sound and I would sign off for implementation provided SF-1 through SF-4
are resolved in the spec (or explicitly risk-accepted in the Security Considerations
section) before code is written. SF-1 is a correctness bug that breaks the pipeline; SF-2
and SF-3 are perimeter gaps that the spec claims to close but does not; SF-4 is a
fail-open control that must be made a hard prerequisite. None are architectural vetoes.

No veto.
