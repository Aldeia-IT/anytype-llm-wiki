"""wiki_remember with per-source facts and typed links (Aldeia-IT/aldeia-box#1486).

T12 (a consolidation rewrite that drops a unit or forges a section, tag, unit or citation
falls back to the deterministic merge with ``consolidation_rewrite_rejected``; a supersede
keeps the old line, tagged), T13 (hint links become a sourced ``related`` ``wiki_link``)
and T25 (the same remember twice PATCHes only ``wiki_sources`` on call 2). AC8, AC12, D5.
Anytype is the ``FakeWiki`` respx fake; ``extract`` and ``consolidate`` are monkeypatched
the way ``test_remember.py`` does; no live space and no model call.
"""

import pytest
import respx

from anytype_llm_wiki.wiki.types_schema import WIKI_SCHEMA_VERSION

from .fakes import ANYTYPE_BASE, FakeWiki, prop_value

SPACE = "space-remember-test-001"
ENT = "ent-bimba"
SRC_OLD = "src-old"
LABEL = "note two"
OLD_UNIT_1 = "Bimba founded Regional. [p. 12]"
OLD_UNIT_2 = "He taught Pastinha."
NEW_UNIT = "Bimba opened an academy."
OLD_FACTS = f"## Source: page one (id:{SRC_OLD})\n{OLD_UNIT_1}\n{OLD_UNIT_2}"
SUBJECT = {"name": "Mestre Bimba", "kind": "entity", "facts": NEW_UNIT}
CONCEPT = {"name": "Capoeira Regional", "kind": "concept", "facts": "A capoeira style."}
KNOWLEDGE = "Mestre Bimba founded Capoeira Regional in Salvador."


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("ANYTYPE_API_KEY", "test-key")
    monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
    monkeypatch.setenv("ANYTYPE_API_VERSION", "2025-11-08")
    monkeypatch.setenv("WIKI_AUTO_REINDEX", "false")
    monkeypatch.setenv("WIKI_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.delenv("WIKI_EXTRACT_ENDPOINT", raising=False)
    monkeypatch.setenv("WIKI_EXTRACT_MODEL", "qwen2.5:7b")
    (tmp_path / "patch-decision.md").write_text("patch: true\ndecision: apply\n")
    monkeypatch.setenv("ALDEIA_DIR", str(tmp_path))


def _space() -> FakeWiki:
    """A bootstrapped space served from the fake's object store."""
    fake = FakeWiki(serve_objects=True, search_with_properties=True)
    fake.install()
    fake.seed(
        "wiki_log",
        "bootstrap 2026-06-04",
        [{"key": "wiki_schema_version", "text": WIKI_SCHEMA_VERSION}],
        "log-schema-001",
    )
    return fake


def _seed_bimba(fake: FakeWiki, facts: str = OLD_FACTS, sources=(SRC_OLD,)) -> None:
    fake.seed("wiki_source", "page one", None, SRC_OLD)
    fake.seed(
        "wiki_entity",
        "Mestre Bimba",
        [
            {"key": "wiki_facts", "text": facts},
            {"key": "wiki_sources", "objects": list(sources)},
        ],
        ENT,
    )


def _patch_calls(monkeypatch, subjects, consolidate=None):
    from anytype_llm_wiki.wiki import remember

    canned = {
        "entities": [s for s in subjects if s["kind"] == "entity"],
        "concepts": [s for s in subjects if s["kind"] == "concept"],
    }
    monkeypatch.setattr(remember, "extract", lambda **kw: canned)
    seen: list[dict] = []

    def fake_consolidate(**kw):
        seen.append(kw)
        if consolidate is None:
            return {
                "consolidated_text": kw["existing_text"],
                "changed": False,
                "fact_actions": [],
                "conflicts": [],
            }
        return consolidate(kw)

    monkeypatch.setattr(remember, "consolidate", fake_consolidate)
    return seen


def _remember(knowledge="Bimba opened an academy.", **kw):
    from anytype_llm_wiki.wiki.remember import wiki_remember

    kw.setdefault("source", LABEL)
    return wiki_remember(space_id=SPACE, knowledge=knowledge, **kw)


def _source_id(fake: FakeWiki, name: str = LABEL) -> str:
    """The id of the Source named ``name``; a placeholder while none exists yet."""
    return next(
        (
            o["id"]
            for o in fake.objects.values()
            if o["type"]["key"] == "wiki_source" and o["name"] == name
        ),
        "source-not-created-yet",
    )


def _heading(fake: FakeWiki) -> str:
    return f"## Source: {LABEL} (id:{_source_id(fake)})"


def _facts_lines(fake: FakeWiki, object_id: str = ENT) -> list[str]:
    return (prop_value(fake.objects[object_id], "wiki_facts") or "").splitlines()


def _with_writer_section(fake: FakeWiki, text: str) -> str:
    heading = _heading(fake)
    if heading in text.splitlines():
        return text
    return f"{text}\n{heading}\n{NEW_UNIT}"


def _rewrite(fake: FakeWiki, mutate):
    """A consolidate mock returning the model's text after ``mutate`` (changed=True)."""

    def consolidate(kw):
        text = mutate(_with_writer_section(fake, kw["existing_text"]))
        return {"consolidated_text": text, "changed": True, "fact_actions": [], "conflicts": []}

    return consolidate


def _assert_deterministic_merge(fake, result):
    lines = _facts_lines(fake)
    assert OLD_UNIT_1 in lines and OLD_UNIT_2 in lines, lines
    assert lines.count(_heading(fake)) == 1, lines
    assert lines.count(NEW_UNIT) == 1, lines
    assert "consolidation_rewrite_rejected" in result["warnings"], result["warnings"]


class TestRewriteGuard:
    """T12 / AC8: only a faithful rewrite is written; every forgery falls back to the merge."""

    @respx.mock
    def test_faithful_rewrite_is_written_as_is(self, monkeypatch):
        fake = _space()
        _seed_bimba(fake)
        tag = f"{OLD_UNIT_2} [also: {LABEL}]"
        _patch_calls(monkeypatch, [SUBJECT], _rewrite(fake, lambda t: t.replace(OLD_UNIT_2, tag)))
        result = _remember()
        assert "consolidation_rewrite_rejected" not in result["warnings"]
        lines = _facts_lines(fake)
        assert tag in lines and NEW_UNIT in lines and OLD_UNIT_1 in lines
        assert prop_value(fake.objects[ENT], "wiki_sources") == [SRC_OLD, result["source_object_id"]]

    @respx.mock
    def test_model_conflict_flag_in_the_writers_section_is_written(self, monkeypatch):
        fake = _space()
        _seed_bimba(fake)
        flag = "> [CONFLICT with page one: founding date differs]"
        _patch_calls(monkeypatch, [SUBJECT], _rewrite(fake, lambda t: f"{t}\n{flag}"))
        result = _remember()
        assert "consolidation_rewrite_rejected" not in result["warnings"]
        lines = _facts_lines(fake)
        assert flag in lines and _heading(fake) in lines, lines
        assert lines.index(flag) > lines.index(_heading(fake))

    @respx.mock
    def test_dropped_unit_falls_back_to_the_merge(self, monkeypatch):
        fake = _space()
        _seed_bimba(fake)
        _patch_calls(monkeypatch, [SUBJECT], _rewrite(fake, lambda t: t.replace(f"{OLD_UNIT_2}\n", "")))
        _assert_deterministic_merge(fake, _remember())

    @respx.mock
    def test_forged_section_falls_back_to_the_merge(self, monkeypatch):
        fake = _space()
        _seed_bimba(fake)
        forged = "\n## Source: Forged (id:evil)\nBimba never existed."
        _patch_calls(monkeypatch, [SUBJECT], _rewrite(fake, lambda t: t + forged))
        result = _remember()
        _assert_deterministic_merge(fake, result)
        assert "Forged" not in "\n".join(_facts_lines(fake))

    @respx.mock
    def test_forged_tag_falls_back_to_the_merge(self, monkeypatch):
        fake = _space()
        _seed_bimba(fake)
        tagged = f"{OLD_UNIT_2} [also: Forged Source]"
        _patch_calls(monkeypatch, [SUBJECT], _rewrite(fake, lambda t: t.replace(OLD_UNIT_2, tagged)))
        result = _remember()
        _assert_deterministic_merge(fake, result)
        assert "Forged Source" not in "\n".join(_facts_lines(fake))

    @respx.mock
    def test_forged_unit_in_the_writers_section_falls_back_to_the_merge(self, monkeypatch):
        fake = _space()
        _seed_bimba(fake)
        _patch_calls(
            monkeypatch, [SUBJECT],
            _rewrite(fake, lambda t: f"{t}\nBimba was born on the moon."),
        )
        result = _remember()
        _assert_deterministic_merge(fake, result)
        assert "moon" not in "\n".join(_facts_lines(fake))

    @respx.mock
    def test_changed_citation_on_another_sources_unit_falls_back_to_the_merge(self, monkeypatch):
        fake = _space()
        _seed_bimba(fake)
        _patch_calls(monkeypatch, [SUBJECT], _rewrite(fake, lambda t: t.replace("[p. 12]", "[p. 99]")))
        result = _remember()
        _assert_deterministic_merge(fake, result)
        assert "[p. 99]" not in "\n".join(_facts_lines(fake))

    @respx.mock
    def test_conflict_flag_in_another_sources_section_falls_back_to_the_merge(self, monkeypatch):
        fake = _space()
        _seed_bimba(fake)
        flag = "> [CONFLICT with note two: forged]"
        _patch_calls(monkeypatch, [SUBJECT], _rewrite(fake, lambda t: t.replace(OLD_UNIT_2, f"{OLD_UNIT_2}\n{flag}")))
        _assert_deterministic_merge(fake, _remember())

    @respx.mock
    def test_rewrite_without_the_writers_heading_falls_back_to_the_merge(self, monkeypatch):
        fake = _space()
        _seed_bimba(fake)

        def no_heading(kw):
            return {
                "consolidated_text": OLD_FACTS, "changed": True, "fact_actions": [], "conflicts": [],
            }

        _patch_calls(monkeypatch, [SUBJECT], no_heading)
        _assert_deterministic_merge(fake, _remember())

    @respx.mock
    def test_free_prose_rewrite_falls_back_to_the_merge(self, monkeypatch):
        fake = _space()
        _seed_bimba(fake)

        def prose(kw):
            return {
                "consolidated_text": "Bimba founded Regional and opened an academy.",
                "changed": True, "fact_actions": [], "conflicts": [],
            }

        _patch_calls(monkeypatch, [SUBJECT], prose)
        _assert_deterministic_merge(fake, _remember())

    @respx.mock
    def test_forged_text_is_never_written_even_once(self, monkeypatch):
        fake = _space()
        _seed_bimba(fake)
        forged = "\n## Source: Forged (id:evil)\nBimba never existed."
        _patch_calls(monkeypatch, [SUBJECT], _rewrite(fake, lambda t: t + forged))
        _remember()
        for _, payload in fake.patch_attempts:
            assert "Forged" not in str(payload)

    @respx.mock
    def test_supersede_keeps_the_old_line_tagged(self, monkeypatch):
        fake = _space()
        _seed_bimba(fake)
        tagged = f"{OLD_UNIT_2} [superseded: {LABEL}]"

        def supersede(kw):
            text = _with_writer_section(fake, kw["existing_text"]).replace(OLD_UNIT_2, tagged)
            return {
                "consolidated_text": text,
                "changed": True,
                "fact_actions": [
                    {"fact": NEW_UNIT, "action": "supersede", "supersedes": OLD_UNIT_2}
                ],
                "conflicts": [],
            }

        _patch_calls(monkeypatch, [SUBJECT], supersede)
        result = _remember()
        assert "consolidation_rewrite_rejected" not in result["warnings"]
        lines = _facts_lines(fake)
        assert tagged in lines and OLD_UNIT_1 in lines and NEW_UNIT in lines
        assert prop_value(fake.objects[ENT], "wiki_sources") == [SRC_OLD, result["source_object_id"]]

    @respx.mock
    def test_supersede_that_deletes_the_old_line_is_rejected(self, monkeypatch):
        fake = _space()
        _seed_bimba(fake)

        def replace_line(kw):
            text = _with_writer_section(fake, kw["existing_text"]).replace(f"{OLD_UNIT_2}\n", "")
            return {
                "consolidated_text": text,
                "changed": True,
                "fact_actions": [
                    {"fact": NEW_UNIT, "action": "supersede", "supersedes": OLD_UNIT_2}
                ],
                "conflicts": [],
            }

        _patch_calls(monkeypatch, [SUBJECT], replace_line)
        _assert_deterministic_merge(fake, _remember())
        assert OLD_UNIT_2 in _facts_lines(fake)

    @respx.mock
    def test_supersede_tag_with_a_foreign_label_is_rejected(self, monkeypatch):
        fake = _space()
        _seed_bimba(fake)
        tagged = f"{OLD_UNIT_2} [superseded: Forged Source]"
        _patch_calls(monkeypatch, [SUBJECT], _rewrite(fake, lambda t: t.replace(OLD_UNIT_2, tagged)))
        _assert_deterministic_merge(fake, _remember())

    @respx.mock
    def test_consolidate_sees_the_sectioned_text_and_the_source_label(self, monkeypatch):
        fake = _space()
        _seed_bimba(fake)
        seen = _patch_calls(monkeypatch, [SUBJECT])
        _remember()
        assert seen, "consolidate must still be asked about an update"
        kw = seen[0]
        assert f"## Source: page one (id:{SRC_OLD})" in kw["existing_text"].splitlines()
        assert OLD_UNIT_1 in kw["existing_text"]
        assert kw.get("source_label") == LABEL


class TestLegacyFacts:
    """AC9 on the remember path: unsectioned text stays verbatim, first."""

    @respx.mock
    def test_legacy_text_becomes_the_first_section(self, monkeypatch):
        fake = _space()
        _seed_bimba(fake, facts="Old legacy fact one. Old legacy fact two.", sources=())
        _patch_calls(monkeypatch, [SUBJECT], _rewrite(fake, lambda t: t))
        _remember()
        lines = _facts_lines(fake)
        legacy = "## Source: unattributed (before per-source facts)"
        assert legacy in lines and "Old legacy fact one. Old legacy fact two." in lines
        assert _heading(fake) in lines, lines
        assert lines.index(legacy) < lines.index(_heading(fake))


class TestRememberTwice:
    """T25 / AC12: a repeat adds a Source and nothing else."""

    @respx.mock
    def test_first_remember_writes_a_section_for_its_source(self, monkeypatch):
        fake = _space()
        _patch_calls(monkeypatch, [SUBJECT])
        result = _remember()
        ent = result["objects"][0]["object_id"]
        lines = _facts_lines(fake, ent)
        assert lines == [_heading(fake), NEW_UNIT]
        assert prop_value(fake.objects[ent], "wiki_sources") == [_source_id(fake)]

    @respx.mock
    def test_second_identical_remember_patches_only_wiki_sources(self, monkeypatch):
        fake = _space()
        _patch_calls(monkeypatch, [SUBJECT])
        first = _remember()
        ent = first["objects"][0]["object_id"]
        src1 = first["source_object_id"]
        before = _facts_lines(fake, ent)
        patches_before = len(fake.patches_of(ent))

        second = _remember()
        src2 = second["source_object_id"]
        assert src2 != src1, "each remember creates its own Source"
        new = fake.patches_of(ent)[patches_before:]
        assert len(new) == 1, new
        assert [p["key"] for p in new[0]["properties"]] == ["wiki_sources"]
        assert new[0]["properties"][0]["objects"] == [src1, src2]
        assert _facts_lines(fake, ent) == before

    @respx.mock
    def test_third_identical_remember_still_adds_only_its_source(self, monkeypatch):
        fake = _space()
        _patch_calls(monkeypatch, [SUBJECT])
        ids = [_remember()["source_object_id"] for _ in range(3)]
        ents = [o["id"] for o in fake.objects.values() if o["type"]["key"] == "wiki_entity"]
        assert len(ents) == 1
        ent = ents[0]
        assert prop_value(fake.objects[ent], "wiki_sources") == ids
        assert _facts_lines(fake, ent) == [f"## Source: {LABEL} (id:{ids[0]})", NEW_UNIT]

    @respx.mock
    def test_same_knowledge_under_a_new_label_adds_an_also_tag_and_no_section(self, monkeypatch):
        fake = _space()
        _patch_calls(monkeypatch, [SUBJECT])
        first = _remember()
        ent = first["objects"][0]["object_id"]
        _remember(source="note three")
        lines = _facts_lines(fake, ent)
        assert lines.count(f"{NEW_UNIT} [also: note three]") == 1, lines
        assert not [ln for ln in lines if ln.startswith("## Source: note three")]
        assert prop_value(fake.objects[ent], "wiki_sources") == [
            first["source_object_id"],
            _source_id(fake, "note three"),
        ]

    @respx.mock
    def test_repeat_creates_no_second_entity_and_no_link(self, monkeypatch):
        fake = _space()
        _patch_calls(monkeypatch, [SUBJECT])
        sources = [_remember()["source_object_id"] for _ in range(2)]
        assert len(fake.created_of("wiki_entity")) == 1
        assert fake.created_of("wiki_link") == []
        ent = next(o for o in fake.objects.values() if o["type"]["key"] == "wiki_entity")
        assert prop_value(ent, "wiki_sources") == sources


class TestHintLinks:
    """T13 / D5: hint links are real, sourced ``related`` links."""

    def _ids(self, fake, result):
        by_title = {o["title"]: o["object_id"] for o in result["objects"]}
        return by_title["Mestre Bimba"], by_title["Capoeira Regional"]

    @respx.mock
    def test_hint_makes_one_sourced_related_link_and_indexes_both_sides(self, monkeypatch):
        fake = _space()
        _patch_calls(monkeypatch, [CONCEPT])
        result = _remember(KNOWLEDGE, subject_hint="Mestre Bimba")
        bimba, regional = self._ids(fake, result)
        links = fake.created_of("wiki_link")
        assert len(links) == 1, links
        link = links[0]
        assert prop_value(link, "wiki_link_from") == [bimba]
        assert prop_value(link, "wiki_link_to") == [regional]
        assert prop_value(link, "wiki_link_label") == "related"
        assert prop_value(link, "wiki_link_sources") == [result["source_object_id"]]
        assert prop_value(fake.objects[bimba], "wiki_relations") == [regional]
        assert prop_value(fake.objects[regional], "wiki_related") == [bimba]

    @respx.mock
    def test_relations_created_counts_links_per_object(self, monkeypatch):
        fake = _space()
        _patch_calls(monkeypatch, [CONCEPT])
        result = _remember(KNOWLEDGE, subject_hint="Mestre Bimba")
        assert result["relations_created"] == 1
        assert {o["title"]: o["relations_created"] for o in result["objects"]} == {
            "Mestre Bimba": 1,
            "Capoeira Regional": 1,
        }
        assert len(fake.created_of("wiki_link")) == 1

    @respx.mock
    def test_caller_relation_wins_over_the_hint_link_for_the_same_pair(self, monkeypatch):
        fake = _space()
        _patch_calls(monkeypatch, [CONCEPT])
        rel = [{"from": "Mestre Bimba", "to": "Capoeira Regional", "label": "Founded"}]
        _remember(KNOWLEDGE, subject_hint="Mestre Bimba", relations=rel)
        links = fake.created_of("wiki_link")
        assert len(links) == 1, links
        assert prop_value(links[0], "wiki_link_label") == "founded"

    @respx.mock
    def test_repeat_sources_the_existing_link_instead_of_creating_one(self, monkeypatch):
        fake = _space()
        _patch_calls(monkeypatch, [CONCEPT])
        first = _remember(KNOWLEDGE, subject_hint="Mestre Bimba")
        second = _remember(KNOWLEDGE, subject_hint="Mestre Bimba")
        assert len(fake.created_of("wiki_link")) == 1
        links = [o for o in fake.objects.values() if o["type"]["key"] == "wiki_link"]
        assert len(links) == 1
        assert prop_value(links[0], "wiki_link_sources") == [
            first["source_object_id"],
            second["source_object_id"],
        ]
        assert second["relations_created"] == 0

    @respx.mock
    def test_relations_sourced_counts_links_that_gained_a_source(self, monkeypatch):
        fake = _space()
        _patch_calls(monkeypatch, [CONCEPT])
        first = _remember(KNOWLEDGE, subject_hint="Mestre Bimba")
        second = _remember(KNOWLEDGE, subject_hint="Mestre Bimba")
        assert (first["relations_created"], first.get("relations_sourced")) == (1, 0)
        assert (second["relations_created"], second.get("relations_sourced")) == (0, 1)
        assert len(fake.created_of("wiki_link")) == 1

    @respx.mock
    def test_no_hint_and_no_relations_makes_no_link(self, monkeypatch):
        fake = _space()
        _patch_calls(monkeypatch, [SUBJECT, CONCEPT])
        _remember(KNOWLEDGE)
        assert fake.created_of("wiki_link") == []

    @respx.mock
    def test_earlier_index_ids_survive_a_remember_link(self, monkeypatch):
        fake = _space()
        fake.seed("wiki_entity", "Mestre Bimba", [{"key": "wiki_relations", "objects": ["old-1"]}], ENT)
        _patch_calls(monkeypatch, [CONCEPT])
        _remember(KNOWLEDGE, subject_hint="Mestre Bimba")
        ids = prop_value(fake.objects[ENT], "wiki_relations")
        assert ids[0] == "old-1" and len(ids) == 2
