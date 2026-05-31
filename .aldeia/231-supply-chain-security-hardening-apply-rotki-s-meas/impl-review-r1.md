# Implementation Review — Round 1 — #231 Supply-Chain Hardening

**Date:** 2026-05-31
**Reviewers:** chief-security-officer (control-correctness), chief-technology-officer (AC/spec compliance) + lead inline checks
**Verdict:** **NEEDS CHANGES** (2 BLOCKING control-correctness defects; advisories folded in)

The deliverable is structurally complete and AC-compliant on every static check (CTO verified AC1–AC8, SF-7, all addendum items, hardened SHA-pin regex, 25/3 test_ci_config pass). However, two of the three NEW OSS-hygiene scanners (fold-244 item 9) are "green build, no actual protection" — they pass CI but do not enforce what they claim. Preserving the higher of the two reviewers' severities (consolidation rule: never downgrade), both are BLOCKING.

---

## BLOCKING

### B1 — gitleaks scans the working tree, not git history (control under-scoped)
**Files:** `.github/workflows/release.yml:53-56`, `.github/workflows/audit.yml:44-47`
The impl runs `gitleaks dir . --redact --exit-code 1`. In gitleaks v8, `dir` scans only on-disk files in their current state; `git` scans commit history. fold-244 item 9 requires secret scanning "over the repo/**history**." The dominant leak scenario — a secret committed then deleted in a later commit — lives only in history and is never seen by `gitleaks dir`. Compounding: the `actions/checkout` steps use the default shallow clone, which would defeat history scanning even after switching subcommands.
**Fix:**
- Change both invocations to `gitleaks git . --redact --exit-code 1`.
- Add `with: { fetch-depth: 0 }` to the `actions/checkout` step in the gitleaks-running job in BOTH `release.yml` (audit job) and `audit.yml`.
- Tighten the `tests/test_ci_config.py` scanner assertion to require `gitleaks git` (not merely `gitleaks`) so a regression to `dir` fails CI.

### B2 — pip-licenses copyleft gate never fires (exact-match, missing `--partial-match`)
**Files:** `.github/workflows/release.yml:49-51`, `.github/workflows/audit.yml:40-42`
`uvx pip-licenses==5.5.5 --from=mixed --fail-on="GPL;AGPL;SSPL;EUPL"`. Per the pip-licenses 5.5.5 source (CSO read it), `--fail-on` without `--partial-match` does case-insensitive EXACT set-membership. With `--from=mixed` the compared string is an SPDX expression (`GPL-3.0-only`, `AGPL-3.0-or-later`) or a Trove classifier — neither ever equals the bare token `GPL`/`AGPL`/`SSPL`/`EUPL`. So a genuinely GPL/AGPL dependency passes the gate. This is a licensing-exposure risk for an MIT public release, not only a technical gap.
**Fix:**
- Add `--partial-match` to both invocations: `uvx pip-licenses==5.5.5 --from=mixed --partial-match --fail-on="GPL;AGPL;SSPL;EUPL"`.
- Note in a YAML comment that `--partial-match` with `GPL` also flags `LGPL` (acceptable/conservative for MIT).
- Tighten the `tests/test_ci_config.py` assertion to require `--partial-match` alongside `pip-licenses` so the weak form cannot regress.
- UNKNOWN-license deps are still not blocked by `--fail-on` (advisory) — `docs/dependency-intake.md` should state UNKNOWN is a manual blocker (confirm it does).

---

## SHOULD-FIX

### SF1 — Green-suite robustness: reachable-but-unauthorized service does not skip (addendum-r1 item 1)
**Files:** `tests/test_server.py`, `tests/test_indexer.py`, `tests/test_anytype_client.py`, `tests/test_embedder.py`
The skip-guard probes do `httpx.get(...)` without `raise_for_status()`. A reachable service returning 401/403/5xx (e.g., an authenticated Qdrant on the dev host) does NOT raise → guard returns "available" → the test runs and fails inside the client. CTO verified 6 `test_server` tests fail on this host for exactly this reason (Qdrant returns 401). This is NOT a CI risk (GitHub runners have no services → ConnectError → skip → green; lead independently confirmed 38 passed/26 skipped on 3.11+3.13 under a service-less env) and NOT a regression from this diff. But addendum-r1 item 1 made green-on-both-interpreters a load-bearing gate "or document the gap explicitly."
**Fix (preferred — makes the suite robust on ANY host, fully satisfying the gate):** add `.raise_for_status()` to each reachability probe so an HTTP error status is treated as "not available" → skip. Then verify `uv run pytest` (no URL overrides) is green on this host too. Add a one-line note to `CONTRIBUTING.md` testing section that integration tests skip when services are absent or not successfully reachable.

---

## ADVISORY (no change required; recorded)

- **A1 — `go install ...@vX.Y.Z` integrity (actionlint, gitleaks):** version-tag installs verified via Go checksum DB (GOSUMDB) — stronger than a mutable Action tag, weaker than a local hash pin. Accepted residual; the build toolchain (preinstalled Go on ubuntu-latest) is an unpinned input. Not blocking.
- **A2 — release `audit` job now installs `--all-extras`** for the license scan. This is on the UNPRIVILEGED audit job; the privileged `build-and-publish` job stays install-free (SF-10 intent preserved). Slightly longer audit runtime, within the spec's 30–90s note. No action.
- **A3 — bandit** verified exits non-zero on findings by default (CSO ran it). No severity floor / no `.bandit` baseline → a single finding red-lines a release (security-correct, operationally noisy). Acceptable per fold-244 (a documented baseline is permitted if needed later).

---

## Verified CORRECT (no action)
OIDC publish gate (`environment: pypi` + job-scoped `id-token: write`, version-guard ordered before build/attest/publish — AC8), SHA-pin completeness (AC2, zero unpinned), cache policy (AC3), provenance + README snippet (AC4), no secrets / `docs/releasing.md` exits-non-zero Environment hard-gate (AC5), 7 substantive intake sections + CONTRIBUTING link (AC6), 3.11/3.13 matrix (AC7), hatchling==1.29.0 (SF-7), dependabot github-actions+uv-only (#13426 resolved), SECURITY.md correctly absent (item 10), hardened SHA-pin regex closes the trailing-comment soft-pass (item 4, proven by execution), actionlint gate covering all three workflows (item 3).

**Rounds used:** 1 of 3. Re-review required after B1, B2, SF1 fixes.
