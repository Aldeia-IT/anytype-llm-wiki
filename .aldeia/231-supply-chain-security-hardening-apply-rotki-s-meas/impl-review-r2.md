# Implementation Review — Round 2 (re-review) — #231

**Date:** 2026-05-31
**Verdict:** **APPROVED** (0 BLOCKING, 0 SHOULD-FIX)

Round-1 findings B1, B2, SF1 verified resolved by lead inline re-review (read the actual changed lines + re-ran all gates).

## Findings dispositions
- **B1 (gitleaks history) — RESOLVED.** `release.yml:68` and `audit.yml:59` now run `gitleaks git . --redact --exit-code 1`; `fetch-depth: 0` added to the gitleaks-running `actions/checkout` in both files (SHA pin intact). `build-and-publish` checkout left shallow (correct — it doesn't run gitleaks). test_ci_config asserts `gitleaks git`.
- **B2 (pip-licenses gate) — RESOLVED.** Both invocations now `--from=mixed --partial-match --fail-on="GPL;AGPL;SSPL;EUPL"` with explanatory comment; test_ci_config asserts `--partial-match`; `docs/dependency-intake.md` notes UNKNOWN-license deps are a manual blocker.
- **SF1 (probe robustness) — RESOLVED.** `resp.raise_for_status()` added to all 7 reachability probes across the 4 test files; `except httpx.HTTPError:` retained (catches HTTPStatusError). CONTRIBUTING note added.

## Lead verification (actual)
- `uv lock --check` → exit 0.
- AC2 SHA-pin grep → zero unpinned. Secrets grep → zero.
- `tests/test_ci_config.py` → 27 passed, 3 skipped (the 3 intentional side-effect skips).
- Service-less full suite (CI-equivalent) → 40 passed, 26 skipped, exit 0 on BOTH 3.11 and 3.13.
- Fixer-reported naive-local run (host services up) → 0 failures on both interpreters (previously 6 test_server failures); the SF1 fix makes reachable-but-401 services skip.
- Working tree clean; no `__pycache__` tracked.

**Rounds used:** 2 of 3. Implementation approved for PR.
