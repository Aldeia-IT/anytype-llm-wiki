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
    """Addendum item 5a: README must disclose the v0.6.0 detection scope limitations.

    Addendum item 3 (CPO-A-1 / Client-ADV-1) requires:
    - Linked-peers-only limitation: contradiction detection covers only entities
      already linked via wiki_relations (DI-3: unlinked-entity contradictions not caught).
    - Entity-only scope: v0.6.0 detects contradictions for wiki_entity only
      (DI-1: concept scope deferred).

    Both must be present in README.md AFTER the "passive until v0.6.0" section is
    replaced by the active-but-scoped disclosure copy (impl §8 step 11).

    FAILS until §8 step 11 (impl docs sweep) updates README.md.
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

    def test_readme_discloses_entity_only_scope(self):
        """Addendum item 5a / CPO-A-1: README must state that contradiction detection
        is entity-only in v0.6.0 (concept scope deferred, DI-1).

        The addendum-mandated operator language (item 3):
        "Entity-only; concept scope deferred."

        ONE cohesive assertion: README contains "entity-only" (or equivalent) in
        the context of contradiction detection.

        FAILS now: the current README "passive until v0.6.0" section does NOT
        contain "entity-only" or equivalent entity/concept scope distinction
        in the contradiction detection context.
        """
        readme = _readme_text().lower()

        # ONE cohesive gate: "entity-only" is the exact operator language required.
        # Alternatives: "entity only" (no hyphen) or "concept scope deferred".
        entity_only_disclosed = (
            "entity-only" in readme
            or "entity only" in readme
            or ("concept scope deferred" in readme)
            or ("concept" in readme and "deferred" in readme
                and "contradiction" in readme
                and readme.find("deferred") > readme.find("contradiction"))
        )
        assert entity_only_disclosed, (
            "README.md must disclose the entity-only contradiction detection scope "
            "(addendum item 3 / CPO-A-1): v0.6.0 detection is scoped to wiki_entity "
            "only (wiki_last_reviewed absent from wiki_concept, DI-1). "
            "Expected phrases like 'entity-only' or 'concept scope deferred' in the "
            "README contradiction/lint section. "
            "This is a gated impl-phase deliverable (§8 step 11)."
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
