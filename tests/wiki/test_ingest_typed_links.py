"""wiki_ingest end to end: typed links and per-source facts (Aldeia-IT/aldeia-box#1486).

Rows T2, T5 (ingest half), T8 (ingest half), T9 (ingest half), T14, T15 (second
half), T16 and AC1 end to end. Anytype is the ``FakeWiki`` respx fake; extraction
and the contradiction model call are monkeypatched.
"""

import re
import socket

import pytest
import respx

from .fakes import ANYTYPE_BASE, SPACE, FakeWiki, prop_value

PAGE_1 = "https://lalaue.example/page-one"
PAGE_2 = "https://lalaue.example/page-two"
BIMBA = "Mestre Bimba"
PASTINHA = "Mestre Pastinha"
REGIONAL = "Capoeira Regional"
SRC_OLD = "src-old"
HEADING = re.compile(r"^## Source: (?P<label>.*?)(?: \(id:(?P<id>[^)]*)\))?$")
LEGACY_HEADING = "## Source: unattributed (before per-source facts)"


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("ANYTYPE_API_KEY", "test-key")
    monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
    monkeypatch.setenv("ANYTYPE_API_VERSION", "2025-11-08")
    monkeypatch.setenv("WIKI_AUTO_REINDEX", "false")
    monkeypatch.setenv("WIKI_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.delenv("WIKI_EXTRACT_ENDPOINT", raising=False)
    from anytype_llm_wiki.wiki import fetch as fetch_mod

    monkeypatch.setattr(
        fetch_mod.socket,
        "getaddrinfo",
        lambda host, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )


@pytest.fixture(autouse=True)
def _model(monkeypatch):
    """The contradiction model call answers "no contradictions" in both shapes."""
    from anytype_llm_wiki.wiki import ingest

    monkeypatch.setattr(
        ingest,
        "_call_ollama_prompt",
        lambda base, prompt: ({"results": [], "contradictions": []}, None),
    )


def _space(**kw) -> FakeWiki:
    """A bootstrapped space served from the fake's object store."""
    from anytype_llm_wiki.wiki.types_schema import WIKI_SCHEMA_VERSION

    kw.setdefault("search_with_properties", True)
    fake = FakeWiki(serve_objects=True, **kw)
    fake.install()
    fake.seed(
        "wiki_log",
        "bootstrap 2026-06-04",
        [{"key": "wiki_schema_version", "text": WIKI_SCHEMA_VERSION}],
        "log-schema-001",
    )
    return fake


def _extract_returns(monkeypatch, *results: dict) -> None:
    """Each extract() call returns the next result; the last one repeats."""
    from anytype_llm_wiki.wiki import ingest

    queue = list(results)

    def fake_extract(**kw):
        return queue.pop(0) if len(queue) > 1 else queue[0]

    monkeypatch.setattr(ingest, "extract", fake_extract)


def _ingest(source=PAGE_1):
    from anytype_llm_wiki.wiki.ingest import wiki_ingest

    return wiki_ingest(source=source, space_id=SPACE)


def _source_id(fake: FakeWiki, name: str) -> str:
    return next(
        o["id"]
        for o in fake.objects.values()
        if o["type"]["key"] == "wiki_source" and o["name"] == name
    )


def _obj(fake: FakeWiki, type_key: str, name: str) -> dict:
    return next(
        o for o in fake.objects.values() if o["type"]["key"] == type_key and o["name"] == name
    )


def _headings(text: str) -> list[tuple[str, str | None]]:
    """``(label, id)`` of every ``## Source:`` heading, in order."""
    out = []
    for line in text.split("\n"):
        if line.startswith("## Source: "):
            m = HEADING.match(line)
            out.append((m["label"], m["id"]))
    return out


def _entity(name, desc):
    return {"name": name, "description": desc}


def _concept(name, definition):
    return {"name": name, "definition": definition}


def _link_objects(fake: FakeWiki) -> list[dict]:
    return [o for o in fake.objects.values() if o["type"]["key"] == "wiki_link"]


def _index_patches(fake: FakeWiki) -> list[tuple[str, dict]]:
    """PATCHes (and creates, as a pseudo-PATCH) that carry an untyped index key."""
    keys = {"wiki_relations", "wiki_related"}
    return [
        (oid, p)
        for oid, p in fake.patch_attempts
        if any(isinstance(q, dict) and q.get("key") in keys for q in p.get("properties") or [])
    ]


HEADINGS_ONLY_PAGE = (
    "# Capoeira Regional notes\n\n"
    + "Intro paragraph about the notes, long enough to count as usable content. " * 4
    + "\n\n## Overview\n\n"
    + "The overview section explains the style in some detail for the reader. " * 4
    + "\n\n## Migration Path\n\n"
    + "The migration section explains how the style travelled over the years. " * 4
    + "\n\n## Open Questions\n\n"
    + "The questions section lists what is still unknown about the history. " * 4
    + "\n"
)


class TestHeadingsOnlyExtraction:
    """T2 / AC1: no model relations -> no link and no untyped index write."""

    @respx.mock
    def test_headings_only_page_writes_no_link_and_no_index_patch(self, monkeypatch):
        fake = _space(page_body=HEADINGS_ONLY_PAGE)
        _extract_returns(monkeypatch, {"entities": [], "concepts": []})
        result = _ingest()
        assert result["status"] == "ok", result
        assert len(result["objects_created"]) >= 2, "heading objects were written"
        assert fake.created_of("wiki_link") == []
        assert _index_patches(fake) == []
        assert not any(
            prop_value(o, "wiki_relations") or prop_value(o, "wiki_related")
            for o in fake.objects.values()
        )
        assert result["relations_created"] == 0

    @respx.mock
    def test_extraction_without_relations_key_writes_no_link(self, monkeypatch):
        fake = _space()
        _extract_returns(
            monkeypatch,
            {
                "entities": [_entity(BIMBA, "Founded Regional."), _entity(PASTINHA, "Led Angola.")],
                "concepts": [_concept(REGIONAL, "A style.")],
            },
        )
        result = _ingest()
        assert result["status"] == "ok", result
        assert len(result["objects_created"]) == 3
        assert fake.created_of("wiki_link") == []
        assert _index_patches(fake) == []


STATED_RELATION = {
    "entities": [
        _entity(BIMBA, "Bimba was a student of Pastinha."),
        _entity(PASTINHA, "Pastinha led Capoeira Angola."),
        _entity("Mestre Moraes", "Moraes taught in Salvador."),
    ],
    "concepts": [],
    "relations": [{"from": BIMBA, "to": PASTINHA, "label": "Student Of"}],
}


class TestStatedRelationEndToEnd:
    """AC1: "A student of B" gives one typed link A -> B sourced to the page, no chain."""


    @respx.mock
    def test_one_typed_link_sourced_to_the_page_and_no_chain(self, monkeypatch):
        fake = _space()
        _extract_returns(monkeypatch, STATED_RELATION)
        result = _ingest()
        assert result["status"] == "ok", result
        a, b = _obj(fake, "wiki_entity", BIMBA), _obj(fake, "wiki_entity", PASTINHA)
        c = _obj(fake, "wiki_entity", "Mestre Moraes")
        links = fake.created_of("wiki_link")
        assert len(links) == 1, links
        link = links[0]
        assert prop_value(link, "wiki_link_from") == [a["id"]]
        assert prop_value(link, "wiki_link_to") == [b["id"]]
        assert prop_value(link, "wiki_link_label") == "student of"
        assert prop_value(link, "wiki_link_sources") == [_source_id(fake, PAGE_1)]
        assert result["relations_created"] == 1
        assert prop_value(fake.objects[a["id"]], "wiki_relations") == [b["id"]]
        assert prop_value(fake.objects[b["id"]], "wiki_relations") == [a["id"]]
        assert not prop_value(fake.objects[c["id"]], "wiki_relations"), "no chain to the third"

    @respx.mock
    def test_second_page_stating_it_again_joins_the_link(self, monkeypatch):
        fake = _space()
        _extract_returns(monkeypatch, STATED_RELATION)
        _ingest(PAGE_1)
        result = _ingest(PAGE_2)
        assert result["status"] == "ok", result
        links = fake.created_of("wiki_link")
        stored = _link_objects(fake)
        assert len(links) == 1 and len(stored) == 1, (links, stored)
        assert prop_value(stored[0], "wiki_link_sources") == [
            _source_id(fake, PAGE_1),
            _source_id(fake, PAGE_2),
        ]
        assert result["relations_created"] == 0
        assert result.get("relations_sourced") == 1
        assert links[0]["name"] == stored[0]["name"]


class TestEarlierIndexIdsSurvive:
    """T5 (ingest half) / AC5: ids already in the untyped index are kept."""

    @respx.mock
    def test_existing_relation_ids_stay_beside_the_new_one(self, monkeypatch):
        fake = _space()
        old_a = fake.seed("wiki_entity", "Old peer A", object_id="old-a")
        old_b = fake.seed("wiki_entity", "Old peer B", object_id="old-b")
        a = fake.seed(
            "wiki_entity", BIMBA, [{"key": "wiki_relations", "objects": [old_a]}], "ent-bimba"
        )
        b = fake.seed(
            "wiki_entity", PASTINHA, [{"key": "wiki_relations", "objects": [old_b]}], "ent-past"
        )
        _extract_returns(
            monkeypatch,
            {
                "entities": [_entity(BIMBA, "Taught Moraes."), _entity(PASTINHA, "Led Angola.")],
                "concepts": [],
                "relations": [{"from": BIMBA, "to": PASTINHA, "label": "student of"}],
            },
        )
        result = _ingest()
        assert result["status"] == "ok", result
        assert len(fake.created_of("wiki_link")) == 1
        assert prop_value(fake.objects[a], "wiki_relations") == [old_a, b]
        assert prop_value(fake.objects[b], "wiki_relations") == [old_b, a]


BIMBA_PAGE_ONE = {
    "entities": [_entity(BIMBA, "Bimba founded Regional. He taught Pastinha.")],
    "concepts": [_concept(REGIONAL, "A capoeira style.")],
}


BIMBA_PAGE_TWO = {
    "entities": [_entity(BIMBA, "Bimba opened an academy.")],
    "concepts": [_concept(REGIONAL, "It was created in the 1930s.")],
}


class TestTwoPagesOneObject:
    """T8 (ingest half) / AC2: two pages give two attributed sections and both sources."""


    @respx.mock
    def test_entity_gets_two_sections_and_both_sources(self, monkeypatch):
        fake = _space()
        _extract_returns(monkeypatch, BIMBA_PAGE_ONE, BIMBA_PAGE_TWO)
        assert _ingest(PAGE_1)["status"] == "ok"
        assert _ingest(PAGE_2)["status"] == "ok"
        s1, s2 = _source_id(fake, PAGE_1), _source_id(fake, PAGE_2)
        bimba = _obj(fake, "wiki_entity", BIMBA)
        text = prop_value(bimba, "wiki_facts")
        assert [i for _, i in _headings(text)] == [s1, s2]
        assert [lab for lab, _ in _headings(text)] == [
            "https://lalaue.example/page-one",
            "https://lalaue.example/page-two",
        ]
        first, second = text.split("## Source: ")[1:]
        assert "Bimba founded Regional. He taught Pastinha." in first
        assert "Bimba opened an academy." in second and "academy" not in first
        assert prop_value(bimba, "wiki_sources") == [s1, s2]

    @respx.mock
    def test_concept_gets_two_sections_and_both_sources(self, monkeypatch):
        fake = _space()
        _extract_returns(monkeypatch, BIMBA_PAGE_ONE, BIMBA_PAGE_TWO)
        _ingest(PAGE_1)
        _ingest(PAGE_2)
        s1, s2 = _source_id(fake, PAGE_1), _source_id(fake, PAGE_2)
        concept = _obj(fake, "wiki_concept", REGIONAL)
        text = prop_value(concept, "wiki_definition")
        assert [i for _, i in _headings(text)] == [s1, s2]
        assert "A capoeira style." in text and "It was created in the 1930s." in text
        assert prop_value(concept, "wiki_sources") == [s1, s2]

    @respx.mock
    def test_create_writes_one_line_per_paragraph(self, monkeypatch):
        fake = _space()
        _extract_returns(
            monkeypatch,
            {
                "entities": [
                    _entity(
                        "Mestre Moraes",
                        "Moraes was a mestre. He lived in Salvador.\n\nHe taught Bimba.",
                    )
                ],
                "concepts": [],
            },
        )
        assert _ingest()["status"] == "ok"
        moraes = _obj(fake, "wiki_entity", "Mestre Moraes")
        text = prop_value(moraes, "wiki_facts")
        sid = _source_id(fake, PAGE_1)
        assert _headings(text) == [("https://lalaue.example/page-one", sid)]
        body = [line for line in text.split("\n")[1:] if line.strip()]
        assert body == ["Moraes was a mestre. He lived in Salvador.", "He taught Bimba."]
        assert prop_value(moraes, "wiki_sources") == [sid]


class TestDuplicatesAndLegacy:
    """T9 (ingest half) / AC2, AC9: duplicates are tagged, legacy text comes first."""

    @respx.mock
    def test_legacy_text_stays_first_and_a_duplicate_is_tagged_not_repeated(self, monkeypatch):
        fake = _space()
        legacy = "Bimba founded Regional."
        ent = fake.seed("wiki_entity", BIMBA, [{"key": "wiki_facts", "text": legacy}], "ent-b")
        _extract_returns(
            monkeypatch,
            {
                "entities": [_entity(BIMBA, "Bimba founded Regional. He taught Pastinha.")],
                "concepts": [],
            },
        )
        assert _ingest()["status"] == "ok"
        text = prop_value(fake.objects[ent], "wiki_facts")
        sid = _source_id(fake, PAGE_1)
        assert text.startswith(LEGACY_HEADING), text
        assert text.index("Bimba founded Regional.") < text.index("## Source: https://")
        assert text.count("Bimba founded Regional.") == 1, "the duplicate is not repeated"
        assert re.search(r"Bimba founded Regional\. \[also: [^\]]*page-one[^\]]*\]", text), text
        new_section = text.split("## Source: https://")[1]
        assert "He taught Pastinha." in new_section
        assert _headings(text)[-1][1] == sid
        assert prop_value(fake.objects[ent], "wiki_sources") == [sid]

    @respx.mock
    def test_page_of_only_duplicates_adds_no_section_but_both_sources(self, monkeypatch):
        fake = _space()
        fake.seed("wiki_source", "page zero", None, SRC_OLD)
        old = f"## Source: https://lalaue.example/page-zero (id:{SRC_OLD})\nBimba founded Regional."
        ent = fake.seed(
            "wiki_entity",
            BIMBA,
            [
                {"key": "wiki_facts", "text": old},
                {"key": "wiki_sources", "objects": [SRC_OLD]},
            ],
            "ent-b",
        )
        _extract_returns(
            monkeypatch,
            {"entities": [_entity(BIMBA, "Bimba founded Regional.")], "concepts": []},
        )
        assert _ingest()["status"] == "ok"
        text = prop_value(fake.objects[ent], "wiki_facts")
        assert _headings(text) == [("https://lalaue.example/page-zero", SRC_OLD)], text
        assert text.count("Bimba founded Regional.") == 1
        assert re.search(r"\[also: [^\]]*page-one[^\]]*\]", text), text
        assert prop_value(fake.objects[ent], "wiki_sources") == [
            SRC_OLD,
            _source_id(fake, PAGE_1),
        ]


class TestTwoCandidatesOneObject:
    """T14 / AC2: two candidates resolving to one object keep both units, from a fresh read."""

    @respx.mock
    def test_both_candidates_units_survive_in_one_section(self, monkeypatch):
        # "Mestre Pastinhá" is fuzzily the stored "Mestre Pastinha" (ratio > 0.92); search
        # hits carry no properties, so the stored text can only come from a fresh read.
        fake = _space(
            search_with_properties=False,
            search_aliases={"mestre pastinhá": "mestre pastinha"},
        )
        old = "Pastinha ran an academy."
        ent = fake.seed("wiki_entity", PASTINHA, [{"key": "wiki_facts", "text": old}], "ent-p")
        _extract_returns(
            monkeypatch,
            {
                "entities": [
                    _entity(PASTINHA, "Pastinha led Capoeira Angola."),
                    _entity("Mestre Pastinhá", "Pastinha painted in Salvador."),
                ],
                "concepts": [],
            },
        )
        assert _ingest()["status"] == "ok"
        text = prop_value(fake.objects[ent], "wiki_facts")
        sid = _source_id(fake, PAGE_1)
        assert old in text, "the stored text was read, not overwritten"
        assert "Pastinha led Capoeira Angola." in text
        assert "Pastinha painted in Salvador." in text
        assert [i for _, i in _headings(text) if i == sid] == [sid], "one section for the page"
        assert ("GET", f"/v1/spaces/{SPACE}/objects/{ent}") in fake.requests
        assert prop_value(fake.objects[ent], "wiki_sources") == [sid]


class TestResolveBesideLinks:
    """T15 (second half) / AC1: an entity is still found beside 50 link objects."""

    @respx.mock
    def test_entity_is_updated_not_recreated_beside_fifty_links(self, monkeypatch):
        fake = _space()
        others = [f"Aluno {i:02d}" for i in range(50)]
        _extract_returns(
            monkeypatch,
            {
                "entities": [_entity(BIMBA, "Bimba taught many.")]
                + [_entity(n, f"{n} learned from Bimba.") for n in others],
                "concepts": [],
                "relations": [{"from": n, "to": BIMBA, "label": "student of"} for n in others],
            },
            {"entities": [_entity(BIMBA, "Bimba opened an academy.")], "concepts": []},
        )
        first = _ingest(PAGE_1)
        assert first["status"] == "ok", first
        assert len(fake.created_of("wiki_link")) == 50
        entities_before = len(fake.created_of("wiki_entity"))
        second = _ingest(PAGE_2)
        assert second["status"] == "ok", second
        assert [o["title"] for o in second["objects_updated"]] == [BIMBA]
        assert second["objects_created"] == []
        assert len(fake.created_of("wiki_entity")) == entities_before
        assert len(fake.created_of("wiki_link")) == 50


class TestSamePageTwice:
    """T16 / AC12: re-ingesting a page writes nothing to entities, concepts or links."""

    @respx.mock
    def test_second_run_writes_no_entity_concept_or_link(self, monkeypatch):
        fake = _space()
        _extract_returns(
            monkeypatch,
            {
                "entities": [
                    _entity(BIMBA, "Bimba founded Regional. He taught Pastinha."),
                    _entity(PASTINHA, "Pastinha led Capoeira Angola."),
                ],
                "concepts": [_concept(REGIONAL, "A capoeira style.")],
                "relations": [
                    {"from": BIMBA, "to": PASTINHA, "label": "student of"},
                    {"from": BIMBA, "to": REGIONAL, "label": "founded"},
                ],
            },
        )
        first = _ingest()
        assert first["status"] == "ok", first
        assert len(fake.created_of("wiki_link")) == 2
        kept = {
            oid: (prop_value(o, "wiki_facts"), prop_value(o, "wiki_definition"))
            for oid, o in fake.objects.items()
        }
        created_before, attempts_before = len(fake.created), len(fake.patch_attempts)

        second = _ingest()
        assert second["status"] == "ok", second
        new_created = fake.created[created_before:]
        assert [p["type_key"] for p in new_created if p["type_key"] != "wiki_log"] == []
        content_ids = {
            o["id"]
            for o in fake.objects.values()
            if o["type"]["key"] in ("wiki_entity", "wiki_concept", "wiki_link")
        }
        assert [oid for oid, _ in fake.patch_attempts[attempts_before:] if oid in content_ids] == []
        assert second["relations_created"] == 0
        assert len(_link_objects(fake)) == 2
        for oid, texts in kept.items():
            assert (
                prop_value(fake.objects[oid], "wiki_facts"),
                prop_value(fake.objects[oid], "wiki_definition"),
            ) == texts
