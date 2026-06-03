# Impl Review — #234 v0.2.0 tag-prep rework (Round 1)

**Date:** 2026-05-31
**Reviewer:** impl lead (inline review — scope is docs/CI/config, zero `src/` changes; all gates objectively verifiable and run directly)
**Branch:** aldeia/234-v0-2-0-tag-prep-checklist-anytype-llm-wiki-post-im
**Scope:** the four pipeline-doable council BLOCKING/ADVISORY tag-blockers + the remaining pipeline-doable advisories Jan asked to close ("address ALL recommendations").

## Verdict: APPROVED

All pipeline-doable council findings are addressed and verified. The maintainer/live-env gates
(B3, B4, B5, A5) are out of scope for a sandbox pass and are carried forward to the PR as a
Jan-owned tag-cut punch-list.

## Objective gates (run by the lead, real output)

| Gate | Result |
|------|--------|
| License gate — effective + passing: `uv run --frozen --with pip-licenses==5.5.5 python -m piplicenses --from=mixed --partial-match --fail-on="GPL;AGPL;SSPL;EUPL" --ignore-packages docutils` | **exit 0**, scans 85 packages |
| License gate — proven effective: same minus the waiver | **exit 1**, docutils the SOLE `fail-on` hit |
| `actionlint` on ci.yml + release.yml + audit.yml | **exit 0** (validates the A6 job split) |
| `uv run pytest` | **256 passed, 22 skipped, 3 xfailed** (+1 vs prior 255 = new publish-guard test) |
| `uv lock --check` | **exit 0** |
| `git status` / push | clean; branch pushed, 0 commits ahead of origin |

## Per-item findings

- **B1 (license gate)** — APPROVED. Fixed in BOTH `release.yml:53-73` and `audit.yml`. The fix corrects
  two defects: (1) the council's docutils GPL-classifier false positive (per-package `--ignore-packages`
  waiver, auditable comment, COPYING cross-ref, `--fail-on` tokens un-broadened); and (2) a lead-discovered
  defect the council missed — the prior `uvx` invocation ran in an isolated venv and scanned only ~3
  packages, making the gate a vacuous no-op. Now project-scoped via `uv run` against the synced tree.
  The gate is now both **effective** (catches real copyleft) and **passing** (exit 0).
- **B2 (launchd plist)** — APPROVED. `ProgramArguments` repointed from the non-existent `uv tool install`
  path to absolute-`uv` + `run --directory <repo>`, matching the README cron form. Plist header + README
  launchd block updated consistently.
- **A1 (publish-guard test)** — APPROVED. `TestPublishGuard` asserts the release.yml publish step's `if:`
  contains both `vars.PYPI_PUBLISH_ENABLED == 'true'` and `inputs.skip_publish != true`. Green.
- **A2 (CONTRIBUTING tree)** — APPROVED. `wiki/` subpackage added with all headline modules; matches the
  real `src/` layout.
- **A3 (MIGRATIONS commands)** — APPROVED. All three bare commands `uv run`-prefixed.
- **A4 (NOTICE inventory)** — APPROVED. Full transitive inventory appended (generated from resolved
  `uv.lock`); certifi MPL-2.0 documented as no-action; docutils classifier explained with cross-ref.
  Existing direct-dependency attribution preserved.
- **A6 (publish job split)** — APPROVED. `audit → build → publish`. `environment: pypi` now gates ONLY the
  `publish` job, so future required-reviewer protection no longer pauses unattended git-tag-only builds.
  Artifact handoff via SHA-pinned `upload-artifact@v4.6.2` / `download-artifact@v4.3.0`; `id-token`/
  `attestations` on build, `id-token` on publish; publish guard preserved verbatim. actionlint-clean.
- **A7 (log rotation)** — APPROVED. README newsyslog.d guidance added near Auto-reindex.
- **A8 (official anytype-mcp differentiation)** — APPROVED. Accurate, hedged note (no superlative);
  legally defensible — states the official `anyproto/anytype-mcp` offers API object access without built-in
  semantic search, our differentiator.

## Out of scope — maintainer/live-env tag-cut gates (documented in PR, Jan-owned)

- **B3** SECURITY.md reporting channels must be made operable (enable GitHub private vuln reporting; add
  org-profile/backup email) before tag.
- **B4** "No telemetry / data stays local" claim needs live egress verification before the public claim ships.
- **B5** Live-env gates: `verify-anytype-writes.sh` + `patch-decision.md`; `doctor` strict exit-0; p95<30s
  bootstrap on Mac Mini M4; `wiki-bootstrap --space-id <real>` demo; validate guessed `wiki_client.py` REST
  endpoints; cross-host bootstrap dedup probe.
- **A5** Copyright-holder entity name (Aldeia IT vs "Aldeia IT Consulting" vs individual) — Jan's legal call,
  not guessed.

## Reconciliation note

ci.yml scanner scope was intentionally NOT changed: the fast-PR-CI + weekly-`audit.yml` + tag-`release.yml`
split is the #231 design the council blessed. Recorded so this is not read as an omission of checklist item 1.
