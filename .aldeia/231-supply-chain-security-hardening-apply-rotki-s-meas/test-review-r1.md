# Test Review: supply-chain-security-hardening Round 1

**Verdict: APPROVED**

## Review Date
2026-05-31

## 1. Spec Coverage

All in-scope ACs from the spec and addendum item 4 have at least one meaningful test assertion. Cross-reference:

| Criterion | Tests Present | Assertion Meaningful | Notes |
|-----------|--------------|---------------------|-------|
| AC1 — Lockfile frozen (ci.yml) | `test_ci_yml_lockfile_check_and_frozen_sync` | YES — asserts both `uv lock --check` and `uv sync --frozen` | |
| AC1 — Lockfile frozen (release.yml) | `test_release_yml_lockfile_check_present` | YES | Minor gap: only checks string presence once, not in both jobs (see item 2) |
| AC2 — SHA pins (ci, release, audit) | Three `test_*_all_uses_sha_pinned` tests | YES — format invariant via regex, not literal SHA | |
| AC2 — dependabot.yml exists | `test_dependabot_yml_exists` | YES | |
| AC3 — Cache-free release/audit | Two tests + `test_ci_yml_cache_enabled` | YES — all three workflow files covered | |
| AC4 — Provenance static presence | `test_release_yml_attest_action_referenced` + `test_readme_has_gh_attestation_verify_snippet` | YES — action reference + README snippet | |
| AC4 — Actual attestation (side-effect) | SKIP with rationale | Correctly excluded | |
| AC5 — OIDC static presence | `test_release_yml_id_token_write`, `test_release_yml_environment_pypi`, `test_no_workflow_contains_pypi_secret` | YES | |
| AC5 — Live Environment (side-effect) | SKIP with rationale | Correctly excluded | |
| AC6 — Intake checklist + CONTRIBUTING | Two tests | YES — keyword-based seven-section check + link check | Minor soft-pass risk on 'release'/'license' keywords (see item 2) |
| AC7 — Python matrix | `test_ci_yml_python_matrix_contains_311_and_313` | YES — checks both `"3.11"` and `"3.13"` with quote variants | |
| AC8 — Version guard static + ordering | `test_release_yml_version_guard_step_exists_and_precedes_build` | YES — positional ordering via `text.index()` | |
| AC8 — Mismatch behavior (side-effect) | SKIP with rationale | Correctly excluded | |
| SF-7 — Hatchling exact pin | `test_pyproject_toml_hatchling_exact_pin` | YES — format invariant, not `1.27.0` | |
| Dependabot ecosystems | Two `TestDependabotConfig` tests | YES — accepts `uv` OR `pip` per spec contingency | |
| Addendum item 1 (green suite precondition) | None | Correctly excluded — meta-requirement for impl phase | |
| Addendum item 2 (scriptable AC5 gate) | None | Correctly excluded — behavioral, requires live GitHub | |

PASSED — every in-scope AC has a corresponding test. Side-effect ACs are correctly marked as SKIP, not omitted silently.

## 2. Edge Case Coverage

**AC2 SHA-pin check — empty file guard:**
The `_assert_no_unpinned_uses` helper asserts `len(uses_lines) > 0` before checking the unpinned list. A workflow file with zero `uses:` lines fails with a clear message rather than silently passing. This guard is correct and prevents the most dangerous soft-pass scenario.

**AC1 release.yml — both-jobs requirement:**
The spec states `uv lock --check` must appear in BOTH the `audit` job and the `build-and-publish` job. The test `test_release_yml_lockfile_check_present` only asserts `"uv lock --check" in text` (one occurrence sufficient). An implementation that includes it in only one of the two jobs would pass this test. This is a genuine gap relative to the spec's "BOTH jobs" language. However, the spec's own verification command (§AC1 detail: "confirm `release.yml` contains `uv lock --check` before `uv build`") is also presence-only, not a count assertion. The test faithfully mirrors the spec's greppable verification. Severity: SUGGESTION (the spec's own verification is weaker than the AC narrative; the test is consistent with the spec's stated verification).

**AC6 keyword false-pass risk:**
Two keywords have soft false-pass potential:
- `"release"` matches section 3 ("Release history") but could also match incidental mentions of "release workflow", "release cadence", or "release path" in an intake doc that omits the actual Release history checklist item.
- `"license"` matches section 5 ("License compatibility") but could also match an SPDX license header (`SPDX-License-Identifier: MIT`) in a doc that omits the License checklist section.

These are low-severity risks — a well-written intake doc is unlikely to mention these words without having the relevant sections. The debrief explicitly calls this a deliberate design choice (keyword match, not byte-exact), matching the addendum's intent to give the implementer prose freedom. Severity: SUGGESTION.

**Boundary/edge coverage otherwise adequate:**
- Partial SHA (39 chars) is correctly flagged as unpinned by the regex.
- Tag-pinned actions (`@v4`, `@main`) are correctly caught.
- SHA in comment-only position (e.g. `# de0fac2e...` without `@` prefix) does not produce a false negative.
- Quoted vs. unquoted Python version strings in AC7: the test requires quoted versions (`"3.11"` or `'3.11'`), which is correct since bare YAML floats would truncate 3.11 to 3.1.

PASSED with two suggestions noted.

## 3. Assertion Correctness

Each assertion was cross-referenced against the spec:

**AC1:** Asserts `"uv lock --check"` and `"uv sync --frozen"` — both are verbatim commands from spec §ci.yml. Correct.

**AC2:** Asserts format `@[0-9a-f]{40}` — exactly the pattern from spec §AC2 verification grep (`@[0-9a-f]\{40\}`). Correct. Does NOT hardcode specific SHA values from the spec table. Correct (addendum item 3 compliance).

**AC3:** Asserts `"enable-cache: false"` in release.yml and audit.yml; `"enable-cache: true"` in ci.yml. This matches spec §AC3 exactly.

**AC4:** Asserts `"actions/attest-build-provenance"` and `"subject-path: dist/*"` — matches spec §AC4 verbatim. Asserts `"gh attestation verify"` in README.md — matches spec §Deliverables (AC4 consumer-facing snippet, security SG-6). Correct.

**AC5:** Asserts `"id-token: write"`, `"environment: pypi"`, and absence of `"PYPI_TOKEN"`, `"pypi_token"`, `"password:"` — all match spec §AC5 verification. Correct.

**AC6:** Seven keywords match the seven checklist items in spec §7. The `"release"` keyword for section 3 is a weak discriminator (see item 2 suggestion), but it is the appropriate keyword for "Release history" and is consistent with the spec's section title.

**AC7:** Asserts `"3.11"` and `"3.13"` (quoted) and `"matrix"` presence — matches spec §AC7 verification (`grep -A2 'matrix:'`). The quoted-version requirement correctly excludes bare YAML floats. Correct.

**AC8:** Asserts `"Verify tag matches pyproject version"` appears before `"uv build"` using `text.index()`. The guard phrase matches the step name in spec §release.yml exactly. The ordering check correctly uses character position comparison. Correct.

**SF-7:** Asserts `hatchling==\d+\.\d+` — matches the spec's exact-pin requirement without asserting `1.27.0` specifically. Correct (addendum item 3 compliance). The regex would also accept `hatchling==1.27` (two-part version) which is a valid PEP 440 specifier; this is acceptable.

No assertion asserts the wrong expected output, uses the wrong comparison type, or is tautological.

PASSED.

## 4. Test Validity (will they fail now?)

`uv run pytest tests/test_ci_config.py -q` was run. Result: **21 failed, 3 skipped, exit 1** — exactly matching the debrief's documented expected state.

Failure modes are all `AssertionError` with clear messages (file-missing or content-missing), not import errors, collection errors, or attribute errors. No test passed on the current unimplemented codebase.

The three SKIP tests (`test_actual_attestation_verify`, `test_live_github_environment_protection`, `test_version_mismatch_exits_nonzero`) are correctly marked and excluded from the fail count.

The one existing test that touches the pre-existing `pyproject.toml` (`test_pyproject_toml_hatchling_exact_pin`) fails correctly because `pyproject.toml` currently has `requires = ["hatchling"]` (unpinned), not `hatchling==<version>`.

PASSED — all 21 active tests fail now, confirming they will gate the implementation correctly.

## 5. Convention Compliance

This is a Python/pytest project using stdlib-only tests. Applicable conventions:

**Stdlib-only imports:** The test file imports only `re`, `pathlib.Path`, and `pytest`. No PyYAML, no non-stdlib package. The `uv.lock` is unchanged by this test. PASSED.

**No hardcoded `/Users/` paths:** `REPO_ROOT` is derived from `Path(__file__).resolve().parents[1]` — portable. No absolute `/Users/` paths in test constants. PASSED.

**Pass/fail reporting:** pytest's built-in assertion reporting is used. The project does not use a bash `pass()`/`fail()` counter pattern (that convention is for bash projects; this is Python/pytest). PASSED.

**BASH_SOURCE guard:** Not applicable — Python project. PASSED.

**Overridable globals / MOCK_BIN pattern:** Not applicable — tests assert against static files on disk, no external tool invocations. PASSED.

**Temp directories:** No temp directories used (tests read existing files only). PASSED.

**Clear failure messages:** Every `assert` includes an f-string with the file path and AC reference. PASSED.

PASSED — all applicable conventions met.

## 6. Test Isolation

Each test is independently runnable. Verified:

- Tests share read-only access to `REPO_ROOT`-relative paths. No test mutates files.
- No test depends on another test having run first (no shared mutable state).
- `REPO_ROOT` is computed from `__file__` — no dependency on `cwd` or machine-specific state.
- No running services, specific user accounts, or home directory contents required.
- The skipped tests (`pass` body) have no side effects.
- `_assert_no_unpinned_uses` is a helper method, not a test — no ordering dependency.

PASSED.

## 7. Existing Test Impact

The following existing test files exist in `tests/`:
- `tests/test_anytype_client.py`
- `tests/test_chunker.py`
- `tests/test_embedder.py`
- `tests/test_indexer.py`
- `tests/test_server.py`

This spec adds CI configuration files (`.github/` directory), documentation files (`docs/`), and modifies `pyproject.toml` (`[build-system] requires`) and `CONTRIBUTING.md`. None of these changes affect the application source code under `src/anytype_llm_wiki/`.

The existing test files test application logic (Anytype client, chunker, embedder, indexer, server). They do not assert anything about `pyproject.toml`'s `[build-system]` section, workflow files, or documentation structure.

One non-obvious interaction: the `pyproject.toml` change adds `hatchling==<version>` to `[build-system] requires`. This changes how `uv build` resolves its build environment but does NOT affect `uv sync`, `uv run pytest`, or the test suite itself. Existing tests are unaffected.

PASSED — no existing tests are invalidated by this spec's implementation.

## Summary

The test file is well-constructed: it correctly asserts format invariants (not literal SHAs or version numbers), properly excludes side-effect ACs with clear skip rationale, guards against the empty-file soft-pass in the AC2 helper, uses portable path resolution, and fails clearly on the current unimplemented codebase (21 failed, 3 skipped, exit 1 confirmed). The traceability matrix in the debrief accurately reflects the implemented tests. Two suggestions are noted — a SUGGESTION to count `uv lock --check` occurrences in release.yml to enforce the both-jobs requirement, and a SUGGESTION to use more specific keywords for AC6 sections 3 and 5 — but neither rises to BLOCKING or SHOULD-FIX given that the spec's own verification commands are presence-only and the keyword choice is a deliberate design decision documented in the debrief. All 7 checklist items pass.
