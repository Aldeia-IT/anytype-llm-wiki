"""Typed, sourced links: the ``wiki/links.py`` module (Aldeia-IT/aldeia-box#1486).

T1 (link, label, source, both index sides), T3 (``relation_specs``), T4 (second source,
no Source), T6 (failure and rollback), T7 (label table) and the ``link_object_name``
half of T15. Anytype is the ``FakeWiki`` respx fake; no live space.
"""

import pytest
import respx

from .fakes import ANYTYPE_BASE, SPACE, FakeWiki, prop_value

A, B, C = "obj-a-0001", "obj-b-0002", "obj-c-0003"
SRC1, SRC2 = "src-0001", "src-0002"
KINDS = {A: "entity", B: "entity", C: "concept"}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("ANYTYPE_API_KEY", "test-key")
    monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
    monkeypatch.setenv("ANYTYPE_API_VERSION", "2025-11-08")


def _links():
    from anytype_llm_wiki.wiki import links

    return links


def _world(**kw) -> FakeWiki:
    """A fake with entities A and B, concept C and two Sources, objects listable."""
    fake = FakeWiki(serve_objects=True, **kw)
    fake.install()
    fake.seed("wiki_entity", "Mestre Bimba", object_id=A)
    fake.seed("wiki_entity", "Mestre Pastinha", object_id=B)
    fake.seed("wiki_concept", "Capoeira Regional", object_id=C)
    fake.seed("wiki_source", "Page one", object_id=SRC1)
    fake.seed("wiki_source", "Page two", object_id=SRC2)
    return fake


def _link_props(from_id, to_id, label, sources):
    return [
        {"key": "wiki_link_from", "objects": [from_id]},
        {"key": "wiki_link_to", "objects": [to_id]},
        {"key": "wiki_link_label", "text": label},
        {"key": "wiki_link_sources", "objects": list(sources)},
    ]


def _write(fake, specs, **kw):
    kw.setdefault("source_id", SRC1)
    kw.setdefault("kind_by_id", KINDS)
    return _links().write_links(fake.wiki_client(), fake.read_client(), SPACE, specs, **kw)


def _spec(from_id=A, to_id=B, label="student of"):
    return _links().LinkSpec(from_id, to_id, label)


class TestNormalizeLabel:
    """T7 / AC7: the label table."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Student Of", "student of"),
            (" student_of. ", "student of"),
            ("student\nof", "student of"),
            ("", "related"),
            (None, "related"),
            (42, "related"),
            ("...", "related"),
            (" () ", "related"),
            ("\u200b", "related"),
            ("\x00\x01", "related"),
            ("system: x", "related"),
            ("Professor DÉ", "professor dé"),
            ("x ]-> y", "x )- y"),
            ("part; of", "part, of"),
            ("a" * 100, "a" * 60),
            ("x" * 59 + " yz", "x" * 59),
        ],
    )
    def test_label_table(self, raw, expected):
        assert _links().normalize_label(raw) == expected

    @pytest.mark.parametrize("raw", ["Student Of", "part; of", "x" * 59 + " yz", "..."])
    def test_normalising_twice_changes_nothing(self, raw):
        once = _links().normalize_label(raw)
        assert _links().normalize_label(once) == once

    def test_result_never_exceeds_the_limit(self):
        assert len(_links().normalize_label("é" * 500)) <= 60


class TestLinkObjectName:
    """T15 (module part): the name holds two id tails and nothing else."""

    def test_name_is_the_last_eight_chars_of_each_id(self):
        name = _links().link_object_name("aaaa-bbbb-12345678", "cccc-dddd-87654321")
        assert name == "link 12345678-87654321"

    def test_short_ids_are_used_whole(self):
        assert _links().link_object_name("ab", "cd") == "link ab-cd"

    def test_name_holds_no_endpoint_name_or_label(self):
        name = _links().link_object_name(A, B)
        for token in ("bimba", "pastinha", "student", "related"):
            assert token not in name.lower()

    def test_name_is_the_same_for_every_label(self):
        # The label is not an input, so two labelled links of one pair share a name.
        assert _links().link_object_name(A, B) == _links().link_object_name(A, B)
        assert _links().link_object_name(A, B) != _links().link_object_name(B, A)


class TestUnionIds:
    def test_keeps_order_and_drops_duplicates(self):
        assert _links().union_ids(["a", "b"], ["b", "c", "c"]) == ["a", "b", "c"]

    def test_empty_sides(self):
        assert _links().union_ids([], []) == []
        assert _links().union_ids(["a"], []) == ["a"]
        assert _links().union_ids([], ["a"]) == ["a"]

    def test_duplicates_inside_current_collapse(self):
        assert _links().union_ids(["a", "a"], []) == ["a"]

    def test_inputs_are_not_mutated(self):
        cur, add = ["a"], ["b"]
        _links().union_ids(cur, add)
        assert cur == ["a"] and add == ["b"]


class TestParseLink:
    def _obj(self, **over):
        obj = {
            "id": "lnk-1",
            "type": {"key": "wiki_link"},
            "properties": _link_props(A, B, "student of", [SRC1]),
        }
        obj.update(over)
        return obj

    def test_parses_a_link(self):
        rec = _links().parse_link(self._obj())
        assert rec == _links().LinkRecord("lnk-1", A, B, "student of", (SRC1,))

    def test_object_shaped_ids_parse(self):
        obj = self._obj()
        obj["properties"][0] = {"key": "wiki_link_from", "objects": [{"id": A}]}
        assert _links().parse_link(obj).from_id == A

    def test_no_sources_is_an_empty_tuple(self):
        obj = self._obj()
        obj["properties"] = _link_props(A, B, "related", [])
        assert _links().parse_link(obj).source_ids == ()

    def test_other_type_is_none(self):
        assert _links().parse_link(self._obj(type={"key": "wiki_entity"})) is None

    def test_missing_endpoint_is_none(self):
        obj = self._obj()
        obj["properties"] = [p for p in obj["properties"] if p["key"] != "wiki_link_to"]
        assert _links().parse_link(obj) is None

    def test_two_ids_on_one_side_is_malformed(self):
        obj = self._obj()
        obj["properties"][0] = {"key": "wiki_link_from", "objects": [A, C]}
        assert _links().parse_link(obj) is None

    def test_not_a_dict_properties_is_none(self):
        assert _links().parse_link(self._obj(properties=None)) is None


class TestLoadLinkIndex:
    @respx.mock
    def test_keys_by_from_label_to_and_skips_non_links(self):
        fake = _world()
        fake.seed("wiki_link", "link a-b", _link_props(A, B, "student of", [SRC1]), "lnk-1")
        fake.seed("wiki_link", "link b-a", _link_props(B, A, "teacher of", []), "lnk-2")
        fake.seed("wiki_link", "link broken", [{"key": "wiki_link_label", "text": "x"}], "lnk-3")
        index = _links().load_link_index(fake.wiki_client(), SPACE)
        assert set(index) == {(A, "student of", B), (B, "teacher of", A)}
        assert index[(A, "student of", B)].id == "lnk-1"


class TestLinksByEndpoint:
    def test_a_link_is_listed_under_both_endpoints(self):
        objs = [
            {"id": "lnk-1", "type": {"key": "wiki_link"},
             "properties": _link_props(A, B, "student of", [SRC1])},
            {"id": "lnk-2", "type": {"key": "wiki_link"},
             "properties": _link_props(C, A, "related", [])},
            {"id": A, "type": {"key": "wiki_entity"}, "properties": []},
        ]
        by = _links().links_by_endpoint(objs)
        assert {r.id for r in by[A]} == {"lnk-1", "lnk-2"}
        assert {r.id for r in by[B]} == {"lnk-1"}
        assert {r.id for r in by[C]} == {"lnk-2"}

    def test_no_links_gives_no_endpoints(self):
        assert _links().links_by_endpoint([{"id": A, "type": {"key": "wiki_entity"}}]) == {}


NAMES = {"mestre bimba": A, "mestre pastinha": B, "capoeira regional": C}


class TestRelationSpecs:
    """T3: validation of the model's ``relations``."""

    def _specs(self, relations, names=None):
        return _links().relation_specs({"relations": relations}, names or NAMES)

    def test_resolves_names_and_normalises_the_label(self):
        specs, warnings = self._specs(
            [{"from": "Mestre Bimba", "to": "  MESTRE Pastinha ", "label": "Student_Of."}]
        )
        assert specs == [_links().LinkSpec(A, B, "student of")]
        assert warnings == []

    def test_unresolved_endpoint_warns_with_its_name(self):
        specs, warnings = self._specs([{"from": "Mestre Bimba", "to": "Ghost", "label": "x"}])
        assert specs == []
        assert warnings == ["relation_endpoint_unresolved: Ghost"]

    def test_endpoint_whose_write_failed_is_unresolved(self):
        names = {k: v for k, v in NAMES.items() if v != B}
        specs, warnings = self._specs(
            [{"from": "Mestre Bimba", "to": "Mestre Pastinha", "label": "x"}], names
        )
        assert specs == []
        assert any(w.startswith("relation_endpoint_unresolved:") for w in warnings)

    def test_self_loop_is_dropped(self):
        specs, _ = self._specs([{"from": "Mestre Bimba", "to": "mestre bimba", "label": "x"}])
        assert specs == []

    @pytest.mark.parametrize(
        "item",
        [None, "Mestre Bimba -> Mestre Pastinha", 7, ["a", "b"]],
    )
    def test_non_dict_items_are_dropped(self, item):
        good = {"from": "Mestre Bimba", "to": "Mestre Pastinha", "label": "student of"}
        specs, _ = self._specs([item, good])
        assert specs == [_links().LinkSpec(A, B, "student of")]

    @pytest.mark.parametrize("field", ["from", "to"])
    def test_non_string_endpoint_is_dropped(self, field):
        item = {"from": "Mestre Bimba", "to": "Mestre Pastinha", "label": "x"}
        item[field] = 5
        specs, _ = self._specs([item])
        assert specs == []

    def test_duplicates_collapse_after_normalising(self):
        rel = {"from": "Mestre Bimba", "to": "Mestre Pastinha"}
        specs, _ = self._specs(
            [{**rel, "label": "Student Of"}, {**rel, "label": " student_of "}]
        )
        assert specs == [_links().LinkSpec(A, B, "student of")]

    def test_direction_and_label_make_distinct_links(self):
        fwd = {"from": "Mestre Bimba", "to": "Mestre Pastinha"}
        rev = {"from": "Mestre Pastinha", "to": "Mestre Bimba"}
        specs, _ = self._specs(
            [{**fwd, "label": "a"}, {**rev, "label": "a"}, {**fwd, "label": "b"}]
        )
        assert {(s.from_id, s.label, s.to_id) for s in specs} == {
            (A, "a", B),
            (B, "a", A),
            (A, "b", B),
        }

    def test_relation_to_a_concept_resolves(self):
        specs, _ = self._specs(
            [{"from": "Mestre Bimba", "to": "Capoeira Regional", "label": "founded"}]
        )
        assert specs == [_links().LinkSpec(A, C, "founded")]

    @pytest.mark.parametrize("extracted", [{}, {"relations": None}, {"relations": "x"}])
    def test_missing_or_malformed_relations_give_nothing(self, extracted):
        assert _links().relation_specs(extracted, NAMES) == ([], [])

    def test_empty_relations_give_nothing(self):
        assert self._specs([]) == ([], [])

    def test_cap_keeps_the_limit_and_warns(self):
        cap = _links().RELATION_SPECS_MAX
        names = {f"n{i}": f"id-{i}" for i in range(cap + 10)}
        relations = [{"from": "n0", "to": f"n{i}", "label": "x"} for i in range(1, cap + 6)]
        specs, warnings = _links().relation_specs({"relations": relations}, names)
        assert len(specs) == cap
        assert "relations_capped" in warnings

    def test_exactly_the_cap_does_not_warn(self):
        cap = _links().RELATION_SPECS_MAX
        names = {f"n{i}": f"id-{i}" for i in range(cap + 10)}
        relations = [{"from": "n0", "to": f"n{i}", "label": "x"} for i in range(1, cap + 1)]
        specs, warnings = _links().relation_specs({"relations": relations}, names)
        assert len(specs) == cap
        assert "relations_capped" not in warnings


class TestWriteLinkAndIndex:
    """T1 / AC1: one link, its label and source, both index sides, nothing else."""

    @respx.mock
    def test_creates_one_sourced_link_and_indexes_both_sides(self):
        fake = _world()
        result = _write(fake, [_spec()])
        assert (result.created, result.sourced, result.unchanged) == (1, 0, 0)
        assert (result.skipped, result.failed) == (0, 0)
        (link,) = fake.created_of("wiki_link")
        assert link["name"] == _links().link_object_name(A, B)
        assert prop_value(link, "wiki_link_from") == [A]
        assert prop_value(link, "wiki_link_to") == [B]
        assert prop_value(link, "wiki_link_label") == "student of"
        assert prop_value(link, "wiki_link_sources") == [SRC1]
        assert prop_value(fake.objects[A], "wiki_relations") == [B]
        assert prop_value(fake.objects[B], "wiki_relations") == [A]

    @respx.mock
    def test_only_the_two_endpoints_are_patched(self):
        fake = _world()
        _write(fake, [_spec()])
        assert sorted(oid for oid, _ in fake.patch_attempts) == sorted([A, B])
        assert fake.created_of("wiki_entity") == [] and fake.created_of("wiki_concept") == []

    @respx.mock
    def test_concept_endpoint_uses_wiki_related(self):
        fake = _world()
        _write(fake, [_spec(A, C, "founded")])
        assert prop_value(fake.objects[A], "wiki_relations") == [C]
        assert prop_value(fake.objects[C], "wiki_related") == [A]
        assert prop_value(fake.objects[C], "wiki_relations") is None

    @respx.mock
    def test_no_specs_writes_and_reads_nothing(self):
        fake = _world()
        result = _write(fake, [])
        assert (result.created, result.failed, result.skipped) == (0, 0, 0)
        assert fake.created == [] and fake.patch_attempts == []

    @respx.mock
    def test_earlier_index_ids_survive(self):
        fake = _world()
        fake.objects[A]["properties"].append({"key": "wiki_relations", "objects": ["old-1"]})
        _write(fake, [_spec()])
        assert prop_value(fake.objects[A], "wiki_relations") == ["old-1", B]

    @respx.mock
    def test_two_specs_on_one_endpoint_accumulate_with_one_read(self):
        fake = _world()
        _write(fake, [_spec(A, B, "x"), _spec(A, C, "y")])
        assert prop_value(fake.objects[A], "wiki_relations") == [B, C]
        a_reads = [p for m, p in fake.requests if m == "GET" and p.endswith(f"/objects/{A}")]
        assert len(a_reads) == 1

    @respx.mock
    def test_direction_matters(self):
        fake = _world()
        result = _write(fake, [_spec(A, B, "student of"), _spec(B, A, "student of")])
        assert result.created == 2
        assert len(fake.created_of("wiki_link")) == 2

    @respx.mock
    def test_already_indexed_pair_sends_no_patch(self):
        fake = _world()
        fake.objects[A]["properties"].append({"key": "wiki_relations", "objects": [B]})
        fake.objects[B]["properties"].append({"key": "wiki_relations", "objects": [A]})
        _write(fake, [_spec()])
        assert fake.patch_attempts == []

    @respx.mock
    def test_index_cache_replaces_reads_and_is_updated(self):
        fake = _world()
        cache = {A: ["old-1"], B: []}
        _write(fake, [_spec()], index_cache=cache)
        assert not [1 for m, p in fake.requests if m == "GET" and f"/objects/{A}" in p]
        assert fake.patches_of(A)[0]["properties"] == [
            {"key": "wiki_relations", "objects": ["old-1", B]}
        ]
        assert cache[A] == ["old-1", B]
        assert cache[B] == [A]

    @respx.mock
    def test_passed_link_index_is_extended_with_the_new_link(self):
        fake = _world()
        index: dict = {}
        _write(fake, [_spec()], link_index=index)
        assert list(index) == [(A, "student of", B)]
        assert not [1 for m, p in fake.requests if m == "GET" and p.endswith("/objects")]


class TestSecondSourceAndNoSource:
    """T4 / AC6: a second source joins the link; no Source writes nothing."""

    def _existing(self, fake, sources):
        return fake.seed(
            "wiki_link", "link x-y", _link_props(A, B, "student of", sources), "lnk-1"
        )

    @respx.mock
    def test_second_source_is_unioned_into_the_one_link(self):
        fake = _world()
        self._existing(fake, [SRC1])
        result = _write(fake, [_spec()], source_id=SRC2)
        assert (result.created, result.sourced, result.unchanged) == (0, 1, 0)
        assert fake.created_of("wiki_link") == []
        assert prop_value(fake.objects["lnk-1"], "wiki_link_sources") == [SRC1, SRC2]

    @respx.mock
    def test_same_source_again_is_unchanged_and_sends_no_link_patch(self):
        fake = _world()
        self._existing(fake, [SRC1])
        result = _write(fake, [_spec()], source_id=SRC1)
        assert (result.created, result.sourced, result.unchanged) == (0, 0, 1)
        assert not fake.patches_of("lnk-1")

    @respx.mock
    def test_same_pair_other_label_is_a_new_link(self):
        fake = _world()
        self._existing(fake, [SRC1])
        result = _write(fake, [_spec(label="teacher of")], source_id=SRC2)
        assert result.created == 1 and result.sourced == 0

    @respx.mock
    def test_creating_the_same_link_twice_in_one_call_makes_one_object(self):
        fake = _world()
        result = _write(fake, [_spec(), _spec()])
        assert len(fake.created_of("wiki_link")) == 1
        assert result.created == 1 and result.unchanged == 1

    @respx.mock
    def test_no_source_skips_the_link_with_a_note(self):
        fake = _world()
        result = _write(fake, [_spec()], source_id=None)
        assert result.skipped == 1 and result.created == 0 and result.failed == 0
        assert any("link_skipped_no_source" in n for n in result.notes)
        assert fake.created == [] and fake.patch_attempts == []

    @respx.mock
    def test_self_loop_is_skipped(self):
        fake = _world()
        result = _write(fake, [_spec(A, A)])
        assert result.skipped == 1 and result.created == 0
        assert fake.created == [] and fake.patch_attempts == []


class TestFailuresAndRollback:
    """T6 / AC5: create, read, first- and second-side failures."""

    @respx.mock
    def test_create_failure_counts_failed_and_skips_the_index(self):
        fake = _world()
        fake.fail("POST", type_key="wiki_link")
        result = _write(fake, [_spec()])
        assert result.failed == 1 and result.created == 0
        assert any("link_create_failed" in n for n in result.notes)
        assert fake.patch_attempts == []

    @respx.mock
    def test_one_failed_create_does_not_stop_the_next_spec(self):
        fake = _world()
        fake.fail("POST", type_key="wiki_link", nth=1)
        result = _write(fake, [_spec(A, B, "x"), _spec(A, C, "y")])
        assert result.failed == 1 and result.created == 1
        assert len(fake.objects) == 6  # five seeded + the one link that was created

    @respx.mock
    def test_read_failure_skips_the_index_patch_and_keeps_the_link(self):
        fake = _world()
        fake.fail("GET", object_id=A)
        result = _write(fake, [_spec()])
        assert result.failed == 1
        assert any("relation_index_read_failed" in n for n in result.notes)
        assert fake.patches_of(A) == []
        assert len(fake.created_of("wiki_link")) == 1

    @respx.mock
    def test_first_side_failure_skips_the_second_side(self):
        fake = _world()
        fake.fail("PATCH", object_id=A)
        result = _write(fake, [_spec()])
        assert result.failed == 1
        assert any("relation_index_write_failed" in n for n in result.notes)
        assert [oid for oid, _ in fake.patch_attempts] == [A]
        assert len(fake.created_of("wiki_link")) == 1

    @respx.mock
    def test_second_side_failure_restores_the_first_side(self):
        fake = _world()
        fake.objects[A]["properties"].append({"key": "wiki_relations", "objects": ["old-1"]})
        fake.fail("PATCH", object_id=B)
        cache = {A: ["old-1"], B: ["old-2"]}
        result = _write(fake, [_spec()], index_cache=cache)
        assert result.failed == 1
        assert any("relation_rollback" in n for n in result.notes)
        assert [oid for oid, _ in fake.patch_attempts] == [A, B, A]
        assert fake.patch_attempts[2][1]["properties"] == [
            {"key": "wiki_relations", "objects": ["old-1"]}
        ]
        assert prop_value(fake.objects[A], "wiki_relations") == ["old-1"]
        assert cache[A] == ["old-1"]
        assert len(fake.created_of("wiki_link")) == 1

    @respx.mock
    def test_rollback_to_an_empty_index(self):
        fake = _world()
        fake.fail("PATCH", object_id=B)
        _write(fake, [_spec()])
        assert prop_value(fake.objects[A], "wiki_relations") == []

    @respx.mock
    def test_writing_the_link_again_repairs_the_index(self):
        fake = _world()
        fake.fail("PATCH", object_id=B)
        first = _write(fake, [_spec()])
        assert first.failed == 1
        second = _write(fake, [_spec()])
        assert (second.created, second.failed, second.unchanged) == (0, 0, 1)
        assert len(fake.created_of("wiki_link")) == 1
        assert prop_value(fake.objects[A], "wiki_relations") == [B]
        assert prop_value(fake.objects[B], "wiki_relations") == [A]
