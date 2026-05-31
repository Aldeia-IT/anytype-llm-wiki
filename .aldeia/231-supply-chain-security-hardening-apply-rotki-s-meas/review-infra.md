# Infrastructure / Operational-Readiness Review — Spec #231

**Reviewer:** Infrastructure Lead (CI/CD + operational-readiness angle)
**Date:** 2026-05-30
**Spec:** `.aldeia/231-supply-chain-security-hardening-apply-rotki-s-meas/spec.md`
**Verdict:** APPROVED WITH CONDITIONS

---

## Scope note

This change is entirely GitHub-hosted (`ubuntu-latest`). It adds zero steady-state load
to the Mac Mini M4 32GB — no new launchd plist, no Docker/Colima change, no service,
no new local data store, no new log file, no watchdog/ntfy need. The "Resource Impact"
section (spec L552-560) is accurate: negligible host impact. I therefore focused on
**workflow correctness, release operational readiness, and failure modes**, which are the
real risk surface here.

The repo state confirms the spec's premises: `uv.lock` is present (259 KB, committed),
`tests/` exists with 5 test modules that all skip gracefully when external services are
unreachable (verified `pytest.skip()` fixtures in `test_anytype_client.py`,
`test_server.py`, etc.), and there is no `.github/` directory — this is genuinely
greenfield CI.

---

## Findings

### BLOCKING

**B1. Tag-version vs `pyproject.toml` version reconciliation is unspecified — silent
mismatch / wrong-version publish.**
*Spec: release.yml L449-506; review prompt item 4.*

`pyproject.toml` pins `version = "0.1.0"` (static, hatchling — no dynamic versioning).
The release workflow triggers on any `v*` tag and runs `uv build` + `uv publish`, but the
built artifact's version comes **only** from `pyproject.toml`, not from the tag. Nothing
in the workflow asserts that `git tag v0.2.0` corresponds to `version = "0.2.0"`.

Operational impact / failure modes this creates:
- Tag `v0.2.0` pushed while `pyproject.toml` still says `0.1.0` → workflow builds and
  publishes `anytype-llm-wiki-0.1.0` (wrong version, silently) OR, if `0.1.0` already
  exists on PyPI, `uv publish` fails with a 400 (file already exists) **after** a
  successful attestation — a partial/confusing release.
- Re-tagging or moving a tag does not change the artifact version. PyPI is immutable per
  (name, version); a botched first publish of `0.1.0` permanently burns that version.

**Required fix (pick one, document it):**
- (a) Add a guard step in `build-and-publish` that fails fast if the tag does not match
  the project version, e.g. read `uv version --short` (or parse `pyproject.toml`) and
  compare to `${GITHUB_REF_NAME#v}`, exiting non-zero on mismatch. This belongs **before**
  `uv build` so no attestation/publish is attempted on a mismatch.
- (b) Adopt tag-driven dynamic versioning (`hatch-vcs` / `uv-dynamic-versioning`) so the
  tag *is* the source of truth. Larger change; note it as the long-term option.

Recommend (a) for this spec — minimal, deterministic, and turns the most likely
operational mistake (tag/version drift) into a clean pre-build failure instead of a
poisoned PyPI release.

---

### SHOULD-FIX

**S1. No `workflow_dispatch` escape hatch in the authored `release.yml` — the test plan
depends on one that the spec doesn't actually define.**
*Spec: release.yml L449-506 (no `workflow_dispatch`); Test Plan L669-672 references a
`skip_publish` input.*

The Test Plan (L669-672) says "Add a `workflow_dispatch` trigger to `release.yml` with an
input `skip_publish: boolean`" so the audit+build+attest pipeline can be exercised without
publishing. But the canonical workflow spec at L449-506 has `on: push: tags: ["v*"]` only.
As written, the **only** way to exercise the real release path is to push a real `v*` tag,
which (per B1 and the partial-failure modes) is exactly the thing you don't want to dry-run
against production PyPI.

Operational impact: the first-ever release of this project would be the first-ever
execution of `release.yml` end-to-end. That is a poor operational posture for a workflow
whose failure modes include irreversible PyPI state and OIDC/Environment misconfiguration.

**Fix:** Promote the `workflow_dispatch` + `skip_publish` (or a `dry_run`) input from the
test plan into the authored `release.yml` spec itself, with the publish step guarded
(`if: inputs.dry_run != true`). Make the implementer author it that way, not as an
afterthought. This makes the publish path validatable before the first tag and gives a
manual re-run handle if a tag-triggered run fails partway.

**S2. Partial-failure / non-atomic release between attest and publish is not addressed.**
*Spec: release.yml L496-505; Security Considerations L564-590; review prompt item 6.*

The job order is `uv build` -> `attest-build-provenance` -> `uv publish`, all in one job.
There is no statement of what happens if:
- `uv publish` uploads the sdist then fails before the wheel (PyPI uploads are per-file,
  not transactional) → partial release on PyPI, re-run behavior undefined.
- Attestation succeeds but publish fails → an attestation exists in the GitHub store for
  artifacts that were never published (benign, but should be noted).
- The run is retried after a partial upload → `uv publish` will 400 on the already-present
  file. uv treats existing-file as an error by default.

Operational impact: a maintainer hitting a mid-publish failure has no documented recovery
procedure. For a single-maintainer project this is precisely where an undocumented edge
case becomes a multi-hour incident.

**Fix:** Add a short "Release failure recovery" note to the operational section:
(1) re-runs are safe only if no file was uploaded; (2) if a partial upload occurred, the
version is burned on PyPI and a patch-version bump + new tag is required (consequence of
PyPI immutability); (3) consider whether `uv publish` should run with a
"skip existing" tolerance is **not** desirable here (it would mask the version-collision
signal) — so document the bump-and-retag path instead. Pair this with B1's pre-build
version guard, which prevents the most common collision in the first place.

**S3. `release.yml` audit job uses `uv export ... --no-dev` but the audit cannot see
build-backend / non-locked surfaces, and the gate semantics differ from the merge-gate.**
*Spec: release.yml L471-475; research Q7 L496-505.*

Minor correctness points on the audit step:
- `uv export --format requirements-txt --no-dev` excludes dev deps. That is intentional
  (audit shipped surface), but `pytest` etc. are then unaudited even though they run in
  CI. Acceptable for a *release* audit; just confirm it is deliberate (it is, per research).
- The audit job runs `uv export` **without** first running `uv lock --check` or
  `uv sync --frozen`. If `uv.lock` drifted from `pyproject.toml` on the tagged commit,
  `uv export` will still emit *something* (from the lock) and the audit may pass against a
  lockfile that no longer matches the manifest being built in the sibling job. The build
  job re-derives from the same lock via `--frozen`, so they agree, but neither job asserts
  lock/manifest consistency on the release path.

Operational impact: a release could be built and published from a drifted lockfile because
the lockfile-consistency gate (`uv lock --check`) only exists in `ci.yml` (merge-gate), not
`release.yml` (tag-gate). Tags can be pushed to commits that never passed merge-gate
(e.g., a tag on an older commit, or branch protection not covering the tagged ref).

**Fix:** Add `uv lock --check` as the first step of the `audit` job (or of
`build-and-publish`). It is install-free and costs ~1s. This closes the "tag bypasses the
merge-gate" hole and guarantees the published artifact derives from a consistent lockfile.

**S4. CONTRIBUTING.md drift: test invocation in CI (`uv run pytest`) vs documented
(`uv run --extra dev pytest tests/ -v`) — and the spec's own §6/Open-Q2 are inconsistent.**
*Spec: ci.yml L444; spec L719-722; Open Questions L760-765; CONTRIBUTING.md L15, L214;
review prompt item 2.*

- `ci.yml` runs `uv run pytest`. CONTRIBUTING.md runs `uv run --extra dev pytest tests/ -v`.
  These resolve to the same tests *only because* the CI install step is
  `uv sync --frozen --all-extras --dev`, which pre-installs the dev group, so the bare
  `uv run pytest` finds pytest. This works, but the install command is itself questionable
  (see next bullet) and the divergence between the two documented invocations is a future
  trap.
- `uv sync --frozen --all-extras --dev` (ci.yml L441) is redundant/confusing:
  `--all-extras` already includes the `dev` *extra* (it is an `optional-dependencies`
  group in `pyproject.toml`, L18-19, **not** a PEP 735 dependency-group). The separate
  `--dev` flag refers to dependency-*groups*, of which this project has none. The command
  works but `--dev` is a no-op here and implies a project structure that doesn't exist.
  Spec Open-Q2 (L760-765) flags the `--all-extras` vs `--extra dev` choice but never
  resolves it.

Operational impact: low, but this is a from-scratch CI spec — the canonical invocation
should be unambiguous so contributors and future workflows don't cargo-cult a wrong flag
combo.

**Fix:** Standardize on `uv sync --frozen --extra dev` (matches the actual
`optional-dependencies.dev` group) and `uv run --extra dev pytest`, and make
CONTRIBUTING.md and both workflows use the identical command. Drop the `--dev` flag (no
dependency-groups exist). Resolve Open-Q2 explicitly in the spec rather than deferring to
the implementer.

**S5. No Python-version matrix; `requires-python = ">=3.11"` is tested on exactly one
implicit interpreter.**
*Spec: ci.yml L426-444; pyproject.toml L7; review prompt item 1.*

`pyproject.toml` declares `>=3.11` but `ci.yml` has no `strategy.matrix` and pins no
Python version. `uv` will pick one interpreter (whatever it resolves on the runner /
from `.python-version` if present — none is committed). So the published-as-supporting
"3.11+" claim is validated against a single, non-deterministic Python version per run.

Operational impact: a 3.11-only syntax/stdlib regression (or a 3.13-only break) ships
undetected. For a library intended for PyPI distribution this is a real correctness gap,
though not a deployment blocker.

**Fix:** Add a small matrix to the test job (`python-version: ["3.11", "3.13"]`) and use
`uv python install ${{ matrix.python-version }}` / `uv sync` against it, or pin a
`.python-version`. Keep it to the endpoints (min + max supported) to bound CI minutes.
Low cost on GitHub-hosted runners; no host impact.

---

### SUGGESTION

**G1. Document the GitHub Environment + pending-publisher prerequisites as a committed
runbook, not prose buried in the spec.**
*Spec: Operational Considerations L596-606; Open-Q1 L754-758.*

The first-release prerequisites (create `pypi` Environment, required reviewers, restrict to
`v*`, configure PyPI pending publisher with exact `release.yml` filename + `pypi`
environment name) are correct and complete in the spec. But Open-Q1 leaves the *home* for
this runbook undecided. For operational readiness these steps must live in the repo
(`docs/releasing.md` preferred) so the one-time setup is reproducible and reviewable, not
re-derived from a closed spec. Recommend resolving Open-Q1 toward `docs/releasing.md`.

**G2. `gh attestation verify` glob limitation is well-noted; also note the wheel filename
normalization.**
*Spec: L246-251, L665, L728-732.*

The spec correctly states `gh attestation verify` takes no globs. Minor: the example
filename `anytype_llm_wiki-0.1.0-py3-none-any.whl` assumes the PyPI name
`anytype-llm-wiki` normalizes to `anytype_llm_wiki` in the wheel — that is correct
(PEP 427/503 normalization), so the example is accurate. No change needed; just confirming
it's right.

**G3. `act` local validation caveat for the Mac Mini.**
*Spec: Test Plan L632-642.*

`act` requires Docker. On the Mac Mini, Docker runs under Colima with a 2GB RAM cap. `act`
pulling/running the large `ubuntu-latest` runner images can exceed 2GB and contend with the
other co-located services. This is the *one* place this otherwise host-neutral change could
touch the Mac Mini. Recommend either (a) noting that `act` validation should be done off
the shared Mini, or (b) using `act --dry-run` (no container exec) plus a real
`workflow_dispatch` dry-run (see S1) as the primary validation path, reserving full `act`
runs for a developer workstation. Do not let `act` runs compete with steady-state services
on the 2GB Colima allocation.

**G4. Dependabot `uv` ecosystem + `pip` fallback: avoid double-PR noise if both are
enabled.**
*Spec: dependabot.yml L518-548; research Q6.*

If issue #13426 forces adding the `pip` fallback entry alongside `uv`, both ecosystems
point at the same `pyproject.toml` and can open overlapping PRs (uv updates lock; pip
proposes manifest bumps without touching `uv.lock`). The spec correctly scopes the pip
entry to "security-only" in prose but the YAML snippet (L542-548) does not actually
restrict it to security updates. If the fallback is needed, add
`open-pull-requests-limit: 0` is wrong here; instead the intended scoping is not
expressible in `dependabot.yml` directly (Dependabot opens both version and security PRs
for an ecosystem). Note this honestly: enabling the `pip` fallback *will* produce some
version-update noise, and the operator should expect to close non-security pip PRs. Low
stakes; just set expectations.

---

## Dimensions that are sound (brief)

- **Workflow YAML structure** (triggers, `needs: audit`, job-level least-privilege
  permissions, `runs-on: ubuntu-latest`, checkout-before-setup-uv ordering): correct and
  will run. The merge/tag split is well-reasoned.
- **uv command semantics** for the merge-gate (`uv lock --check` then `uv sync --frozen`):
  correct per the documented semantics; the two-step rationale over `--locked` is sound.
- **Cache strategy** (`enable-cache: true` dev, `enable-cache: false` release): correctly
  specified and matches the cache-poisoning rationale.
- **SHA pinning**: all five actions pinned to 40-char commit SHAs with version comments;
  the annotated-tag dereference for `pypa/gh-action-pypi-publish` is handled correctly
  (though that action is not used in the final design — `uv publish` is). AC2 grep
  verification is a good gate.
- **OIDC trusted publishing** (`uv publish`, `id-token: write`, `environment: pypi`,
  pending-publisher): the design is correct and the no-long-lived-secret posture is the
  right call. Defer to the CSO on the Environment required-reviewer / branch-restriction
  specifics (network/auth overlap).
- **Resource impact on the Mac Mini**: effectively nil (GitHub-hosted), with the single
  `act`/Colima caveat in G3.

---

## Verdict

**APPROVED WITH CONDITIONS.**

The architecture is operationally sound and adds no Mac Mini load. Conditions for sign-off:

1. **B1 (blocking):** Add a tag-vs-`pyproject.toml` version guard before `uv build`, or
   adopt tag-driven versioning. This is the one issue that can produce an irreversible
   wrong/partial PyPI release.
2. Address **S1** (author `workflow_dispatch` dry-run into `release.yml`, not just the test
   plan), **S3** (`uv lock --check` on the release path so tags can't bypass the
   lockfile gate), and **S4** (single canonical install/test command across workflows +
   CONTRIBUTING.md, resolve Open-Q2). **S2** and **S5** should be addressed but can be
   documented mitigations rather than hard blockers.

Once B1 is resolved and S1/S3/S4 are folded in, this is a clean deployment with no
operational risk to the shared host.

**Finding counts:** BLOCKING: 1 · SHOULD-FIX: 5 · SUGGESTION: 4
