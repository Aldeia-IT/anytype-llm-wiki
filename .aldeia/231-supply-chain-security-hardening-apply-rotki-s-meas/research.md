# Research: Supply-Chain Security Hardening (rotki measures) for anytype-llm-wiki
**Ticket:** Aldeia-IT/aldeia-box#231
**Date:** 2026-05-30
**Branch:** aldeia/231-supply-chain-security-hardening-apply-rotki-s-meas
**Researcher:** Technical research worker

---

## Sources and Verification Notes

All SHA values below were verified via live `git ls-remote` against the upstream GitHub
repositories on 2026-05-30. These are the current latest tags at time of writing; they
will advance — pin to the SHA not the tag in workflow files.

Annotated tags: `git ls-remote` returns two lines — the tag object SHA and `^{}` (the
dereferenced commit SHA). For pinning in `uses:` lines you must use the **commit** SHA
(the `^{}` value for annotated tags). For lightweight tags only one line appears and that
SHA is the commit directly.

---

## Q1: Frozen uv installs in CI

### Semantics: --locked vs --frozen vs uv lock --check

Source: https://docs.astral.sh/uv/reference/cli/ (fetched 2026-05-30)

**`uv sync --locked`**
> "Assert that the `uv.lock` will remain unchanged. Requires that the lockfile is
> up-to-date. If the lockfile is missing or needs to be updated, uv will exit with an
> error."

Mechanism: uv re-runs the resolver against the current `pyproject.toml` in memory,
compares the result to the committed `uv.lock`, and fails if they would differ. This is a
consistency check plus install in one step.

**`uv sync --frozen`**
> "Run without updating the `uv.lock` file. Instead of checking if the lockfile is
> up-to-date, uses the versions in the lockfile as the source of truth. If the lockfile
> is missing, uv will exit with an error."

Mechanism: skips re-running the resolver entirely; treats `uv.lock` as authoritative.
Faster, but does NOT catch drift between `pyproject.toml` and `uv.lock`.

**`uv lock --check`**
Explicitly checks whether `uv.lock` is consistent with `pyproject.toml` without
installing anything and without modifying the lockfile. Exit code is non-zero if drift is
detected. Documented as equivalent to `--locked` for other commands.

Note: `--frozen` and `--locked` cannot be combined.

### CI Recommendations

**(a) Verify that the committed `uv.lock` is up to date with `pyproject.toml` (merge gate):**

```yaml
- name: Check lockfile consistency
  run: uv lock --check
```

This is the right choice for a fast, install-free gate. It runs in seconds and will fail
PRs that modify `pyproject.toml` without regenerating `uv.lock`.

**(b) Install exactly the locked versions (all CI jobs that need the environment):**

```yaml
- name: Install dependencies
  run: uv sync --frozen --all-extras --dev
```

Use `--frozen` here rather than `--locked` because: (1) the lockfile consistency check
has already been run by `uv lock --check` in a prior step or job; (2) `--frozen` skips
the resolver, making installs faster and deterministic without re-validating the lockfile
a second time; (3) it exactly mirrors what Docker/production deploys should do.

Alternatively, combine both into a single step with `uv sync --locked` when you want one
command that both validates and installs.

### `astral-sh/setup-uv` cache and frozen flags

The `setup-uv` action does NOT run `uv sync`; it only installs the `uv` binary and
optionally populates the uv download cache. The `--locked`/`--frozen` flags are passed to
subsequent `uv sync` / `uv run` calls that the workflow author writes. Cache is keyed by
`uv.lock` by default when `cache-dependency-glob` is not overridden.

Recommended job pattern (merge-gate job):

```yaml
- uses: astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b  # v8.1.0
  with:
    enable-cache: true
- run: uv lock --check
- run: uv sync --frozen --all-extras --dev
- run: uv run pytest
```

---

## Q2: Cache-free release builds

### Exact input

Source: https://github.com/astral-sh/setup-uv (fetched 2026-05-30)

```yaml
- uses: astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b  # v8.1.0
  with:
    enable-cache: false
```

The `enable-cache` input accepts `"true"`, `"false"`, or `"auto"`. The default on
GitHub-hosted runners is effectively `true`; `"auto"` enables caching only on
GitHub-hosted runners.

### Why it matters for releases

The uv cache on GitHub Actions stores downloaded wheel and sdist files. If an attacker
has poisoned a cached artifact (e.g., via a compromised earlier run, a cache-key
collision, or a cache restore from a fork), that poisoned artifact will be reused without
re-downloading and re-verifying from PyPI. Release/publish workflows must build from
clean downloads to ensure what is attested and published is verifiably fresh.

This mirrors rotki's rationale: "malicious artifacts in caches could be reused without
verification."

### Dev/test jobs

Dev, test, and lint jobs may freely use `enable-cache: true`. Cache hits only affect
test performance, not artifact integrity. The risk of a poisoned cache in a test job is
low — the worst outcome is a flaky test, not a compromised release artifact.

---

## Q3: SHA-pinning GitHub Actions

### Best practice

Pin every `uses:` line to a full 40-character commit SHA. Add a version comment so
humans and Dependabot/Renovate can identify what version is pinned.

```yaml
uses: owner/action@<40-char-sha>  # vX.Y.Z
```

Rationale: tags are mutable; a tag can be moved to a new (malicious) commit. A commit
SHA is immutable. The 2026 tj-actions/changed-files attack compromised >23,000
repositories through exactly this vector.

### Verified SHAs (verified via git ls-remote, 2026-05-30)

All SHAs below are **commit SHAs** (dereferenced from annotated tags where applicable).
The `^{}` notation in `git ls-remote` output identifies the actual commit for an
annotated tag.

**`actions/checkout` v6.0.2**
- Tag: `v6.0.2` (lightweight — SHA is directly the commit)
- Commit SHA: `de0fac2e4500dabe0009e67214ff5f5447ce83dd`
- Pin line:
  ```yaml
  uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd  # v6.0.2
  ```
- Verified: yes (git ls-remote 2026-05-30)

**`astral-sh/setup-uv` v8.1.0**
- Tag: `v8.1.0` (lightweight — SHA is directly the commit)
- Commit SHA: `08807647e7069bb48b6ef5acd8ec9567f424441b`
- Pin line:
  ```yaml
  uses: astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b  # v8.1.0
  ```
- Verified: yes (git ls-remote 2026-05-30)
- Note: as of v8.0.0 (March 2026), astral-sh stopped publishing moving `v8` / `v8.0`
  floating tags; only immutable full-version tags are published, nudging users toward
  SHA pinning or full version references.

**`actions/attest-build-provenance` v4.1.0**
- Tag: `v4.1.0` (lightweight)
- Commit SHA: `a2bbfa25375fe432b6a289bc6b6cd05ecd0c4c32`
- Pin line:
  ```yaml
  uses: actions/attest-build-provenance@a2bbfa25375fe432b6a289bc6b6cd05ecd0c4c32  # v4.1.0
  ```
- Verified: yes (git ls-remote 2026-05-30)
- Note: The GitHub-side docs say v4 is a wrapper on `actions/attest`. Existing workflows
  using `attest-build-provenance` are still fully supported; new projects could use
  `actions/attest` directly, but `attest-build-provenance` remains the simpler interface.

**`pypa/gh-action-pypi-publish` v1.14.0**
- Tag: `v1.14.0` (annotated — must use dereferenced commit SHA)
- Tag object SHA: `6733eb7d741f0b11ec6a39b58540dab7590f9b7d`
- **Commit SHA (use this):** `cef221092ed1bacb1cc03d23a2d87d1d172e277b`
- Pin line:
  ```yaml
  uses: pypa/gh-action-pypi-publish@cef221092ed1bacb1cc03d23a2d87d1d172e277b  # v1.14.0
  ```
- Verified: yes (git ls-remote 2026-05-30)
- Released: April 7, 2026

**`actions/setup-python` v5.6.0**
- Tag: `v5.6.0` (lightweight)
- Commit SHA: `a26af69be951a213d495a4c3e4e4022e16d87065`
- Pin line:
  ```yaml
  uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065  # v5.6.0
  ```
- Verified: yes (git ls-remote 2026-05-30)
- Note: `actions/setup-python` may not be needed if `astral-sh/setup-uv` with
  `uv python install` is used instead. Include only if the workflow requires the
  `python` binary on PATH independently of uv.

### To resolve a SHA for any action at any time

```bash
git ls-remote https://github.com/OWNER/ACTION.git refs/tags/vX.Y.Z 'refs/tags/vX.Y.Z^{}'
```

If both lines appear, use the `^{}` SHA (annotated tag; use the dereferenced commit).
If only one line, use that SHA (lightweight tag; it is already the commit SHA).

---

## Q4: Build provenance attestation

Source: https://docs.github.com/actions/security-for-github-actions/using-artifact-attestations/ (fetched 2026-05-30)

### What it does

`actions/attest-build-provenance` generates a SLSA-style provenance attestation for one
or more build artifacts. The attestation is signed using Sigstore with the GitHub OIDC
identity of the workflow run and stored in the GitHub repository's attestation store.
This creates a cryptographically verifiable link between a specific artifact and the
source commit + workflow that produced it.

### Required permissions

```yaml
permissions:
  id-token: write      # obtain OIDC token to sign the attestation
  attestations: write  # write attestation to GitHub's attestation store
  contents: read       # read the repository
```

These must be set at the job level (not workflow level) to follow least-privilege.

### Using subject-path with dist/*

For a Python project that builds sdist + wheel to `dist/`, use a glob:

```yaml
- name: Build distributions
  run: uv build

- name: Attest build provenance
  uses: actions/attest-build-provenance@a2bbfa25375fe432b6a289bc6b6cd05ecd0c4c32  # v4.1.0
  with:
    subject-path: dist/*
```

The `subject-path` glob matches all files in `dist/` (typically one `.tar.gz` sdist and
one `.whl` wheel). Each matched file receives its own attestation record. Wildcards are
supported.

### Consumer verification

A consumer who downloads the wheel from PyPI can verify its provenance:

```bash
gh attestation verify dist/anytype_llm_wiki-0.1.0-py3-none-any.whl \
  --repo Aldeia-IT/anytype-llm-wiki
```

Or with owner-level scope (if the package name is unique):

```bash
gh attestation verify anytype_llm_wiki-0.1.0-py3-none-any.whl \
  --owner Aldeia-IT
```

Note: `gh attestation verify` does NOT accept file globs — each artifact must be verified
individually. This is a known CLI limitation (GitHub CLI issue #9215).

### GitHub-hosted runner requirement

Attestation generation requires a GitHub-hosted runner (or a runner with network access
to GitHub's OIDC endpoint). Self-hosted runners behind strict egress firewalls may fail
to obtain an OIDC token. For this repo, GitHub-hosted `ubuntu-latest` is the standard
runner and satisfies this requirement.

---

## Q5: OIDC Trusted Publishing to PyPI

Sources:
- https://docs.astral.sh/uv/guides/integration/github/ (fetched 2026-05-30)
- https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/ (fetched 2026-05-30)
- https://github.com/astral-sh/trusted-publishing-examples (noted in search 2026-05-30)

### Two options evaluated

**Option A: `uv publish` with trusted publishing (native)**

```yaml
permissions:
  id-token: write
  contents: read

steps:
  - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd  # v6.0.2
  - uses: astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b  # v8.1.0
    with:
      enable-cache: false
  - run: uv build
  - run: uv publish
```

uv detects the GitHub Actions OIDC environment automatically when `id-token: write` is
set and exchanges the token for a short-lived upload credential from PyPI. No secrets
required.

**Option B: `pypa/gh-action-pypi-publish` with OIDC**

```yaml
permissions:
  id-token: write

steps:
  - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd  # v6.0.2
  - uses: astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b  # v8.1.0
    with:
      enable-cache: false
  - run: uv build
  - uses: pypa/gh-action-pypi-publish@cef221092ed1bacb1cc03d23a2d87d1d172e277b  # v1.14.0
```

### Recommendation: Option A — `uv publish`

**Justification:**

1. This is a uv-first project. Keeping the entire build/publish pipeline in uv reduces
   moving parts and external action dependencies.
2. Astral publishes a reference example (`trusted-publishing-examples`) specifically for
   `uv publish`, which shows the recommended pattern is now uv-native.
3. `pypa/gh-action-pypi-publish` still works fine and is widely used, but it adds a
   third-party action dependency that must be SHA-pinned and kept updated.
4. Signed attestations are now generated automatically by PyPI for all trusted-publishing
   uploads (via Sigstore), independent of which upload method is used.
5. The `uv publish` approach composes cleanly with `actions/attest-build-provenance` in
   the same workflow — build, attest, then publish.

**PyPI side configuration:**

For a new project not yet on PyPI, use a "pending publisher":

1. Log into PyPI → Account sidebar → Publishing → "Add a new pending publisher"
2. Fields to fill:
   - PyPI project name: `anytype-llm-wiki`
   - GitHub owner: `Aldeia-IT`
   - GitHub repository: `anytype-llm-wiki`
   - Workflow filename: `release.yml` (exact filename)
   - Environment name: `pypi` (must match the `environment:` value in the workflow)
3. On first publish, the pending publisher converts to a standard publisher.

**GitHub Environment + protection rules:**

```yaml
jobs:
  release:
    name: Publish to PyPI
    runs-on: ubuntu-latest
    environment: pypi        # links to the named GitHub environment
    permissions:
      id-token: write
      attestations: write
      contents: read
```

In GitHub repo Settings → Environments → `pypi`:
- Add required reviewers (maintainer(s) must approve before publish runs)
- Restrict to the `main` branch or protected tags (e.g., `v*`)

This ensures the publish step cannot be triggered by an unreviewed PR or a force-push.

---

## Q6: Maintaining SHA pins

### Dependabot (recommended for this repo)

Dependabot is natively integrated into GitHub and requires no additional tooling setup.
As of 2026 it supports:

- `package-ecosystem: github-actions` — updates `uses:` lines in workflow files; parses
  trailing `# vX.Y.Z` comments and opens PRs that bump both the SHA and the comment.
- `package-ecosystem: uv` — natively understands `pyproject.toml` + `uv.lock` and
  updates both files together. Note: there is a known bug (dependabot/dependabot-core
  #13426, opened Oct 2025) where security updates sometimes fall back to the `pip`
  resolver instead of `uv`. The regression was reported as under investigation. As a
  workaround, if this bug affects the project, use `package-ecosystem: pip` as fallback
  for security updates only.
- `package-ecosystem: pip` — fallback for Python dependencies if `uv` ecosystem has
  issues; reads `requirements*.txt` or `pyproject.toml`; does NOT update `uv.lock`.

**Dependabot + SHA pins for GitHub Actions:** Dependabot correctly handles SHA-pinned
actions that have a version comment. It will update the SHA and the comment together when
a new release is available.

**Minimal `.github/dependabot.yml`:**

```yaml
version: 2
updates:
  # Keep GitHub Actions SHA-pinned references up to date
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    groups:
      actions:
        patterns: ["*"]

  # Keep Python dependencies in uv.lock up to date
  - package-ecosystem: "uv"
    directory: "/"
    schedule:
      interval: "weekly"
```

### Renovate (alternative, more capable)

Renovate supports `uv` natively, updates both `pyproject.toml` and `uv.lock`, and
supports digest pinning for GitHub Actions via the `helpers:pinGitHubActionDigests`
preset. It maintains version comments alongside SHA pins.

Minimal `renovate.json`:

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": [
    "config:recommended",
    "helpers:pinGitHubActionDigests"
  ],
  "lockFileMaintenance": {
    "enabled": true
  }
}
```

Renovate is more powerful but requires either the Renovate GitHub App or a self-hosted
runner, adding operational complexity. For a single-maintainer open-source project with
no existing Renovate setup, **Dependabot is the lower-friction choice**.

### Handling the 7-day cooldown

The rotki blog recommends a 7-day cooldown before applying dependency updates.
Dependabot does not have a native cooldown setting. This can be approximated by:
- Leaving PRs open for a week before merging (manual discipline)
- Using Renovate's `minimumReleaseAge: "7 days"` setting (Renovate only)

For the spec, note this as a workflow convention (human discipline) since Dependabot
automation cannot enforce it.

---

## Q7: Dependency auditing in CI

### Current state of uv-native audit

`uv audit` was introduced as a preview feature and has been under active development
throughout 2026. Key timeline:

- v0.10.10 (2026-03-13): batched OSV queries, output formatting
- v0.10.12 (2026-03-19): unhidden from CLI help (transitioning from hidden preview)
- v0.11.x (2026-04-08 onward): continuing preview enhancements (context, fix mode,
  JSON output, error specialization)
- Roadmap issue #18506 (opened 2026-03-16): MVP includes core CLI, OSV integration,
  workspace support; post-MVP includes additional lockfile formats and ignore controls

**Status as of 2026-05-30:** `uv audit` exists and is functional but is still marked as
a preview feature in most versions. It reads `uv.lock` directly and queries the OSV
database. It is the cleanest solution for a uv project but should be considered
**preview-quality** — its flags and output format may change without a deprecation cycle.

### pip-audit (stable, recommended for now)

`pip-audit` (https://github.com/pypa/pip-audit, v2.10.0, 2025-12-01) is the stable,
PyPA-supported audit tool. It has been tested extensively in CI.

For a uv project, run it via `uvx` (no install required):

```yaml
- name: Audit dependencies
  run: uvx pip-audit
```

`pip-audit` searches the project path for `pyproject.toml` or `pylock.*.toml`. For
`uv.lock` specifically, there is no direct support listed in the pip-audit docs (as of
v2.10.0). The safe pattern is:

```yaml
- name: Export lockfile for audit
  run: uv export --format requirements-txt --no-dev > /tmp/requirements-audit.txt
- name: Audit dependencies
  run: uvx pip-audit -r /tmp/requirements-audit.txt
```

Alternatively, as `uv audit` stabilizes, it can replace `pip-audit` with a cleaner
interface:

```yaml
- name: Audit dependencies
  run: uv audit
```

### Gating recommendation

Following prior council guidance (mem0 0ae961bc):

**MERGE-gate (every PR):**
- `uv lock --check` (lockfile consistency, fast, fail fast)
- `uv run pytest` (unit tests)

**TAG-gate (release tag push only):**
- `uvx pip-audit` or `uv audit` (dependency vulnerability scan)
- `uvx bandit -r src/` (static security analysis)
- `uvx pip-licenses` (license compliance)
- `uvx gitleaks detect` (secret scan)
- Build, attest, publish

Rationale: the security/audit steps can take 30-90s and produce failures that need human
triage. They are inappropriate as a hard gate on every PR. Tag gates run on controlled,
reviewed code and are the right place for heavier security checks.

---

## Q8: Dependency-intake checklist

Source: https://blog.rotki.com/2026/05/22/rotki-security/ — Measure #7 (fetched 2026-05-30)

### Rotki's measure #7 (as described)

Before accepting a new dependency the team evaluates:

1. Maintainer reputation: Who maintains it? Is the project active?
2. Release history: Does it have a history of suspicious releases?
3. Transitive dependencies: How many transitive dependencies does it bring?
4. Make vs. buy: Is the package doing something simple enough that we should implement it
   ourselves? Is vendoring a small piece of code safer than depending on the whole
   package?

The rotki blog also describes a 7-day cooldown: apply updates only 7 days after a new
release to give the ecosystem time to detect suspicious releases.

### Checklist for `docs/dependency-intake.md`

The spec author should commit a file with approximately this structure:

```markdown
# Dependency Intake Checklist

Use this checklist before adding a new dependency (or accepting a major version bump)
to anytype-llm-wiki.

## 1. Necessity

- [ ] Does this solve a problem we cannot reasonably solve ourselves in <200 lines?
- [ ] Have we evaluated vendoring a small, stable excerpt of the library?
- [ ] Is this a direct dependency or can we depend on something we already have?

## 2. Maintainer health

- [ ] Who are the maintainers? Are they known/reputable in the Python ecosystem?
- [ ] Is the project actively maintained (commits in the last 12 months)?
- [ ] Is there a SECURITY.md or a responsible disclosure policy?
- [ ] Is it under a foundation / organization (e.g., PyPA, PSF, NumFocus) or a single
      individual with no succession plan?

## 3. Release history

- [ ] Review the last 3-5 release changelogs. Any unusual changes or ownership transfers?
- [ ] Search PyPI for any prior security advisories (OSV, GitHub Advisory DB).
- [ ] Check release dates: any very recent release (< 7 days)? Apply the cooldown rule.

## 4. Transitive impact

- [ ] Run `uv add <package> --dry-run` and review what transitive packages would be added.
- [ ] Is the transitive footprint proportionate to the value delivered?
- [ ] Do any transitive packages have known CVEs? (`uvx pip-audit` or `uv audit`)

## 5. License compatibility

- [ ] Is the license compatible with MIT?
- [ ] Check transitive licenses: `uvx pip-licenses --from=all`

## 6. Cooldown

- [ ] If the package was released < 7 days ago, defer integration by the remaining days.
      (Research shows 7-day cooldown blocks ~80% of supply-chain attacks.)

## 7. Decision record

Document the outcome in the PR description:
- Why this dependency was accepted (or rejected/vendored)
- Who reviewed it
- Any risk notes

## References
- rotki supply-chain security: https://blog.rotki.com/2026/05/22/rotki-security/
- OSV database: https://osv.dev
- GitHub Advisory Database: https://github.com/advisories
```

---

## Summary table: SHA pins verified 2026-05-30

| Action | Version | Commit SHA (use this) | Verified |
|---|---|---|---|
| `actions/checkout` | v6.0.2 | `de0fac2e4500dabe0009e67214ff5f5447ce83dd` | yes |
| `astral-sh/setup-uv` | v8.1.0 | `08807647e7069bb48b6ef5acd8ec9567f424441b` | yes |
| `actions/attest-build-provenance` | v4.1.0 | `a2bbfa25375fe432b6a289bc6b6cd05ecd0c4c32` | yes |
| `pypa/gh-action-pypi-publish` | v1.14.0 | `cef221092ed1bacb1cc03d23a2d87d1d172e277b` | yes (annotated tag, ^{} used) |
| `actions/setup-python` | v5.6.0 | `a26af69be951a213d495a4c3e4e4022e16d87065` | yes |

All verified with `git ls-remote` on 2026-05-30. Re-run before authoring the spec to
pick up any releases since this date.

---

## Open items / flags for spec author

1. **`uv audit` preview status:** The spec should mention `uv audit` as the forward-
   looking native tool but recommend `pip-audit` (via `uvx`) as the stable choice for
   now, with a note to switch when `uv audit` stabilizes (no hard date).

2. **Dependabot uv bug:** Issue #13426 (security updates falling back to pip) was open as
   of late 2025. Verify current status before writing the spec. If still unresolved,
   recommend using `package-ecosystem: pip` for security update scanning and `uv` for
   version updates.

3. **`actions/checkout` major version:** The source docs showed usage of v6 (latest as
   of 2026-05-30). The spec should note this is a major bump from the commonly-seen v4 in
   older documentation examples, and that v6 is the current latest.

4. **`actions/attest-build-provenance` deprecation note:** GitHub recommends new
   implementations use `actions/attest` directly (v4 of `attest-build-provenance` is a
   wrapper). The spec can either use the wrapper (simpler) or the underlying action
   (more future-proof). Either is valid; note the trade-off.

5. **PyPI project does not yet exist:** The "pending publisher" setup on PyPI must happen
   before the first tag/release push or the publish step will fail. This is a one-time
   manual step by the project maintainer and should be called out in CONTRIBUTING.md or
   a runbook.

6. **Attestation verification glob limitation:** `gh attestation verify` requires per-file
   invocations, not globs. If the spec includes a verification command in the README, it
   should show a single-file example and note this limitation.
