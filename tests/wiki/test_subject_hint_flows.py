"""End-to-end flows for Aldeia-IT/aldeia-box#1430 against an in-memory fake client.

``_run_ingest`` and ``_apply_batch`` run for real; the network edges (fetch,
extraction, Source/WikiLog writes, relation writes, reindex) are stubbed.
"""

import pytest

from anytype_llm_wiki.wiki import ingest, remember

SPACE = "space-1430"
URL = "https://example.com/bimba"


class FakeClient:
    """Minimal WikiClient: search returns every object (the caller filters by type)."""

    def __init__(self, objects=()):
        self.objects: dict[str, dict] = {}
        self.created: list[dict] = []
        self.updated: list[tuple[str, dict]] = []
        self.searches: list[str] = []
        for i, (name, type_key) in enumerate(objects):
            self.objects[f"old-{i}"] = {
                "id": f"old-{i}", "name": name, "type": {"key": type_key}, "properties": [],
            }

    def search(self, space_id, query, filter=None):
        self.searches.append(query)
        return list(self.objects.values())

    def create_object(self, space_id, type_key, name, properties=None, **kw):
        oid = f"new-{len(self.created)}"
        self.created.append({"id": oid, "name": name, "type_key": type_key})
        self.objects[oid] = {"id": oid, "name": name, "type": {"key": type_key}, "properties": []}
        return {"id": oid, "name": name}

    def update_object(self, space_id, object_id, patch):
        self.updated.append((object_id, patch))
        return {"id": object_id}


class FakeRead:
    def close(self):
        pass


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("WIKI_STRIP_NAME_TITLES_SPACES", raising=False)
    monkeypatch.delenv("WIKI_REFUSE_IDENTIFIER_NAMES_SPACES", raising=False)
    monkeypatch.delenv("WIKI_EXTRACT_ENDPOINT", raising=False)


@pytest.fixture
def run(monkeypatch):
    """Return ``run(extracted, hint=None, client=None, is_url=True, markdown=...)``."""
    calls: dict = {"extract": [], "relations": []}

    def go(extracted, hint=None, client=None, is_url=True, markdown="# Page\n\nBody."):
        client = client or FakeClient()
        monkeypatch.setattr(ingest, "AnytypeReadClient", FakeRead)
        monkeypatch.setattr(
            ingest, "fetch_source",
            lambda source: {"markdown": markdown, "is_url": is_url, "unusable": None},
        )

        def fake_extract(**kw):
            calls["extract"].append(kw)
            return extracted

        monkeypatch.setattr(ingest, "extract", fake_extract)
        monkeypatch.setattr(ingest, "_create_source", lambda *a, **k: ("src-1", False))
        monkeypatch.setattr(ingest, "_resolve_wiki_action_tag", lambda *a, **k: ("tag", False))
        monkeypatch.setattr(ingest, "_write_wikilog", lambda *a, **k: "log-1")
        monkeypatch.setattr(ingest, "_maybe_reindex", lambda *a, **k: None)
        monkeypatch.setattr(ingest, "detect_contradictions", lambda *a, **k: [])

        def fake_rel(client_, space_id, relations, kind_by_id):
            calls["relations"].extend(relations)
            return len(relations), []

        monkeypatch.setattr(ingest, "_write_bidirectional_relations", fake_rel)
        kwargs = {} if hint is None else {"subject_hint": hint}
        source = URL if is_url else "/tmp/page.md"
        result = ingest._run_ingest(client, source, SPACE, None, [], **kwargs)
        return result, client, calls

    return go


def _titles(result):
    return [o["title"] for o in result["objects_created"] + result["objects_updated"]]


EXTRACTED = {
    "entities": [
        {"name": "Manoel dos Reis Machado", "description": "Founder of Capoeira Regional."},
        {"name": "Salvador", "description": "A city."},
    ],
    "concepts": [],
    "primary_subject": "Manoel dos Reis Machado",
}


class TestIngestSubjectHint:
    def test_without_a_hint_nothing_changes(self, run):
        result, _client, calls = run(EXTRACTED)
        assert _titles(result) == ["Manoel dos Reis Machado", "Salvador"]
        assert calls["extract"][0]["subject_hint"] is None
        assert result["warnings"] == []

    def test_hint_reaches_extract(self, run):
        _, _, calls = run(EXTRACTED, hint="Mestre Bimba")
        assert calls["extract"][0]["subject_hint"] == "Mestre Bimba"

    def test_marked_primary_is_renamed_and_relations_point_at_it(self, run):
        result, client, calls = run(EXTRACTED, hint="Mestre Bimba")
        assert _titles(result) == ["Mestre Bimba", "Salvador"]
        by_name = {o["name"]: o["id"] for o in client.created}
        assert "Manoel dos Reis Machado" not in by_name
        assert calls["relations"] == [(by_name["Mestre Bimba"], by_name["Salvador"], "related")]

    def test_other_entities_keep_their_extracted_names(self, run):
        result, _, _ = run(EXTRACTED, hint="Mestre Bimba")
        assert "Salvador" in _titles(result)

    def test_fold_of_another_spelling(self, run):
        extracted = {
            "entities": [{"name": "mestre bimba", "description": "a"},
                         {"name": "Mestre Bimba", "description": "b"},
                         {"name": "Salvador", "description": "c"}],
            "concepts": [],
        }
        result, client, _ = run(extracted, hint="Mestre Bimba")
        assert _titles(result) == ["Mestre Bimba", "Salvador"]
        assert len(client.created) == 2
        assert result["warnings"] == []

    def test_qualified_hint_names_the_titled_base(self, run):
        """Aldeia-IT/aldeia-box#1439: "Mestre Onça" is the subject "Onça (São Paulo)"."""
        extracted = {
            "entities": [{"name": "Mestre Onça", "description": "a"},
                         {"name": "Onça (Rio)", "description": "b"}],
            "concepts": [],
        }
        result, client, calls = run(extracted, hint="Onça (São Paulo)")
        assert _titles(result) == ["Onça (São Paulo)", "Onça (Rio)"]
        by_name = {o["name"]: o["id"] for o in client.created}
        assert calls["relations"] == [(by_name["Onça (São Paulo)"], by_name["Onça (Rio)"], "related")]
        assert result["warnings"] == []

    def test_unmatched_hint_warns_and_creates_everything_as_extracted(self, run):
        extracted = {"entities": [{"name": "Salvador", "description": "c"}], "concepts": []}
        result, _, _ = run(extracted, hint="Mestre Bimba")
        assert _titles(result) == ["Salvador"]
        assert (
            'subject_hint_unmatched: no extracted entity is the primary subject "Mestre Bimba"'
            in result["warnings"]
        )

    def test_a_marker_naming_no_entity_warns(self, run):
        extracted = dict(EXTRACTED, primary_subject="Nobody")
        result, _, _ = run(extracted, hint="Mestre Bimba")
        assert any(w.startswith("subject_hint_unmatched") for w in result["warnings"])
        assert _titles(result) == ["Manoel dos Reis Machado", "Salvador"]

    def test_marker_is_ignored_without_a_hint(self, run):
        result, _, _ = run(EXTRACTED)
        assert _titles(result) == ["Manoel dos Reis Machado", "Salvador"]

    def test_degraded_url_reports_only_the_degradation(self, run):
        extracted = {"entities": [], "concepts": [], "error": "extraction_degraded: timeout"}
        result, client, _ = run(extracted, hint="Mestre Bimba")
        assert "extraction_degraded" in result["warnings"]
        assert not any(w.startswith("subject_hint_unmatched") for w in result["warnings"])
        assert client.created == []

    def test_local_file_heading_fallback_folds_a_matching_heading(self, run):
        degraded = {"entities": [], "concepts": [], "error": "extraction_degraded: timeout"}
        result, _client, _ = run(
            degraded, hint="Mestre Bimba", is_url=False,
            markdown="# mestre bimba\n\nBorn in Salvador.\n\n# Salvador\n\nA city.",
        )
        assert _titles(result) == ["Mestre Bimba", "Salvador"]

    def test_local_file_heading_fallback_without_match_warns(self, run):
        degraded = {"entities": [], "concepts": [], "error": "extraction_degraded: timeout"}
        result, _, _ = run(degraded, hint="Mestre Bimba", is_url=False,
                           markdown="# Salvador\n\nA city.")
        assert any(w.startswith("subject_hint_unmatched") for w in result["warnings"])

    def test_primary_is_not_refused_by_the_identifier_policy(self, run, monkeypatch):
        monkeypatch.setenv("WIKI_REFUSE_IDENTIFIER_NAMES_SPACES", SPACE)
        extracted = {
            "entities": [{"name": "anytype-llm-wiki", "description": "the tool"},
                         {"name": "wiki_query", "description": "a tool"}],
            "concepts": [],
            "primary_subject": "anytype-llm-wiki",
        }
        result, _, _ = run(extracted, hint="anytype-llm-wiki")
        assert _titles(result) == ["anytype-llm-wiki"]
        assert "name_policy_rejected: identifier_like: wiki_query" in result["warnings"]

    def test_without_a_hint_identifier_names_are_still_refused(self, run, monkeypatch):
        monkeypatch.setenv("WIKI_REFUSE_IDENTIFIER_NAMES_SPACES", SPACE)
        extracted = {"entities": [{"name": "anytype-llm-wiki", "description": "x"}],
                     "concepts": []}
        result, _, _ = run(extracted)
        assert _titles(result) == []


class TestIngestTitleStrip:
    def test_unlisted_space_keeps_titled_names(self, run):
        extracted = {"entities": [{"name": "Mestre Moraes", "description": "d"}], "concepts": []}
        result, _client, _ = run(extracted)
        assert _titles(result) == ["Mestre Moraes"]

    def test_listed_space_creates_the_bare_name(self, run, monkeypatch):
        monkeypatch.setenv("WIKI_STRIP_NAME_TITLES_SPACES", f"other, {SPACE}")
        extracted = {
            "entities": [{"name": "Mestre Moraes", "description": "d"},
                         {"name": "Contra-Mestre Fulano", "description": "e"},
                         {"name": "Mestre", "description": "only a title"}],
            "concepts": [],
        }
        result, _, _ = run(extracted)
        assert _titles(result) == ["Moraes", "Fulano", "Mestre"]

    def test_listed_space_updates_an_existing_titled_object(self, run, monkeypatch):
        monkeypatch.setenv("WIKI_STRIP_NAME_TITLES_SPACES", SPACE)
        client = FakeClient([("Mestre Moraes", "wiki_entity")])
        extracted = {"entities": [{"name": "Moraes", "description": "new facts"}], "concepts": []}
        result, client, _ = run(extracted, client=client)
        assert client.created == []
        assert [o["object_id"] for o in result["objects_updated"]] == ["old-0"]

    def test_listed_space_updates_an_existing_bare_object_for_a_titled_name(
        self, run, monkeypatch
    ):
        monkeypatch.setenv("WIKI_STRIP_NAME_TITLES_SPACES", SPACE)
        client = FakeClient([("Moraes", "wiki_entity")])
        extracted = {"entities": [{"name": "Mestre Moraes", "description": "f"}],
                     "concepts": []}
        result, client, _ = run(extracted, client=client)
        assert client.created == []
        assert [o["object_id"] for o in result["objects_updated"]] == ["old-0"]

    def test_unlisted_space_still_splits_on_the_same_data(self, run):
        client = FakeClient([("Mestre Moraes", "wiki_entity")])
        extracted = {"entities": [{"name": "Moraes", "description": "f"}], "concepts": []}
        _result, client, _ = run(extracted, client=client)
        assert [c["name"] for c in client.created] == ["Moraes"]

    def test_hint_with_a_title_names_the_bare_object(self, run, monkeypatch):
        monkeypatch.setenv("WIKI_STRIP_NAME_TITLES_SPACES", SPACE)
        result, _client, calls = run(EXTRACTED, hint="Mestre Bimba")
        assert _titles(result) == ["Bimba", "Salvador"]
        assert calls["extract"][0]["subject_hint"] == "Mestre Bimba"

    def test_page_naming_both_forms_makes_one_object(self, run, monkeypatch):
        monkeypatch.setenv("WIKI_STRIP_NAME_TITLES_SPACES", SPACE)
        extracted = {"entities": [{"name": "Mestre Bimba", "description": "a"},
                                  {"name": "Bimba", "description": "b"}], "concepts": []}
        _result, client, _ = run(extracted, hint="Mestre Bimba")
        assert [c["name"] for c in client.created] == ["Bimba"]

    def test_relations_use_the_stripped_names(self, run, monkeypatch):
        monkeypatch.setenv("WIKI_STRIP_NAME_TITLES_SPACES", SPACE)
        extracted = {"entities": [{"name": "Mestre Bimba", "description": "a"},
                                  {"name": "Mestre Pastinha", "description": "b"}],
                     "concepts": []}
        result, _client, calls = run(extracted)
        assert len(calls["relations"]) == 1
        assert result["relations_created"] == 1


class TestResolveEntityStripTitles:
    def _client(self, name):
        return FakeClient([(name, "wiki_entity")])

    def test_default_does_not_match_across_titles(self):
        out = ingest.resolve_entity(self._client("Mestre Moraes"), SPACE, "wiki_entity", "Moraes")
        assert out == {"action": "create"}

    def test_strip_titles_matches_on_equal_stripped_keys(self):
        out = ingest.resolve_entity(
            self._client("Mestre Moraes"), SPACE, "wiki_entity", "Moraes", strip_titles=True
        )
        assert out["action"] == "update" and out["target"]["id"] == "old-0"

    def test_strip_titles_keeps_the_parenthetical_apart(self):
        out = ingest.resolve_entity(
            self._client("Mestre Bimba (Salvador)"), SPACE, "wiki_entity", "Bimba (Rio)",
            strip_titles=True,
        )
        assert out == {"action": "create"}
        out = ingest.resolve_entity(
            self._client("Mestre Bimba (Salvador)"), SPACE, "wiki_entity",
            "Bimba (Salvador)", strip_titles=True,
        )
        assert out["action"] == "update"

    def test_strip_titles_does_not_cross_types(self):
        client = FakeClient([("Mestre Moraes", "wiki_concept")])
        out = ingest.resolve_entity(client, SPACE, "wiki_entity", "Moraes", strip_titles=True)
        assert out == {"action": "create"}

    def test_strip_titles_does_not_merge_different_people(self):
        out = ingest.resolve_entity(
            self._client("Mestre Pastinha"), SPACE, "wiki_entity", "Moraes", strip_titles=True
        )
        assert out == {"action": "create"}


# ---------------------------------------------------------------------------
# remember
# ---------------------------------------------------------------------------


class TestRememberTitleStrip:
    def test_plan_subjects_folds_titled_extraction_into_the_stripped_hint(self, monkeypatch):
        monkeypatch.setenv("WIKI_STRIP_NAME_TITLES_SPACES", SPACE)
        extracted = {"entities": [{"name": "Mestre Bimba", "description": "d"},
                                  {"name": "Salvador", "description": "s"}], "concepts": []}
        subjects, rels, _warnings = remember._plan_subjects(
            extracted, "Bimba was born in Salvador.", "Mestre Bimba", None, None,
            refuse_identifiers=False, strip_titles=True,
        )
        assert [s["name"] for s in subjects] == ["Bimba", "Salvador"]
        assert rels == [{"from": "Bimba", "to": "Salvador", "label": "related"}]

    def test_plan_subjects_default_is_unchanged(self):
        extracted = {"entities": [{"name": "Mestre Bimba", "description": "d"}], "concepts": []}
        subjects, _rels, _ = remember._plan_subjects(
            extracted, "k", "Bimba", None, None, refuse_identifiers=False
        )
        assert [s["name"] for s in subjects] == ["Bimba", "Mestre Bimba"]

    @pytest.fixture
    def apply(self, monkeypatch):
        seen: dict = {"relations": []}
        monkeypatch.setattr(remember, "_create_remember_source", lambda *a, **k: "src-1")
        monkeypatch.setattr(remember, "_resolve_wiki_source_type_tag", lambda *a, **k: ("t", False))
        monkeypatch.setattr(remember, "_resolve_wiki_action_tag", lambda *a, **k: ("t", False))
        monkeypatch.setattr(remember, "_write_wikilog", lambda *a, **k: "log-1")
        monkeypatch.setattr(
            remember, "consolidate",
            lambda **kw: {"consolidated_text": kw["new_facts"], "changed": True,
                          "fact_actions": [], "conflicts": []},
        )

        def fake_rel(client, space_id, relations, kind_by_id):
            seen["relations"].extend(relations)
            return len(relations), []

        monkeypatch.setattr(remember, "_write_bidirectional_relations", fake_rel)

        def go(items, relations=(), client=None):
            client = client or FakeClient()
            result = remember._empty_remember_result()
            remember._apply_batch(
                client, SPACE, items, {"relations": list(relations), "source": None}, result
            )
            return result, client, seen

        return go

    def test_listed_space_creates_the_bare_name(self, apply, monkeypatch):
        monkeypatch.setenv("WIKI_STRIP_NAME_TITLES_SPACES", SPACE)
        result, client, _ = apply([{"name": "Mestre Bimba", "kind": "entity", "facts": "f"}])
        assert [c["name"] for c in client.created] == ["Bimba"]
        assert result["objects"][0]["title"] == "Bimba"

    def test_listed_space_finds_an_existing_titled_object(self, apply, monkeypatch):
        monkeypatch.setenv("WIKI_STRIP_NAME_TITLES_SPACES", SPACE)
        client = FakeClient([("Mestre Bimba", "wiki_entity")])
        result, client, _ = apply([{"name": "Bimba", "kind": "entity", "facts": "f"}], client=client)
        assert client.created == []
        assert result["objects"][0]["object_id"] == "old-0"
        assert result["objects"][0]["action"] == "updated"

    def test_listed_space_finds_an_existing_bare_object_for_a_titled_name(self, apply, monkeypatch):
        monkeypatch.setenv("WIKI_STRIP_NAME_TITLES_SPACES", SPACE)
        client = FakeClient([("Bimba", "wiki_entity")])
        result, client, _ = apply(
            [{"name": "Mestre Bimba", "kind": "entity", "facts": "f"}], client=client
        )
        assert client.created == []
        assert result["objects"][0]["object_id"] == "old-0"

    def test_unlisted_space_unchanged(self, apply):
        client = FakeClient([("Mestre Bimba", "wiki_entity")])
        _result, client, _ = apply([{"name": "Bimba", "kind": "entity", "facts": "f"}], client=client)
        assert [c["name"] for c in client.created] == ["Bimba"]

    def test_relation_endpoints_are_stripped(self, apply, monkeypatch):
        monkeypatch.setenv("WIKI_STRIP_NAME_TITLES_SPACES", SPACE)
        result, client, seen = apply(
            [{"name": "Mestre Bimba", "kind": "entity", "facts": "f"},
             {"name": "Salvador", "kind": "entity", "facts": "s"}],
            relations=[{"from": "Mestre Bimba", "to": "Salvador", "label": "born_in"}],
        )
        ids = {c["name"]: c["id"] for c in client.created}
        assert seen["relations"] == [(ids["Bimba"], ids["Salvador"], "born_in")]
        assert not any(w.startswith("relation_endpoint_unresolved") for w in result["warnings"])

    def test_existing_endpoint_lookup_strips_in_a_listed_space(self, monkeypatch):
        monkeypatch.setenv("WIKI_STRIP_NAME_TITLES_SPACES", SPACE)
        client = FakeClient([("Mestre Bimba", "wiki_entity")])
        name_to_id, kind_by_id = {}, {}
        got = remember._resolve_existing_endpoint(
            client, SPACE, "Bimba", name_to_id, kind_by_id, strip_titles=True
        )
        assert got == "old-0"

    def test_existing_endpoint_lookup_unchanged_in_an_unlisted_space(self):
        client = FakeClient([("Mestre Bimba", "wiki_entity")])
        got = remember._resolve_existing_endpoint(client, SPACE, "Bimba", {}, {}, strip_titles=False)
        assert got is None
