"""tests/wiki/test_docs_disclosure.py — README docs-presence assertion (addendum item 5a).

Asserts that the operator-facing detection-scope limitation copy required by addendum
item 3 (CPO-A-1 / Client-ADV-1) is present in README.md.

As of the test-writer phase, this copy is an impl-phase deliverable (§8 step 11).
These tests FAIL now (the README has not yet been updated) and will pass after impl.

Design rationale (addendum item 5a):
- AC-3 asserts the in-product "PASSIVE" caveat is removed from lint findings.
- Nothing currently asserts the *replacement* operator disclosure lands in README.
- This file closes that gap so the disclosure cannot silently regress.
- ONE cohesive assertion per concept (not fragmented across many substring checks —
  a prior ticket failed review for 4 separate substring checks). Each assertion
  tests one coherent operator-facing disclosure concept.

Note on the existing "passive until v0.6.0" section in README:
The README currently (pre-impl) contains a section:
  '### `contradiction_unresolved` is passive until v0.6.0'
This must be REPLACED by post-v0.6.0 disclosure copy that:
(a) Removes the "passive" framing (the check is now active)
(b) Adds the linked-entities-only scope limitation
(c) Adds the entity-only scope limitation
The tests below assert on the NEW copy that must be present after impl.
They are designed to fail against the current (pre-impl) README.
"""

import os
import pathlib

# README.md is at the repo root, two levels above tests/wiki/
_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
_README_PATH = _REPO_ROOT / "README.md"


def _readme_text() -> str:
    """Read README.md content. Asserts the file exists."""
    assert _README_PATH.exists(), (
        f"README.md not found at {_README_PATH} — cannot run docs disclosure tests"
    )
    return _README_PATH.read_text(encoding="utf-8")


class TestReadmeDetectionScopeDisclosure:
    """README must disclose the contradiction-detection scope limitations.

    Originally (v0.6.0 / #287) this required an "entity-only" scope disclosure.
    #325 extends detection to wiki_concept updates, so that requirement is
    superseded:
    - Linked-peers-only limitation: detection covers only peers already linked
      via the relation property (DI-3: unlinked contradictions not caught).
    - Surfacing gap (#325): concept contradictions are detected and cross-linked
      via wiki_contradictions but are NOT yet flagged by wiki_lint (follow-up).
    """

    def test_readme_discloses_linked_entities_only_scope(self):
        """Addendum item 5a / CPO-A-1: README must state that contradiction detection
        covers only entities already linked via wiki_relations (linked-peers-only scope).

        The CURRENT README (pre-impl) says the check is "passive until v0.6.0".
        The POST-IMPL README must say the check is active BUT scoped to linked
        entities only. The specific disclosure the addendum requires (item 3):
        "v0.6.0 detects contradictions between linked entities only; contradictions
        between unlinked entities are not yet caught".

        ONE cohesive assertion: README contains a phrase combining "linked entities"
        with the concept that detection is limited to them — specifically in the
        context of contradiction detection, not in other unrelated sections.
        The gate looks for the new v0.6.0 disclosure copy as a unit.

        FAILS now: the current README passive section does NOT contain this copy.
        It will pass after impl replaces "passive until v0.6.0" with the new
        scoped-but-active disclosure.
        """
        readme = _readme_text().lower()

        # ONE cohesive gate: "linked entities" must appear in conjunction with
        # contradiction detection context. The phrase "linked entities only" /
        # "between linked entities" is the addendum-mandated operator language.
        # The current README uses "interlinked" in a different context and does
        # NOT contain "linked entities" as a disclosure phrase.
        assert "linked entities" in readme and "contradiction" in readme, (
            "README.md must contain 'linked entities' in the contradiction detection "
            "section (addendum item 3 / CPO-A-1): v0.6.0 detects contradictions "
            "between linked entities only. The current README uses 'interlinked' "
            "in a different context and does NOT contain 'linked entities' as a "
            "disclosure phrase. Expected: 'v0.6.0 detects contradictions between "
            "linked entities only; contradictions between unlinked entities are not "
            "yet caught'. This is a gated impl-phase deliverable (§8 step 11)."
        )

    def test_readme_discloses_concept_lint_surfacing_gap(self):
        """#325 (supersedes the v0.6.0 entity-only disclosure): detection now fires
        for BOTH entity and concept updates, so the README must NO LONGER claim
        detection is entity-only. Instead it must disclose the remaining surfacing
        gap — concept contradictions are detected and cross-linked but not yet
        flagged by wiki_lint (follow-up).

        This test replaces the former test_readme_discloses_entity_only_scope: #325
        ships the concept detection extension, making the "entity-only" scope claim
        false. The operator-facing disclosure required now is the lint-surfacing
        follow-up, not an entity-only scope.
        """
        readme = _readme_text().lower()

        # The stale entity-only scope claim must be gone (detection now covers concepts).
        assert "entity-only" not in readme, (
            "README.md must NOT claim contradiction detection is 'entity-only' — #325 "
            "extends detection to wiki_concept updates. Replace the stale scope claim "
            "with the lint-surfacing follow-up disclosure."
        )

        # The surfacing gap (concept contradictions detected but not yet lint-flagged)
        # must be disclosed so no reader infers a closed integrity loop.
        surfacing_gap_disclosed = (
            "concept" in readme
            and "wiki_lint" in readme
            and "follow-up" in readme
            and "contradiction" in readme
        )
        assert surfacing_gap_disclosed, (
            "README.md must disclose the #325 surfacing gap (addendum item 3 / "
            "CA-CPO-ADV-3): concept contradictions are detected and cross-linked via "
            "wiki_contradictions but are NOT yet flagged by wiki_lint (a planned "
            "follow-up), so no reader infers a closed integrity loop. Expected the "
            "contradiction-detection section to mention 'concept', 'wiki_lint', and "
            "'follow-up'."
        )

    def test_readme_passive_section_replaced(self):
        """Addendum item 5a / sanity: after v0.6.0, the 'passive until v0.6.0' section
        heading should be GONE — it must be replaced by active-but-scoped disclosure copy.

        The current README has:
          '### `contradiction_unresolved` is passive until v0.6.0'
        After impl, this section must be replaced. The PASSIVE framing contradicts
        the activated lint check.

        FAILS now in inverse: the current README DOES have the passive section.
        Will pass after impl removes it.
        """
        readme_text = _readme_text()
        # The old passive heading should be removed by impl
        assert "passive until v0.6.0" not in readme_text, (
            "README.md still contains the 'passive until v0.6.0' section heading — "
            "this must be replaced by the v0.6.0 active-but-scoped disclosure copy "
            "(addendum item 3 / §3.7 change 4). The disclosure must state that the "
            "check is now active AND explain the scope limitations (linked-entities-only, "
            "entity-only). This is a gated impl-phase deliverable (§8 step 11)."
        )
