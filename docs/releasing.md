# Releasing anytype-llm-wiki

This runbook covers publishing a release to PyPI via the `release.yml` tag-gate
workflow. The pipeline uses **OIDC trusted publishing** (no long-lived PyPI
token) plus a **build-provenance attestation**. The security of the publish path
rests on the `pypi` GitHub Environment being correctly protected — that control
is **fail-open**, so the first-release checklist below includes a scriptable
hard-gate that you MUST run before the first tag.

> **⚠️ Publishing is OFF by default — the project is git-tag-only.** The `uv publish`
> step is gated on the repo variable **`PYPI_PUBLISH_ENABLED`** (Settings → Secrets
> and variables → Actions → Variables). While it is unset/`false`, a `v*` tag runs
> audit + build + provenance-attest and goes **green, but nothing is published to
> PyPI** — this is the intended state for v0.2.0 (dogfooded internally first).
> Turning publishing on is step **(d)** of the first-release checklist below: set
> `PYPI_PUBLISH_ENABLED=true` *after* the trusted-publisher + Environment setup.
> You never edit or remove the guard — you flip the variable.

> **Audience:** maintainers with admin access to `Aldeia-IT/anytype-llm-wiki` and
> ownership/maintainer rights on the PyPI project `anytype-llm-wiki`.

---

## How the release pipeline works

A push of a `v*` tag (e.g. `v0.2.0`) triggers `.github/workflows/release.yml`:

1. **`audit` job** — re-checks lockfile consistency, runs `pip-audit` on the
   shipped dependency surface, plus the OSS-hygiene scanners (bandit, pip-licenses,
   gitleaks). Any finding fails the release before anything is built.
2. **`build` job** (`needs: audit`, **no `environment:`**) — re-checks the lockfile,
   runs the **tag-vs-version guard**, builds the sdist + wheel cache-free, attests
   build provenance, and uploads the distributions as a workflow artifact. This job
   carries no Environment, so it never pauses for approval — a git-tag-only build
   runs green and unattended.
3. **`publish` job** (`needs: build`, **`environment: pypi`**) — downloads the exact
   artifacts `build` attested and publishes them to PyPI via `uv publish`, but
   **only when the repo variable `PYPI_PUBLISH_ENABLED` is `true`**. With the
   variable unset (default), nothing is published (git-tag-only).

The split is deliberate: the `environment: pypi` gate (and any required-reviewer
approval) lands **only on the `publish` job** — the one that actually uploads — so
git-only tags build + attest without waiting on an approval they'd never use. That
Environment gate is the load-bearing publish control — see the first-release checklist.

---

## First-release checklist (one-time, manual — do this BEFORE the first `v*` tag)

Perform these steps in order. They are one-time setup; later releases skip to
[Cutting a release](#cutting-a-release).

### (a) Configure the PyPI pending publisher

This cannot be done by CI and must exist before the first publish.

1. Log into [PyPI](https://pypi.org) → Account sidebar → **Publishing** →
   **"Add a new pending publisher"**.
2. Fill in **exactly**:
   - **PyPI project name:** `anytype-llm-wiki`
   - **GitHub owner:** `Aldeia-IT`
   - **GitHub repository:** `anytype-llm-wiki`
   - **Workflow filename:** `release.yml` (exact, case-sensitive)
   - **Environment name:** `pypi` (must match `environment:` in `release.yml`)
3. On the first successful publish, the pending publisher converts to a standard
   trusted publisher automatically.

### (b) Create and protect the `pypi` GitHub Environment

In **Settings → Environments** of `Aldeia-IT/anytype-llm-wiki`:

1. Create an environment named **`pypi`** (must match the workflow value exactly).
2. **Required reviewers:** add **at least one** maintainer. The publish job will
   pause for approval before it runs.
3. **Deployment branches and tags:** set this to **"Selected branches and tags"**,
   then **"Add deployment branch or tag rule"** → choose **Tag** (not Branch) →
   pattern **`v*`**. This ensures only `v*` tag pushes can use the environment.

> **Why this matters (fail-open warning):** if the `pypi` environment is created
> without these protections (or auto-created on first reference), the
> `environment: pypi` label becomes a no-op and ANY `v*` tag push from anyone with
> push access publishes to PyPI with the workflow's OIDC identity. Protection is a
> hard prerequisite, not a footnote. (The `PYPI_PUBLISH_ENABLED` variable is a
> second, independent layer — while it is unset nothing publishes regardless — but
> once you enable publishing in step (d), an unprotected Environment is fully
> fail-open. Both gates must hold.)

Pair this with repository-level **restricted tag protection** (Settings → Rules →
Rulesets, or classic "Protected tags") for `v*` so only maintainers can create
release tags in the first place.

> **Plan-tier note:** Environment protection rules are **free for public repos**.
> `Aldeia-IT/anytype-llm-wiki` is public (MIT), so this is available at no cost. If
> the repo were ever made private on a free plan, the gate would silently stop
> enforcing and an alternative control (manual-approval job / org tag protection)
> would be required.

### (c) Verify the gate is actually closed (scriptable HARD GATE — mandatory)

The Environment control is fail-open, so **verify it programmatically** before
tagging. Copy-paste and run this block. It **exits non-zero** unless (i) a
`required_reviewers` rule with ≥1 reviewer exists AND (ii) a `v*`
deployment-branch/tag policy exists. **Do not tag until it prints `GATE OK` and
exits 0.**

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO="Aldeia-IT/anytype-llm-wiki"
ENV="pypi"

# (i) Require a required_reviewers protection rule with >= 1 reviewer.
reviewer_count="$(
  gh api "repos/${REPO}/environments/${ENV}" \
    --jq '[.protection_rules[]? | select(.type=="required_reviewers") | .reviewers[]?] | length'
)"
if [[ -z "${reviewer_count}" || "${reviewer_count}" -lt 1 ]]; then
  echo "GATE FAIL: pypi environment has no required_reviewers rule with >=1 reviewer." >&2
  echo "  -> Add at least one required reviewer in Settings -> Environments -> pypi." >&2
  exit 1
fi

# (ii) Require a custom deployment-branch/tag policy that includes a 'v*' rule.
custom_policies="$(
  gh api "repos/${REPO}/environments/${ENV}" \
    --jq '.deployment_branch_policy.custom_branch_policies // false'
)"
if [[ "${custom_policies}" != "true" ]]; then
  echo "GATE FAIL: pypi environment is not restricted to custom branch/tag policies." >&2
  echo "  -> Set 'Deployment branches and tags' to 'Selected branches and tags'." >&2
  exit 1
fi

v_star_present="$(
  gh api "repos/${REPO}/environments/${ENV}/deployment-branch-policies" \
    --jq '[.branch_policies[]? | select(.name=="v*")] | length'
)"
if [[ -z "${v_star_present}" || "${v_star_present}" -lt 1 ]]; then
  echo "GATE FAIL: pypi environment has no 'v*' deployment branch/tag policy." >&2
  echo "  -> Add a Tag rule with pattern 'v*' under Deployment branches and tags." >&2
  exit 1
fi

echo "GATE OK: pypi environment has >=1 required reviewer and a 'v*' deployment policy."
```

If this prints `GATE FAIL` for either condition, the publish gate is OPEN — fix
the environment configuration and re-run until it prints `GATE OK`.

### (d) Enable publishing (flip the toggle — do this LAST)

Steps (a)–(c) leave the project **git-tag-only** (the release workflow builds and
attests but does not publish). When you are ready for the first PyPI release —
and only after (a)–(c) are green — turn publishing on by setting the repo
variable:

```bash
gh variable set PYPI_PUBLISH_ENABLED --repo Aldeia-IT/anytype-llm-wiki --body true
```

(or Settings → Secrets and variables → Actions → Variables → New variable
`PYPI_PUBLISH_ENABLED = true`). From the next `v*` tag onward the
`publish` job runs `uv publish`. To pause publishing again later, set
it back to `false`. **Never edit or remove the guard in `release.yml`** — the
variable is the on/off switch.

---

## Cutting a release

### 1. Match the version and the tag exactly (tagging contract)

The release tag MUST be **exactly** `v<project.version>`. The `release.yml`
guard step compares `${GITHUB_REF_NAME#v}` against `uv version --short` with an
**exact string match** (no PEP 440 normalization):

- `pyproject.toml` `version = "0.2.0"` → tag `v0.2.0` ✅
- `v0.2`, `v0.2.0.0`, `0.2.0` (no `v`), or differently-formatted pre-release
  suffixes → guard **fails closed** before any build/publish ❌

So, before tagging:

```bash
# 1. Bump the version in pyproject.toml (e.g. 0.1.0 -> 0.2.0), then:
uv lock                      # regenerate uv.lock if dependencies changed
git add pyproject.toml uv.lock
git commit -m "release: v0.2.0"

# 2. Confirm the manifest version (this is what the guard compares against):
uv version --short           # must equal the tag you are about to push, minus the leading v

# 3. Tag EXACTLY v<that version> and push:
git tag v0.2.0
git push origin v0.2.0
```

### 2. Approve the publish

> Only applies when publishing is enabled (`PYPI_PUBLISH_ENABLED=true`, step (d)).
> If the variable is unset, the tag is **git-tag-only**: the job builds + attests
> and the "Publish to PyPI" step is skipped — there is nothing to approve, and the
> run is green. (This is the v0.2.0 path.)

The `publish` job pauses on the `pypi` environment for required-reviewer
approval. A maintainer approves it; `uv publish` then uploads via OIDC.

### 3. (Optional) Dry-run before a real tag

Exercise audit + build + attest WITHOUT publishing:

```bash
gh workflow run release.yml -f skip_publish=true
gh run watch     # confirm the "Publish to PyPI" step shows as skipped
```

### 4. Verify provenance after publish

```bash
gh attestation verify anytype_llm_wiki-0.2.0-py3-none-any.whl \
  --repo Aldeia-IT/anytype-llm-wiki
```

`gh attestation verify` does not accept globs — verify each artifact file
individually.

---

## Partial-failure recovery (PyPI is immutable)

`uv publish` uploads per-file (sdist, then wheel), and **PyPI is immutable per
`(name, version)`** — a version cannot be deleted or overwritten once any file for
it is uploaded.

| Failure point | State | Recovery |
|---|---|---|
| Guard step failed (tag ≠ manifest) | nothing built/published | Fix `pyproject.toml` (or delete the bad tag), commit, re-tag with the matching version. No cost. |
| Publish failed before any upload | nothing on PyPI | Safe to re-run the workflow (`workflow_dispatch` re-run or re-push the tag). A stray attestation for an unpublished artifact is benign. |
| **Partial upload** (sdist up, wheel failed; or a retry hits an already-present file) | version is **burned** on PyPI | **Bump the patch version** in `pyproject.toml` (e.g. `0.2.0 → 0.2.1`), commit, and push a new matching tag (`v0.2.1`). The burned version number cannot be reclaimed. |

Do **not** add a `--skip-existing` flag to `uv publish` — surfacing the collision
is desirable. The B1 version guard prevents the most common cause of a burned
version (tag/manifest drift) in the first place.

---

## Dependabot PR workflow (release-adjacent)

- Dependabot opens PRs on `main`; **auto-merge is disabled** — every PR needs
  human review and merge.
- Apply the 7-day cooldown convention and the
  [dependency intake checklist](dependency-intake.md) to dependency-version PRs.
- Action SHA-pin PRs can generally be merged after CI passes, since actions are
  already pinned and the risk window is narrow.
