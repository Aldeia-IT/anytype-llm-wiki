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

## Pre-tag live smoke (required before every `v*` tag)

CI runs only mocked tests — the real Anytype wire is never exercised in CI. So
**every `v*` tag must be preceded by a live smoke** against a real Anytype space.
Run it after the release-prep commit is on `main` and before cutting the tag.

### Credentials — export the key; the binary does NOT load `.env`

The wiki clients resolve `ANYTYPE_API_KEY` from `os.environ` at call time
(`wiki/_base_client.py::_resolve_api_key`) — there is **no `load_dotenv`**. A key
that merely sits in `.env` is invisible to the installed binary; a missing/empty
key surfaces as `Illegal header value b'Bearer '`. `uv run` does not load `.env`
either. Always export first:

```bash
cd /Users/Shared/development/anytype-llm-wiki
set -a; source ./.env; set +a      # exports ANYTYPE_API_KEY into the environment
```

The canonical credential is the **aldeia-bot** API token in SOPS (`anytype.api_key`,
via `aldeia-box/scripts/secrets.sh get anytype.api_key`); the repo `.env` carries a
rendered copy. aldeia-bot is an **editor** on the live spaces and the local Anytype
daemon runs at `127.0.0.1:31012`. Full credential model:
`aldeia-box/docs/anytype-setup.md`.

### Target space

Use a **throwaway, populated, Jan-vault space** — `llm-wiki-2`
(`bafyreiacvp2vditsib3qv2h4wqqpdnjloix4if6s4jzcffeuaro4n3znre.h81a2ip0xaff`) or
`llm-wiki-test-2`. Always resolve **by space ID** and prefer the `.h81a2ip0xaff`
(Jan's vault) network — never the empty aldeia-bot-owned orphan spaces on
`meysp1f5qul1` (see `anytype-setup.md` → "Known orphan spaces").

### Steps

1. **Reinstall the runtime at the new version** so the installed binary matches the
   tag you are about to cut (the root-owned `/usr/local/bin` symlink error is
   harmless — the symlink already points at the updated uv-tools install):

   ```bash
   UV_TOOL_DIR=/usr/local/lib/uv-tools UV_TOOL_BIN_DIR=/usr/local/bin /opt/homebrew/bin/uv tool install --force \
     --no-cache --with 'idna>=3.15' --with 'pyjwt>=2.13.0' --with 'urllib3>=2.7.0' \
     --with 'starlette>=1.0.1' --with 'cryptography>=46.0.7' /Users/Shared/development/anytype-llm-wiki
   /usr/local/bin/anytype-llm-wiki wiki-lint --help    # confirms new subcommands exist
   ```

2. **Exercise the shipped tool(s) live** against the throwaway space; expect a
   non-error status and a written WikiLog receipt. For v0.5.0:

   ```bash
   /usr/local/bin/anytype-llm-wiki wiki-lint --space-id <llm-wiki-2 id> --json
   # expect: "status": "ok" | "partial", "wiki_log_id": non-null
   ```

   Run the new/changed command(s) for the release and eyeball the live output for
   the behavior the change introduced.

3. **Schema-affecting releases only:** round-trip through the Anytype desktop
   export → import and diff via the API (this caught the #303 display-name
   collision). Skip when `WIKI_SCHEMA_VERSION` is unchanged.

4. **Skip-gated live pytest** (optional — for surfaces CI can't reach, e.g. the D1
   `backlinks` field shape):

   ```bash
   set -a; source ./.env; set +a
   ANYTYPE_SPACE_ID=<id> ANYTYPE_BACKLINKED_OBJECT_ID=<object with inbound relations> \
     uv run pytest -m live tests/wiki/test_lint.py::TestLintLive -q
   ```

   A space with no inter-object relations cannot exercise backlink *element* shape —
   pick a populated space with real relations when the change depends on it.

Proceed to [Cutting a release](#cutting-a-release) only once the live smoke is clean.

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
