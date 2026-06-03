"""Static-assertion tests for supply-chain security hardening CI config (#231).

All tests parse files as text using stdlib only (pathlib + re).
No PyYAML or non-stdlib imports are used.

These tests are EXPECTED TO FAIL until the implementation phase creates:
  .github/workflows/ci.yml
  .github/workflows/release.yml
  .github/workflows/audit.yml
  .github/dependabot.yml
  docs/dependency-intake.md
  CONTRIBUTING.md (updated to reference docs/dependency-intake.md)
  README.md (updated with gh attestation verify snippet)
  pyproject.toml ([build-system] requires pinned to hatchling==<version>)
"""

import re
from pathlib import Path

import pytest

# Resolve repo root robustly — two levels up from this test file (tests/test_ci_config.py)
REPO_ROOT = Path(__file__).resolve().parents[1]

CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
RELEASE_YML = REPO_ROOT / ".github" / "workflows" / "release.yml"
AUDIT_YML = REPO_ROOT / ".github" / "workflows" / "audit.yml"
DEPENDABOT_YML = REPO_ROOT / ".github" / "dependabot.yml"
INTAKE_MD = REPO_ROOT / "docs" / "dependency-intake.md"
CONTRIBUTING_MD = REPO_ROOT / "CONTRIBUTING.md"
README_MD = REPO_ROOT / "README.md"
PYPROJECT_TOML = REPO_ROOT / "pyproject.toml"

# Regex matching a SHA-pinned `uses:` value: anything@<40-hex-chars>
_SHA_PIN_RE = re.compile(r"uses:\s+\S+@[0-9a-f]{40}")
# Regex to identify ANY `uses:` line and capture its reference TOKEN (the value
# immediately after `uses:`, up to the first whitespace). Anchoring to the token —
# rather than scanning the whole line — closes the trailing-comment soft-pass where a
# tag-pinned action (`uses: foo/bar@v4  # pinned-from @<40-hex>`) carries a 40-hex
# string only in its `# …` comment (post-test addendum item 4 / Council-ADV-3).
_USES_TOKEN_RE = re.compile(r"^\s+(?:-\s+)?uses:\s+(\S+)", re.MULTILINE)
# A correctly SHA-pinned reference token: the value must itself end in @<40-hex>.
_TOKEN_PINNED_RE = re.compile(r"\S+@[0-9a-f]{40}$")


def _read(path: Path) -> str:
    """Read a file, failing with a clear message if it does not exist."""
    assert path.exists(), (
        f"Required file missing (not yet created by impl phase): {path}\n"
        "This file must be created by the implementation phase for this test to pass."
    )
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# AC1 — Lockfile-frozen installs enforced in CI
# Spec ref: AC1 detail (spec.md ~571), Test Plan "Validate lockfile-check gate"
# ---------------------------------------------------------------------------

class TestAC1LockfileFrozen:
    """AC1: every CI and release path enforces uv lock --check + uv sync --frozen."""

    def test_ci_yml_lockfile_check_and_frozen_sync(self):
        """AC1: ci.yml must contain both 'uv lock --check' and 'uv sync --frozen'."""
        # AC1: ci.yml enforces lockfile consistency before installing deps
        text = _read(CI_YML)
        assert "uv lock --check" in text, (
            f"ci.yml is missing 'uv lock --check' (AC1 lockfile gate): {CI_YML}"
        )
        assert "uv sync --frozen" in text, (
            f"ci.yml is missing 'uv sync --frozen' (AC1 frozen install): {CI_YML}"
        )

    def test_release_yml_lockfile_check_present(self):
        """AC1: release.yml must contain 'uv lock --check' (on the release path, both jobs)."""
        # AC1: release path re-asserts lockfile consistency so a tag pushed to a
        # commit that bypassed the merge-gate cannot build from a drifted lockfile (SF-2).
        text = _read(RELEASE_YML)
        count = text.count("uv lock --check")
        assert count >= 2, (
            f"release.yml must run 'uv lock --check' on the release path in BOTH the audit job "
            f"and the build-and-publish job (AC1 / SF-2: a tag pushed to a commit that bypassed "
            f"the merge-gate must not build from a drifted lockfile). Found {count} occurrence(s), "
            f"expected >= 2: {RELEASE_YML}"
        )


# ---------------------------------------------------------------------------
# AC2 — All GitHub Actions pinned to full commit SHAs
# Spec ref: AC2 detail (spec.md ~582), Test Plan "Validate SHA-pin coverage"
# Addendum item 4: assert the FORMAT invariant, NOT specific SHA values
# ---------------------------------------------------------------------------

class TestAC2ShaPinnedActions:
    """AC2: every uses: line across all workflow files must be SHA-pinned."""

    def _assert_no_unpinned_uses(self, path: Path) -> None:
        text = _read(path)
        # Capture the reference TOKEN of every `uses:` line (the value before any
        # trailing `# …` comment, which `\S+` naturally stops at on whitespace).
        tokens = _USES_TOKEN_RE.findall(text)
        assert len(tokens) > 0, (
            f"{path.name} has no 'uses:' lines at all — the workflow looks empty or malformed."
        )
        unpinned = [tok for tok in tokens if not _TOKEN_PINNED_RE.match(tok)]
        assert unpinned == [], (
            f"{path.name} contains {len(unpinned)} unpinned 'uses:' reference(s) "
            f"(the token after 'uses:' must itself end in @[0-9a-f]{{40}}). "
            f"Every action reference must use a full 40-character commit SHA, not a tag or "
            f"branch — and a 40-hex SHA hiding in a trailing comment does not count. "
            f"Offending token(s): {unpinned} in {path}"
        )

    def test_ci_yml_all_uses_sha_pinned(self):
        """AC2: ci.yml — zero unpinned uses: lines."""
        self._assert_no_unpinned_uses(CI_YML)

    def test_release_yml_all_uses_sha_pinned(self):
        """AC2: release.yml — zero unpinned uses: lines."""
        self._assert_no_unpinned_uses(RELEASE_YML)

    def test_audit_yml_all_uses_sha_pinned(self):
        """AC2: audit.yml — zero unpinned uses: lines."""
        self._assert_no_unpinned_uses(AUDIT_YML)

    def test_dependabot_yml_exists(self):
        """AC2 currency: dependabot.yml must exist (keeps SHA pins up to date)."""
        assert DEPENDABOT_YML.exists(), (
            f"Required file missing: {DEPENDABOT_YML}\n"
            "dependabot.yml is needed to keep SHA-pinned actions up to date (AC2)."
        )


# ---------------------------------------------------------------------------
# AC3 — Release workflows build cache-free
# Spec ref: AC3 detail (spec.md ~588)
# Addendum item 4: assert cache settings in all three workflow files
# ---------------------------------------------------------------------------

class TestAC3CacheFreeRelease:
    """AC3: release and audit workflows disable cache; CI enables it."""

    def test_release_yml_cache_disabled(self):
        """AC3: release.yml must set enable-cache: false on astral-sh/setup-uv."""
        text = _read(RELEASE_YML)
        assert "enable-cache: false" in text, (
            f"release.yml must contain 'enable-cache: false' to prevent cache-poisoning "
            f"of published artifacts (AC3): {RELEASE_YML}"
        )

    def test_audit_yml_cache_disabled(self):
        """AC3: audit.yml must set enable-cache: false on astral-sh/setup-uv."""
        text = _read(AUDIT_YML)
        assert "enable-cache: false" in text, (
            f"audit.yml must contain 'enable-cache: false' (AC3): {AUDIT_YML}"
        )

    def test_ci_yml_cache_enabled(self):
        """AC3: ci.yml must set enable-cache: true (dev-speed cache is intentional for merge-gate)."""
        text = _read(CI_YML)
        assert "enable-cache: true" in text, (
            f"ci.yml must contain 'enable-cache: true' (AC3 — merge-gate uses cache for speed): {CI_YML}"
        )


# ---------------------------------------------------------------------------
# AC4 — Build-provenance attestation on published artifacts (static presence only)
# Spec ref: AC4 detail (spec.md ~593)
# Addendum item 4: static presence only — do NOT attempt to run actual attestation
# ---------------------------------------------------------------------------

class TestAC4Provenance:
    """AC4: release.yml references attest-build-provenance; README has verify snippet."""

    def test_release_yml_attest_action_referenced(self):
        """AC4: release.yml must reference actions/attest-build-provenance with subject-path: dist/*."""
        text = _read(RELEASE_YML)
        assert "actions/attest-build-provenance" in text, (
            f"release.yml must reference 'actions/attest-build-provenance' (AC4): {RELEASE_YML}"
        )
        assert "subject-path: dist/*" in text, (
            f"release.yml must specify 'subject-path: dist/*' for attest-build-provenance (AC4): {RELEASE_YML}"
        )

    def test_readme_has_gh_attestation_verify_snippet(self):
        """AC4: README.md must contain a 'gh attestation verify' snippet (consumer-facing provenance)."""
        text = _read(README_MD)
        assert "gh attestation verify" in text, (
            f"README.md must contain a 'gh attestation verify' snippet for consumer provenance "
            f"verification (AC4 / security SG-6): {README_MD}"
        )

    @pytest.mark.skip(
        reason="side-effect / runbook-verified — actual attestation verification requires "
               "a real published artifact and live GitHub attestation store. "
               "See docs/releasing.md for the manual first-release checklist. (AC4)"
    )
    def test_actual_attestation_verify(self):
        """AC4 side-effect: gh attestation verify exits 0 for a real published wheel."""
        pass


# ---------------------------------------------------------------------------
# AC5 — OIDC Trusted Publishing, no long-lived secrets (static presence only)
# Spec ref: AC5 detail (spec.md ~600)
# Addendum item 4: static grep-able assertions; do NOT test live Environment API
# ---------------------------------------------------------------------------

class TestAC5OidcAndNoSecrets:
    """AC5: release.yml uses OIDC (id-token: write + environment: pypi); no PYPI_TOKEN."""

    def test_release_yml_id_token_write(self):
        """AC5: release.yml must contain 'id-token: write' for OIDC Trusted Publishing."""
        text = _read(RELEASE_YML)
        assert "id-token: write" in text, (
            f"release.yml must contain 'id-token: write' for OIDC (AC5): {RELEASE_YML}"
        )

    def test_release_yml_environment_pypi(self):
        """AC5: release.yml must reference 'environment: pypi' (GitHub Environment gate)."""
        text = _read(RELEASE_YML)
        assert "environment: pypi" in text, (
            f"release.yml must contain 'environment: pypi' for the reviewer-protected "
            f"publish gate (AC5): {RELEASE_YML}"
        )

    def test_no_workflow_contains_pypi_secret(self):
        """AC5: no workflow file may contain PYPI_TOKEN, pypi_token, or a password: key."""
        for path in (CI_YML, RELEASE_YML, AUDIT_YML):
            text = _read(path)
            for forbidden in ("PYPI_TOKEN", "pypi_token", "password:"):
                assert forbidden not in text, (
                    f"{path.name} must NOT contain '{forbidden}' — OIDC replaces long-lived "
                    f"secrets (AC5): {path}"
                )

    @pytest.mark.skip(
        reason="side-effect / runbook-verified — the GitHub Environment pypi must have "
               "required reviewers and a v* tag policy, verified via 'gh api' before first "
               "release. See docs/releasing.md for the mandatory pre-release gate check. (AC5)"
    )
    def test_live_github_environment_protection(self):
        """AC5 side-effect: gh api confirms required-reviewer + v* tag policy on pypi Environment."""
        pass


# ---------------------------------------------------------------------------
# #234 ADVISORY-1 — PYPI_PUBLISH_ENABLED publish-guard regression test
# The publish step's `if:` is the SINGLE control preventing accidental PyPI
# publish (git-tag-only until the maintainer opts in). A future edit could
# weaken it undetected — this test pins both halves of the guard expression.
# ---------------------------------------------------------------------------

class TestPublishGuard:
    """The release.yml publish step must be guarded by BOTH PYPI_PUBLISH_ENABLED and skip_publish."""

    def test_release_yml_publish_guard_expression(self):
        """#234: the publish step's `if:` must contain both gate halves so the project
        stays git-tag-only (nothing published) until PYPI_PUBLISH_ENABLED is set true,
        and so the workflow_dispatch dry-run (skip_publish) never publishes."""
        text = _read(RELEASE_YML)
        assert "vars.PYPI_PUBLISH_ENABLED == 'true'" in text, (
            f"release.yml publish step must gate on \"vars.PYPI_PUBLISH_ENABLED == 'true'\" — "
            f"this repo variable is the single control keeping the project git-tag-only "
            f"(no accidental PyPI publish): {RELEASE_YML}"
        )
        assert "inputs.skip_publish != true" in text, (
            f"release.yml publish step must gate on 'inputs.skip_publish != true' so the "
            f"workflow_dispatch dry-run path never publishes: {RELEASE_YML}"
        )


# ---------------------------------------------------------------------------
# AC6 — Dependency-intake checklist documented in the repo
# Spec ref: AC6 detail (spec.md ~619), §7 Dependency-Intake Checklist (~538)
# Addendum item 4: assert seven sections are present (beyond mere file existence)
# ---------------------------------------------------------------------------

class TestAC6DependencyIntakeChecklist:
    """AC6: docs/dependency-intake.md exists with all seven checklist sections; CONTRIBUTING.md links to it."""

    # The seven enumerated checklist topics from spec §7 (spec.md ~541-548).
    # Assert each keyword/concept is present — NOT a byte-exact match so impl can reword prose.
    _CHECKLIST_SECTIONS = [
        ("necessity", "Necessity — can we implement this ourselves / is vendoring appropriate"),
        ("maintainer", "Maintainer health — reputation, activity, succession"),
        ("release", "Release history — recent advisories, suspicious releases"),
        ("transitive", "Transitive impact — uv add --dry-run, CVE scan"),
        ("license", "License compatibility — MIT-compatible check"),
        ("cooldown", "Cooldown — defer if released < 7 days ago"),
        ("decision", "Decision record — document the outcome in the PR"),
    ]

    def test_intake_md_exists_with_all_seven_sections(self):
        """AC6: docs/dependency-intake.md must exist and contain all seven checklist topics."""
        text = _read(INTAKE_MD)
        missing = []
        for keyword, description in self._CHECKLIST_SECTIONS:
            if keyword.lower() not in text.lower():
                missing.append(f"  - '{keyword}' ({description})")
        assert not missing, (
            f"docs/dependency-intake.md is missing {len(missing)} of the seven required "
            f"checklist section(s):\n" + "\n".join(missing) + f"\n(AC6, spec §7): {INTAKE_MD}"
        )

    def test_contributing_md_references_dependency_intake(self):
        """AC6: CONTRIBUTING.md must reference docs/dependency-intake.md."""
        text = _read(CONTRIBUTING_MD)
        assert "docs/dependency-intake.md" in text, (
            f"CONTRIBUTING.md must contain a reference to 'docs/dependency-intake.md' (AC6): {CONTRIBUTING_MD}"
        )


# ---------------------------------------------------------------------------
# AC7 — Python version matrix (3.11 and 3.13)
# Spec ref: AC7 detail (spec.md ~625), Test Plan "Verify Python matrix"
# ---------------------------------------------------------------------------

class TestAC7PythonMatrix:
    """AC7: ci.yml test job must declare a matrix covering Python 3.11 and 3.13."""

    def test_ci_yml_python_matrix_contains_311_and_313(self):
        """AC7: ci.yml must declare a matrix with both '3.11' and '3.13'."""
        text = _read(CI_YML)
        assert '"3.11"' in text or "'3.11'" in text, (
            f"ci.yml matrix must include Python 3.11 (minimum supported, AC7): {CI_YML}"
        )
        assert '"3.13"' in text or "'3.13'" in text, (
            f"ci.yml matrix must include Python 3.13 (current latest, AC7): {CI_YML}"
        )
        assert "matrix" in text, (
            f"ci.yml must declare a 'matrix' strategy block (AC7): {CI_YML}"
        )


# ---------------------------------------------------------------------------
# AC8 — Tag version guard before build (static presence + ordering only)
# Spec ref: AC8 detail (spec.md ~632), Test Plan "Verify the version guard"
# Addendum item 4: static presence + ordering only; do NOT test actual mismatch behavior
# ---------------------------------------------------------------------------

class TestAC8VersionGuard:
    """AC8: release.yml must contain the version-guard step before the build step."""

    def test_release_yml_version_guard_step_exists_and_precedes_build(self):
        """AC8: 'Verify tag matches pyproject version' step must appear BEFORE 'uv build' / Build distributions."""
        text = _read(RELEASE_YML)

        guard_phrase = "Verify tag matches pyproject version"
        build_phrase = "uv build"

        assert guard_phrase in text, (
            f"release.yml must contain the '{guard_phrase}' step (AC8 version guard): {RELEASE_YML}"
        )
        assert build_phrase in text, (
            f"release.yml must contain '{build_phrase}' (build step, AC8): {RELEASE_YML}"
        )

        guard_pos = text.index(guard_phrase)
        build_pos = text.index(build_phrase)
        assert guard_pos < build_pos, (
            f"release.yml: '{guard_phrase}' (pos {guard_pos}) must appear BEFORE "
            f"'{build_phrase}' (pos {build_pos}) — the guard must abort before any build "
            f"side-effect runs (AC8 B1): {RELEASE_YML}"
        )

    @pytest.mark.skip(
        reason="side-effect / runbook-verified — testing actual mismatch behavior requires "
               "pushing a real tag (e.g. v9.9.9) against a mismatched pyproject.toml. "
               "See docs/releasing.md for the dry-run test procedure. (AC8)"
    )
    def test_version_mismatch_exits_nonzero(self):
        """AC8 side-effect: pushing a tag that disagrees with pyproject.toml fails before build."""
        pass


# ---------------------------------------------------------------------------
# SF-7 / Build-backend pin — pyproject.toml hatchling exact-version pin
# Spec ref: §Deliverables "Build-backend pin" (spec.md ~563), Addendum item 3
# Assert the == pin FORMAT; do NOT assert a specific version number
# ---------------------------------------------------------------------------

class TestSF7BuildBackendPin:
    """SF-7: pyproject.toml [build-system] requires must pin hatchling to an exact version."""

    def test_pyproject_toml_hatchling_exact_pin(self):
        """SF-7: pyproject.toml must contain 'hatchling==<version>' (exact pin, not a range)."""
        text = _read(PYPROJECT_TOML)
        # Assert the == pin FORMAT — not a specific version (addendum item 3)
        match = re.search(r'hatchling==\d+\.\d+', text)
        assert match is not None, (
            f"pyproject.toml [build-system] requires must pin hatchling with an exact '==' version "
            f"(e.g. hatchling==1.27.0), not a range or bare 'hatchling'. "
            f"Current content does not contain 'hatchling==<version>'. "
            f"(SF-7 build-backend hardening): {PYPROJECT_TOML}"
        )


# ---------------------------------------------------------------------------
# dependabot.yml — declares both github-actions and pip/uv ecosystems
# Spec ref: §Deliverables "dependabot (AC2 currency)" (spec.md ~822-860)
# ---------------------------------------------------------------------------

class TestDependabotConfig:
    """dependabot.yml must declare the github-actions and uv/pip ecosystems."""

    def test_dependabot_yml_declares_github_actions_ecosystem(self):
        """dependabot.yml must include the github-actions package-ecosystem."""
        text = _read(DEPENDABOT_YML)
        assert "github-actions" in text, (
            f"dependabot.yml must declare the 'github-actions' package-ecosystem "
            f"to keep SHA-pinned action references up to date (AC2 currency): {DEPENDABOT_YML}"
        )

    def test_dependabot_yml_declares_python_ecosystem(self):
        """dependabot.yml must include uv or pip package-ecosystem for Python deps."""
        text = _read(DEPENDABOT_YML)
        has_uv = "uv" in text
        has_pip = "pip" in text
        assert has_uv or has_pip, (
            f"dependabot.yml must declare either the 'uv' or 'pip' package-ecosystem "
            f"to keep Python dependencies up to date (AC2 currency): {DEPENDABOT_YML}"
        )


# ---------------------------------------------------------------------------
# fold #244 — OSS-hygiene scanner suite present on the TAG/audit path
# Spec ref: spec-addendum-fold-244.md item 9 (bandit / pip-licenses / gitleaks).
# String-presence is sufficient here, mirroring the other static CI-config tests.
# ---------------------------------------------------------------------------

class TestFold244OssHygieneScanners:
    """The bandit, pip-licenses, and gitleaks scanners must appear on the tag/audit path."""

    def test_bandit_present_on_tag_or_audit_path(self):
        """fold-244: bandit (Python SAST) must run in release.yml and/or audit.yml."""
        in_release = "bandit" in _read(RELEASE_YML)
        in_audit = "bandit" in _read(AUDIT_YML)
        assert in_release or in_audit, (
            "bandit (Python static analysis) must appear in release.yml and/or audit.yml "
            "(fold #244 OSS-hygiene scanner suite)."
        )

    def test_pip_licenses_present_on_tag_or_audit_path(self):
        """fold-244: pip-licenses (license compatibility) must run in release.yml and/or audit.yml."""
        in_release = "pip-licenses" in _read(RELEASE_YML)
        in_audit = "pip-licenses" in _read(AUDIT_YML)
        assert in_release or in_audit, (
            "pip-licenses (license compatibility) must appear in release.yml and/or audit.yml "
            "(fold #244 OSS-hygiene scanner suite)."
        )

    def test_pip_licenses_uses_partial_match(self):
        """B2: wherever pip-licenses runs, it must pass --partial-match so the copyleft
        --fail-on gate actually fires (exact set-membership never equals the bare
        GPL/AGPL/SSPL/EUPL token, e.g. 'GPL-3.0-only' != 'GPL')."""
        for path in (RELEASE_YML, AUDIT_YML):
            text = _read(path)
            if "pip-licenses" in text:
                assert "--partial-match" in text, (
                    f"{path.name} runs pip-licenses but is missing '--partial-match'. Without it "
                    f"'--fail-on' exact-matches license strings that never equal the bare token "
                    f"(e.g. 'GPL-3.0-only' != 'GPL'), so the copyleft gate silently passes "
                    f"GPL/AGPL deps (B2): {path}"
                )

    def test_gitleaks_present_on_tag_or_audit_path(self):
        """fold-244: gitleaks (secret scanning) must run in release.yml and/or audit.yml."""
        in_release = "gitleaks" in _read(RELEASE_YML)
        in_audit = "gitleaks" in _read(AUDIT_YML)
        assert in_release or in_audit, (
            "gitleaks (secret scanning) must appear in release.yml and/or audit.yml "
            "(fold #244 OSS-hygiene scanner suite)."
        )

    def test_gitleaks_scans_git_history(self):
        """B1: wherever gitleaks runs, it must use the 'gitleaks git' subcommand (scans the
        full commit history), NOT 'gitleaks dir' (working tree only). A secret committed
        then deleted lives only in history."""
        for path in (RELEASE_YML, AUDIT_YML):
            text = _read(path)
            if "gitleaks" in text:
                assert "gitleaks git" in text, (
                    f"{path.name} runs gitleaks but does not use the 'gitleaks git' subcommand. "
                    f"'gitleaks dir' scans only the working tree and misses secrets that were "
                    f"committed then deleted in a later commit (B1): {path}"
                )


# ---------------------------------------------------------------------------
# Council-ADV-4 — actionlint YAML-validity gate in ci.yml
# Spec ref: spec-addendum-post-test-r1.md item 3.
# Without actionlint, a structurally-broken-but-string-present workflow passes
# the presence tests yet fails at GitHub parse time = day-one red main.
# ---------------------------------------------------------------------------

class TestActionlintGate:
    """ci.yml must invoke actionlint to validate the workflow files."""

    def test_ci_yml_runs_actionlint(self):
        """Council-ADV-4: ci.yml must contain an 'actionlint' invocation."""
        text = _read(CI_YML)
        assert "actionlint" in text, (
            "ci.yml must invoke 'actionlint' to validate the Actions schema of all three "
            "workflow files (Council-ADV-4 / post-test addendum item 3). A structurally-broken "
            "workflow that merely contains the right strings would otherwise red-line main at "
            f"GitHub parse time: {CI_YML}"
        )
