"""Tests for scripts/verify-anytype-writes.sh — AC #7.

CI does NOT run the script (requires live Anytype desktop — maintainer-local).
These tests assert:
  1. The script exists at scripts/verify-anytype-writes.sh.
  2. The executable bit is set.
  3. The shebang line is #!/usr/bin/env bash or #!/bin/bash.
  4. bash -n parses the script cleanly (syntax check).
  5. The trap is installed BEFORE the probe creation (spec line 1384 — CSO R2 Advisory #2).
  6. Conditional-execution guards are present.
  7. Non-2xx DELETE diagnostics on stderr (>&2 in cleanup function).
  8. ANYTYPE_OBJECT_ID is NOT consumed (was removed as data-loss foot-gun — spec line 1429).
"""

import os
import pathlib
import re
import subprocess
import shutil
import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify-anytype-writes.sh"


class TestScriptExists:
    def test_script_file_exists(self):
        """scripts/verify-anytype-writes.sh must exist."""
        assert SCRIPT_PATH.exists(), (
            f"scripts/verify-anytype-writes.sh not found at {SCRIPT_PATH}. "
            "The script must be committed to the repo in v0.2.0."
        )

    def test_script_is_a_file(self):
        assert SCRIPT_PATH.is_file(), f"{SCRIPT_PATH} exists but is not a regular file"


class TestScriptExecutableBit:
    def test_script_has_executable_bit(self):
        """scripts/verify-anytype-writes.sh must have the executable bit set."""
        mode = SCRIPT_PATH.stat().st_mode
        assert mode & 0o111, (
            f"Script is not executable (mode={oct(mode)}). "
            "Run: chmod +x scripts/verify-anytype-writes.sh"
        )


class TestScriptShebang:
    def test_script_has_bash_shebang(self):
        """The script's first line must be #!/usr/bin/env bash or #!/bin/bash."""
        first_line = SCRIPT_PATH.read_text(encoding="utf-8").splitlines()[0]
        valid_shebangs = ("#!/usr/bin/env bash", "#!/bin/bash")
        assert first_line.strip() in valid_shebangs, (
            f"Script shebang must be one of {valid_shebangs}, got: {first_line!r}"
        )


class TestScriptSyntax:
    def test_bash_n_parses_clean(self):
        """bash -n scripts/verify-anytype-writes.sh must exit 0 (no syntax errors)."""
        bash = shutil.which("bash")
        if bash is None:
            pytest.skip("bash not found on PATH — cannot run syntax check")
        result = subprocess.run(
            [bash, "-n", str(SCRIPT_PATH)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"bash -n returned non-zero ({result.returncode}).\n"
            f"stderr: {result.stderr}"
        )

    @pytest.mark.skipif(
        shutil.which("shellcheck") is None,
        reason="shellcheck not installed — skipping shellcheck lint"
    )
    def test_shellcheck_clean(self):
        """shellcheck must report no errors on the script (if shellcheck is installed)."""
        result = subprocess.run(
            ["shellcheck", "--severity=error", str(SCRIPT_PATH)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"shellcheck reported errors:\n{result.stdout}\n{result.stderr}"
        )


class TestScriptTrapBeforeProbe:
    """CSO R2 Advisory #2: trap must be installed BEFORE the probe is created."""

    def _get_lines(self):
        return SCRIPT_PATH.read_text(encoding="utf-8").splitlines()

    def test_trap_cleanup_installed_before_probe_creation(self):
        """The first 'trap cleanup' call must precede the first curl POST to /types."""
        lines = self._get_lines()
        trap_line_no = None
        probe_create_line_no = None
        for i, line in enumerate(lines, start=1):
            if trap_line_no is None and re.search(r"\btrap\b.*\bcleanup\b", line):
                trap_line_no = i
            if probe_create_line_no is None and re.search(r"curl.*types", line) and re.search(r"-X\s+POST|POST", line):
                probe_create_line_no = i
        assert trap_line_no is not None, (
            "No 'trap cleanup' call found in the script"
        )
        assert probe_create_line_no is not None, (
            "No curl POST to /types (probe creation) found in the script"
        )
        assert trap_line_no < probe_create_line_no, (
            f"trap cleanup (line {trap_line_no}) must come BEFORE "
            f"the probe creation curl (line {probe_create_line_no})"
        )


class TestScriptConditionalGuards:
    """Conditional-execution guards must be present in the cleanup function."""

    def _content(self):
        return SCRIPT_PATH.read_text(encoding="utf-8")

    def test_probe_object_id_guard_present(self):
        """Script must guard probe object deletion with [[ -n "${PROBE_OBJECT_ID:-}" ]]."""
        content = self._content()
        assert 'PROBE_OBJECT_ID' in content and (
            re.search(r'\[\[\s*-n\s*.*PROBE_OBJECT_ID', content) or
            re.search(r'\$\{PROBE_OBJECT_ID:-\}', content)
        ), (
            "Script missing conditional guard for PROBE_OBJECT_ID. "
            "Expected: [[ -n \"${PROBE_OBJECT_ID:-}\" ]]"
        )

    def test_probe_type_key_guard_present(self):
        """Script must guard probe type deletion with [[ -n "${PROBE_TYPE_KEY:-}" ]]."""
        content = self._content()
        assert 'PROBE_TYPE_KEY' in content and (
            re.search(r'\[\[\s*-n\s*.*PROBE_TYPE_KEY', content) or
            re.search(r'\$\{PROBE_TYPE_KEY:-\}', content)
        ), (
            "Script missing conditional guard for PROBE_TYPE_KEY. "
            "Expected: [[ -n \"${PROBE_TYPE_KEY:-}\" ]]"
        )


class TestScriptStderrDiagnostics:
    """Non-2xx DELETE responses must produce stderr output (>&2) in cleanup."""

    def test_cleanup_emits_to_stderr(self):
        """The cleanup function must redirect diagnostic output to stderr (>&2)."""
        content = SCRIPT_PATH.read_text(encoding="utf-8")
        assert ">&2" in content, (
            "Script cleanup function must emit non-2xx DELETE diagnostics to stderr (>&2)"
        )


class TestScriptNoANYTYPE_OBJECT_ID:
    """ANYTYPE_OBJECT_ID must NOT be consumed by the script (data-loss foot-gun, spec line 1429)."""

    def test_anytype_object_id_not_referenced(self):
        """The script must NOT reference ANYTYPE_OBJECT_ID (removed as a foot-gun)."""
        content = SCRIPT_PATH.read_text(encoding="utf-8")
        # Strip comment lines before checking
        non_comment_lines = [
            line for line in content.splitlines()
            if not line.strip().startswith("#")
        ]
        non_comment_content = "\n".join(non_comment_lines)
        assert "ANYTYPE_OBJECT_ID" not in non_comment_content, (
            "Script must NOT reference ANYTYPE_OBJECT_ID — "
            "this variable was removed as a data-loss foot-gun (spec line 1429). "
            "The script creates its own probe object internally."
        )


class TestScriptEnvironmentVariables:
    """Required env vars must be consumed; optional vars must be documented."""

    def _content(self):
        return SCRIPT_PATH.read_text(encoding="utf-8")

    def test_anytype_api_key_consumed(self):
        """Script must reference ANYTYPE_API_KEY."""
        assert "ANYTYPE_API_KEY" in self._content()

    def test_anytype_space_id_consumed(self):
        """Script must reference ANYTYPE_SPACE_ID."""
        assert "ANYTYPE_SPACE_ID" in self._content()

    def test_anytype_api_url_or_default(self):
        """Script must reference ANYTYPE_API_URL (with default http://127.0.0.1:31012)."""
        content = self._content()
        assert "ANYTYPE_API_URL" in content

    def test_probe_type_key_variable_defined(self):
        """Script must define PROBE_TYPE_KEY variable (for the cleanup guard)."""
        content = self._content()
        assert "PROBE_TYPE_KEY" in content

    def test_probe_object_id_variable_defined(self):
        """Script must define PROBE_OBJECT_ID variable (for the cleanup guard)."""
        content = self._content()
        assert "PROBE_OBJECT_ID" in content
