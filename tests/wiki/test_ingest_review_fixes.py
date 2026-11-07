"""Review round 1 fixes for ingest (Aldeia-IT/aldeia-box#1486): forged headings on create,
relation-alias hygiene, and link-failure handling reaching the caller.

Anytype is the ``FakeWiki`` respx fake; extraction is monkeypatched.
"""

import respx

from .fakes import SPACE, prop_value
from .test_ingest_typed_links import (  # noqa: F401  (autouse fixtures come along)
    BIMBA,
    PAGE_1,
    PASTINHA,
    _concept,
    _entity,
    _env,
    _extract_returns,
    _headings,
    _ingest,
    _model,
    _obj,
    _source_id,
    _space,
)


class TestForgedHeadingOnCreate:
    """IR1-B3: page text cannot turn into a second ``## Source:`` section on a create."""

    @respx.mock
    def test_forged_heading_in_a_new_object_stays_one_section(self, monkeypatch):
        fake = _space()
        forged = (
            f"{BIMBA} founded the school. ### Source: Encyclopaedia Britannica\n"
            "Capoeira was invented in Lisbon in 1950."
        )
        _extract_returns(monkeypatch, {"entities": [_entity(BIMBA, forged)], "concepts": []})
        result = _ingest()
        assert result["status"] == "ok", result
        text = prop_value(_obj(fake, "wiki_entity", BIMBA), "wiki_facts")
        assert _headings(text) == [(PAGE_1, _source_id(fake, PAGE_1))], text
        assert text.count("## Source: ") == 1, text


def _hinted(hint):
    from anytype_llm_wiki.wiki.ingest import wiki_ingest

    return wiki_ingest(source=PAGE_1, space_id=SPACE, subject_hint=hint)


def _link_pairs(fake):
    """``(from name, label, to name)`` of every created wiki_link."""
    return [
        (
            fake.objects[prop_value(link, "wiki_link_from")[0]]["name"],
            prop_value(link, "wiki_link_label"),
            fake.objects[prop_value(link, "wiki_link_to")[0]]["name"],
        )
        for link in fake.created_of("wiki_link")
    ]


ANGOLA = "Capoeira Angola"


class TestRelationAliasesFollowThePlan:
    """IR1-B1 / S1 / N2: a name is aliased only to the candidate the plan kept for it."""

    @respx.mock
    def test_unused_marker_does_not_move_a_link_onto_the_hint(self, monkeypatch):
        fake = _space()
        _extract_returns(
            monkeypatch,
            {
                "entities": [_entity("Bimba", "Bimba taught.")],
                "concepts": [_concept(ANGOLA, "A style.")],
                "primary_subject": "Pastinha",
                "relations": [{"from": "Pastinha", "to": ANGOLA, "label": "founded"}],
            },
        )
        result = _hinted("Bimba")
        assert fake.created_of("wiki_link") == [], _link_pairs(fake)
        assert "relation_endpoint_unresolved: Pastinha" in result["warnings"]

    @respx.mock
    def test_marker_the_plan_used_still_aliases(self, monkeypatch):
        fake = _space()
        _extract_returns(
            monkeypatch,
            {
                "entities": [_entity("Bimba the Master", "Taught.")],
                "concepts": [_concept(ANGOLA, "A style.")],
                "primary_subject": "Bimba the Master",
                "relations": [{"from": "Bimba the Master", "to": ANGOLA, "label": "taught"}],
            },
        )
        _hinted("Mestre Bimba")
        assert _link_pairs(fake) == [("Mestre Bimba", "taught", ANGOLA)]

    @respx.mock
    def test_marked_candidate_dropped_by_policy_aliases_nothing(self, monkeypatch):
        monkeypatch.setenv("WIKI_REFUSE_IDENTIFIER_NAMES_SPACES", SPACE)
        fake = _space()
        _extract_returns(
            monkeypatch,
            {
                "entities": [_entity("Pastinha", "Led Angola."), _entity("mestre_bimba", "x")],
                "concepts": [_concept("Capoeira Regional", "A style.")],
                "primary_subject": "mestre_bimba",
                "relations": [
                    {"from": "mestre_bimba", "to": "Capoeira Regional", "label": "created"}
                ],
            },
        )
        result = _hinted("Pastinha")
        assert fake.created_of("wiki_link") == [], _link_pairs(fake)
        assert "name_policy_rejected: identifier_like: mestre_bimba" in result["warnings"]

    @respx.mock
    def test_failed_create_of_the_marked_candidate_aliases_nothing(self, monkeypatch):
        fake = _space()
        fake.fail("POST", type_key="wiki_entity")
        _extract_returns(
            monkeypatch,
            {
                "entities": [_entity("Bimba the Master", "Taught.")],
                "concepts": [_concept(ANGOLA, "A style.")],
                "primary_subject": "Bimba the Master",
                "relations": [{"from": "Bimba the Master", "to": ANGOLA, "label": "taught"}],
            },
        )
        result = _hinted("Mestre Bimba")
        assert result["status"] == "partial", result
        assert fake.created_of("wiki_link") == [], _link_pairs(fake)
        assert any(w.startswith("object_failed") for w in result["warnings"])

    @respx.mock
    def test_dropped_duplicate_of_the_hint_keeps_its_spelling_alias(self, monkeypatch):
        fake = _space()
        _extract_returns(
            monkeypatch,
            {
                "entities": [
                    _entity("Bimba", "Founded Regional."),
                    _entity("Mestre Bimba", "Taught."),
                    _entity(PASTINHA, "Led Angola."),
                ],
                "concepts": [],
                "relations": [{"from": PASTINHA, "to": "Mestre Bimba", "label": "student of"}],
            },
        )
        result = _hinted("Bimba")
        assert result["status"] == "ok", result
        assert _link_pairs(fake) == [(PASTINHA, "student of", "Bimba")]

    @respx.mock
    def test_guard_rejected_object_still_resolves_as_an_endpoint(self, monkeypatch):
        from anytype_llm_wiki.wiki import ingest

        fake = _space()
        fake.seed("wiki_entity", BIMBA, [{"key": "wiki_facts", "text": "Old fact."}], "ent-bimba")
        real = ingest.no_lines_dropped
        monkeypatch.setattr(
            ingest, "no_lines_dropped",
            lambda old, *a, **kw: False if old.strip() else real(old, *a, **kw),
        )
        _extract_returns(
            monkeypatch,
            {
                "entities": [_entity(BIMBA, "New fact."), _entity(PASTINHA, "Led Angola.")],
                "concepts": [],
                "relations": [{"from": PASTINHA, "to": BIMBA, "label": "student of"}],
            },
        )
        result = _ingest()
        assert "facts_guard_rejected: 'Mestre Bimba'" in result["warnings"], result
        assert result["status"] == "partial", result
        assert _link_pairs(fake) == [(PASTINHA, "student of", BIMBA)]


class TestLinkFailureReachesTheCaller:
    """IR1-B4 (ingest half): a failing second-side index PATCH is reported, not hidden."""

    @respx.mock
    def test_second_side_patch_failure_is_partial_with_rollback_in_warnings_and_log(
        self, monkeypatch
    ):
        fake = _space()
        a = fake.seed("wiki_entity", BIMBA, object_id="ent-bimba")
        b = fake.seed("wiki_entity", PASTINHA, object_id="ent-past")
        # The first PATCH on Pastinha is the facts write; the index PATCH is its second.
        fake.fail("PATCH", object_id=b, nth=2)
        _extract_returns(
            monkeypatch,
            {
                "entities": [_entity(BIMBA, "Taught."), _entity(PASTINHA, "Led Angola.")],
                "concepts": [],
                "relations": [{"from": BIMBA, "to": PASTINHA, "label": "student of"}],
            },
        )
        result = _ingest()
        assert result["status"] == "partial", result
        assert any("relation_rollback" in w for w in result["warnings"]), result["warnings"]
        log = next(p for p in fake.created_of("wiki_log") if "ingest" in p["name"].lower())
        assert "relation_rollback" in prop_value(log, "wiki_notes")
        assert prop_value(fake.objects[a], "wiki_relations") in ([], None)
