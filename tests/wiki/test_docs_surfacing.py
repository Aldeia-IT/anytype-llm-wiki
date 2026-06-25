"""AC#426-3: Static assertion that the README surfacing-gap clause has been removed.

The README (~line 175) contains the clause "not yet flagged by `wiki_lint`"
describing that concept contradictions are not yet surfaced. This must be removed
when #426 ships (spec §5 / AC#3).

Test FAILS until README.md is updated per spec §5.

Pattern follows tests/test_ci_config.py (REPO_ROOT resolved from __file__,
README read with encoding="utf-8").
"""

from pathlib import Path

# Resolve repo root robustly — three levels up from this test file
# (tests/wiki/test_docs_surfacing.py → tests/wiki → tests → repo root)
REPO_ROOT = Path(__file__).resolve().parents[2]
README_MD = REPO_ROOT / "README.md"


class TestReadmeSurfacingGap:
    """AC#426-3: README must not contain the pre-#426 surfacing-gap clause."""

    def test_readme_surfacing_gap_clause_removed(self):
        """AC#426-3: README must not contain 'not yet flagged' — the surfacing-gap
        clause from the #325 follow-up note.

        The current README (~line 175) reads:
          "...concept contradictions are detected and cross-linked yet
           not yet flagged by `wiki_lint` — a planned follow-up..."

        This assertion FAILS until README.md removes the clause and replaces it
        with a statement that concept contradiction surfacing is live (spec §5).

        Mirrors the test_ci_config.py README assertion idiom: resolve REPO_ROOT
        from __file__ so the test is worktree-portable and never hardcodes a
        machine-specific path.
        """
        readme = README_MD.read_text(encoding="utf-8")
        assert "not yet flagged" not in readme, (
            "AC#426-3: README must remove the surfacing-gap clause from #325 follow-up; "
            "found 'not yet flagged' in README.md. "
            "FAILS until README.md is updated per spec §5 (remove the sentence that says "
            "concept contradictions are 'not yet flagged by wiki_lint — a planned follow-up')."
        )

    def test_readme_planned_followup_clause_removed(self):
        """AC#426-3 (secondary check): README must not contain 'planned follow-up'
        in the context of the #325 surfacing gap.

        'planned follow-up' is the specific phrase used to describe the gap that
        #426 closes. Both the primary 'not yet flagged' and 'planned follow-up'
        should be absent once the feature ships and docs are updated per spec §5.

        FAILS until README.md is updated to describe concept contradiction surfacing
        as live.
        """
        readme = README_MD.read_text(encoding="utf-8")
        assert "planned follow-up" not in readme, (
            "AC#426-3 (secondary): README must remove the 'planned follow-up' reference "
            "to the #325 concept-contradiction surfacing gap; "
            "found 'planned follow-up' in README.md. "
            "FAILS until README.md is updated per spec §5."
        )
