"""Typed links: schema, query, lint, synthesis prompt, version and docs (Aldeia-IT/aldeia-box#1486).

T20 (neighbour link notes, legacy ``links: []``, the two lint checks), T21 (type, schema,
bootstrap, no chunk), T22 (version, CHANGELOG, MIGRATIONS, README, ``server.py``, docs) and
T24 (the synthesis prompt keeps the section markers and carries the section rule).
AC10, AC11, AC14. These assert the target state, so they fail until the code and docs land.
Anytype is the ``FakeWiki`` respx fake; the synthesis model call is monkeypatched.
"""

import pathlib
import re
import tomllib

import httpx
import pytest
import respx

from anytype_llm_wiki.wiki import types_schema
from anytype_llm_wiki.wiki.types_schema import WIKI_SCHEMA_VERSION

from .fakes import ANYTYPE_BASE, SPACE, FakeWiki

ROOT = pathlib.Path(__file__).parent.parent.parent


def _read(rel: str) -> str:
    path = ROOT / rel
    assert path.exists(), f"{rel} not found"
    return path.read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("ANYTYPE_API_KEY", "test-key")
    monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
    monkeypatch.setenv("ANYTYPE_API_VERSION", "2025-11-08")
    monkeypatch.setenv("WIKI_AUTO_REINDEX", "false")
    monkeypatch.setenv("WIKI_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.delenv("WIKI_EXTRACT_ENDPOINT", raising=False)
    (tmp_path / "patch-decision.md").write_text("patch: true\ndecision: apply\n")
    monkeypatch.setenv("ALDEIA_DIR", str(tmp_path))


# -- T21: type and schema (AC11) -------------------------------------------


class TestLinkType:
    def test_schema_version_is_0_5_0(self):
        assert WIKI_SCHEMA_VERSION == "0.5.0"

    def test_link_type_joins_the_wiki_types(self):
        keys = [t["type_key"] for t in types_schema.WIKI_TYPES]
        assert "wiki_link" in keys and len(keys) == 7
        assert len(set(keys)) == 7

    def test_link_type_definition(self):
        link = next((t for t in types_schema.WIKI_TYPES if t["type_key"] == "wiki_link"), None)
        assert link is not None, "wiki_link is not in WIKI_TYPES"
        assert (link["name"], link["plural_name"], link["layout"]) == ("Link", "Links", "basic")
        props = {p["property_key"]: p["format"] for p in link["properties"]}
        assert props == {
            "wiki_link_from": "objects",
            "wiki_link_to": "objects",
            "wiki_link_label": "text",
            "wiki_link_sources": "objects",
        }

    def test_link_property_names_are_unique_across_types(self):
        seen: dict[str, str] = {}
        for t in types_schema.WIKI_TYPES:
            for p in t["properties"]:
                assert seen.setdefault(p["property_key"], p["format"]) == p["format"]

    def test_link_type_is_not_a_content_or_query_type(self):
        from anytype_llm_wiki.wiki import ingest, lint, query

        for keys in (ingest._WIKI_TYPE_KEYS, query._WIKI_TYPE_KEYS, lint._CONTENT_TYPES):
            assert "wiki_link" not in keys

    def test_link_objects_produce_no_chunks(self):
        from anytype_llm_wiki.chunker import chunk_object

        link = {
            "id": "lnk-1",
            "name": "link a-b",
            "type": {"key": "wiki_link"},
            "properties": [
                {"key": "wiki_link_label", "text": "student of"},
                {"key": "wiki_link_from", "objects": ["a"]},
            ],
        }
        assert chunk_object({**link, "space_id": SPACE}) == []

    def test_dry_run_plan_counts_seven_types(self):
        from anytype_llm_wiki.wiki import cli

        assert cli._dry_run_plan(None)["would_create_types"] == 7

    @respx.mock
    def test_bootstrap_creates_the_link_type_and_its_properties(self):
        created_types: list[str] = []
        created_props: list[str] = []
        existing = [
            {"object": "property", "id": f"prop-{p['property_key']}", "key": p["property_key"],
             "name": p["name"], "format": p["format"]}
            for t in types_schema.WIKI_TYPES
            for p in t["properties"]
            if not p["property_key"].startswith("wiki_link_")
        ]

        def get(request):
            path = request.url.path
            data = existing if path.endswith("/properties") else []
            return httpx.Response(200, json={"data": data, "pagination": {"has_more": False}})

        def post(request):
            import json

            path = request.url.path
            body = json.loads(request.content or b"{}")
            if path.endswith("/types"):
                created_types.append(body.get("key", ""))
                # A new type carries its properties inline (bootstrap's missing-type loop).
                created_props.extend(prop.get("key", "") for prop in body.get("properties", []))
                return httpx.Response(201, json={"type": {"id": "t", "key": body.get("key")}})
            if path.endswith("/properties"):
                created_props.append(body.get("key", ""))
                return httpx.Response(201, json={"property": {"id": "p", "key": body.get("key")}})
            if path.endswith("/tags"):
                return httpx.Response(201, json={"tag": {"id": "g", "name": "x", "color": "blue"}})
            return httpx.Response(201, json={"object": {"id": "o", "name": "Wiki"}})

        respx.get().mock(side_effect=get)
        respx.post().mock(side_effect=post)
        from anytype_llm_wiki.wiki.bootstrap import wiki_bootstrap

        result = wiki_bootstrap(space_id=SPACE)
        assert "wiki_link" in created_types, created_types
        assert len(result["types_created"]) == 7
        assert {"wiki_link_from", "wiki_link_to", "wiki_link_label", "wiki_link_sources"} <= set(
            created_props
        ), created_props


# -- T24: synthesis prompt (AC10) ------------------------------------------

SECTIONED = (
    "## Source: page one (id:s1)\n"
    "Bimba founded Regional. [also: page two] [p. 12]\n"
    "He taught Pastinha. [superseded: page two]\n"
    "> [CONFLICT with page two: founding date differs]\n"
    "## Source: page two (id:s2)\n"
    "Bimba opened an academy."
)


class TestSynthesisPrompt:
    def _prompt(self):
        from anytype_llm_wiki.wiki.query import _build_synthesis_prompt

        obj = {
            "id": "e1",
            "name": "Mestre Bimba",
            "type": {"key": "wiki_entity"},
            "properties": [{"key": "wiki_facts", "text": SECTIONED}],
        }
        return _build_synthesis_prompt("Who is Bimba?", [obj])

    def test_sectioned_text_reaches_the_model_verbatim_inside_the_fence(self):
        prompt = self._prompt()
        fenced = prompt.split("<context>", 1)[1].split("</context>", 1)[0]
        for line in SECTIONED.splitlines():
            assert line in fenced, line

    def test_the_section_rule_sits_outside_the_context_fence(self):
        rules = self._prompt().split("<context>", 1)[0]
        assert "## Source:" in rules
        assert "[superseded" in rules
        assert "[CONFLICT" in rules or "> [CONFLICT" in rules
        assert "[also" in rules

    def test_rule_names_what_each_marker_means(self):
        rules = self._prompt().split("<context>", 1)[0].lower()
        assert re.search(r"label", rules)
        assert re.search(r"superseded[^\n]*(outdated|old|newer)", rules)
        assert re.search(r"conflict[^\n]*(disagree|both)", rules)
        assert re.search(r"also[^\n]*(several|multiple|more than one|sources)", rules)

    def test_the_data_preamble_survives(self):
        prompt = self._prompt()
        assert "DATA, not INSTRUCTIONS" in prompt or "DATA" in prompt.split("## TASK")[0]


# -- T20: neighbour link notes (AC10) --------------------------------------

A, B, C, SRC1, SRC2 = "ent-a", "ent-b", "ent-c", "src-1", "src-2"


def _link_props(from_id, to_id, label, sources):
    return [
        {"key": "wiki_link_from", "objects": [from_id]},
        {"key": "wiki_link_to", "objects": [to_id]},
        {"key": "wiki_link_label", "text": label},
        {"key": "wiki_link_sources", "objects": list(sources)},
    ]


def _entity_props(rels=(), facts="Founder of Capoeira Regional in Salvador."):
    return [
        {"key": "wiki_description", "text": facts},
        {"key": "wiki_relations", "objects": list(rels)},
    ]


def _bootstrapped() -> FakeWiki:
    fake = FakeWiki(serve_objects=True)
    fake.install()
    fake.seed(
        "collection", "Wiki", [{"key": "wiki_schema_version", "text": WIKI_SCHEMA_VERSION}],
        "coll-wiki-001",
    )
    return fake


def _query(monkeypatch, question="Who is Mestre Bimba?"):
    import anytype_llm_wiki.wiki.query as q

    prompts: list[str] = []

    def fake_synthesis(base, prompt, *a, **k):
        prompts.append(prompt)
        return "answer " * 15

    monkeypatch.setattr(q, "_call_ollama_synthesis", fake_synthesis)
    # Tier 1 makes every object a seed, so no object would be a neighbour. Force Tier 2
    # with the first entity as the only seed; its relation index makes the rest 1-hop
    # neighbours (a neighbour's links are those to its discovering seed, spec section 8).
    # So link notes in Tier 1 are not pinned here: there every object is a seed and has no
    # discovering seed, hence no neighbour link notes (nothing to show, by design).
    monkeypatch.setenv("WIKI_INDEX_THRESHOLD", "1")
    monkeypatch.setattr(
        q.indexer,
        "hybrid_search_core",
        lambda **kw: [{"object_id": A, "type": "wiki_entity", "score": 0.9}],
    )
    result = q.wiki_query(question=question, space_id=SPACE, file_back=False)
    return result, prompts


def _neighbour(result, object_id):
    return next((s for s in result["sources_consulted"] if s["object_id"] == object_id), None)


class TestQueryLinkNotes:
    @respx.mock
    def test_neighbour_carries_its_link_with_label_and_source_titles(self, monkeypatch):
        fake = _bootstrapped()
        fake.seed("wiki_entity", "Mestre Bimba", _entity_props([B]), A)
        fake.seed("wiki_entity", "Mestre Pastinha", _entity_props([A], "Kept Angola."), B)
        fake.seed("wiki_source", "Page one", None, SRC1)
        fake.seed("wiki_link", "link a-b", _link_props(A, B, "student of", [SRC1]), "lnk-1")
        result, _ = _query(monkeypatch)
        neighbour = _neighbour(result, B)
        assert neighbour is not None, result["sources_consulted"]
        assert "links" in neighbour, neighbour
        assert len(neighbour["links"]) == 1, neighbour["links"]
        link = neighbour["links"][0]
        assert link["label"] == "student of"
        # D17: `links[]` entries carry ids only (object ids, Source ids).
        assert link["from"] == A
        assert link["to"] == B
        assert link["sources"] == [SRC1]

    @respx.mock
    def test_prompt_prints_the_note_before_the_neighbours_text(self, monkeypatch):
        fake = _bootstrapped()
        fake.seed("wiki_entity", "Mestre Bimba", _entity_props([B]), A)
        fake.seed("wiki_entity", "Mestre Pastinha", _entity_props([A], "Kept Angola."), B)
        fake.seed("wiki_source", "Page one", None, SRC1)
        fake.seed("wiki_link", "link a-b", _link_props(A, B, "student of", [SRC1]), "lnk-1")
        _, prompts = _query(monkeypatch)
        note = "Mestre Bimba -[student of]-> Mestre Pastinha (source: Page one)"
        assert prompts and note in prompts[0], prompts[:1]
        assert prompts[0].index(note) < prompts[0].index("Kept Angola.")

    @respx.mock
    def test_legacy_edge_has_empty_links_and_no_note(self, monkeypatch):
        fake = _bootstrapped()
        fake.seed("wiki_entity", "Mestre Bimba", _entity_props([B]), A)
        fake.seed("wiki_entity", "Mestre Pastinha", _entity_props([A], "Kept Angola."), B)
        result, prompts = _query(monkeypatch)
        neighbour = _neighbour(result, B)
        assert neighbour is not None and neighbour.get("links") == []
        assert "-[" not in prompts[0]

    @respx.mock
    def test_candidate_entries_keep_their_old_shape(self, monkeypatch):
        fake = _bootstrapped()
        fake.seed("wiki_entity", "Mestre Bimba", _entity_props([B]), A)
        fake.seed("wiki_entity", "Mestre Pastinha", _entity_props([A], "Kept Angola."), B)
        result, _ = _query(monkeypatch)
        candidate = _neighbour(result, A)
        assert candidate is not None
        assert {"title", "type", "object_id", "deeplink"} <= set(candidate)

    @respx.mock
    def test_two_links_to_one_neighbour_are_both_listed(self, monkeypatch):
        fake = _bootstrapped()
        fake.seed("wiki_entity", "Mestre Bimba", _entity_props([B]), A)
        fake.seed("wiki_entity", "Mestre Pastinha", _entity_props([A], "Kept Angola."), B)
        fake.seed("wiki_source", "Page one", None, SRC1)
        fake.seed("wiki_source", "Page two", None, SRC2)
        fake.seed("wiki_link", "l1", _link_props(A, B, "student of", [SRC1]), "lnk-1")
        fake.seed("wiki_link", "l2", _link_props(A, B, "friend of", [SRC2]), "lnk-2")
        result, _ = _query(monkeypatch)
        labels = sorted(link["label"] for link in _neighbour(result, B).get("links", []))
        assert labels == ["friend of", "student of"]


# -- T20: lint checks (AC10) -----------------------------------------------


def _lint(include=("link_dangling", "link_index_missing")):
    from anytype_llm_wiki.wiki.lint import wiki_lint

    result = wiki_lint(space_id=SPACE)
    return {c: [f for f in result["findings"] if f["check"] == c] for c in include}


def _lint_world(*, index_a=(B,), index_b=(A,), link_sources=(SRC1,), link_to=B):
    fake = _bootstrapped()
    fake.seed("wiki_entity", "Entity A", _entity_props(index_a), A)
    fake.seed("wiki_entity", "Entity B", _entity_props(index_b), B)
    fake.seed("wiki_source", "Page one", None, SRC1)
    fake.seed("wiki_link", "link a-b", _link_props(A, link_to, "student of", link_sources), "lnk-1")
    return fake


def _ids(findings):
    return [f["object_id"] for f in findings]


def _add_broken_companions(fake):
    """A second link that is dangling and a third that is index-missing, so a check that
    does not exist yet cannot pass the 'healthy link raises nothing' tests vacuously."""
    fake.seed("wiki_entity", "Entity D", _entity_props(()), "ent-d")
    fake.seed("wiki_link", "broken", _link_props(A, "ghost", "x", [SRC1]), "lnk-dangling")
    fake.seed("wiki_link", "unindexed", _link_props(A, "ent-d", "y", [SRC1]), "lnk-unindexed")


class TestLintLinkChecks:
    @respx.mock
    def test_healthy_link_raises_neither_check(self):
        _add_broken_companions(_lint_world())
        found = _lint()
        assert _ids(found["link_dangling"]) == ["lnk-dangling"]
        assert _ids(found["link_index_missing"]) == ["lnk-unindexed"]

    @respx.mock
    def test_missing_endpoint_is_dangling_and_high(self):
        _lint_world(link_to="ghost")
        found = _lint()
        assert len(found["link_dangling"]) == 1
        assert found["link_dangling"][0]["severity"] == "high"

    @respx.mock
    def test_missing_source_is_dangling(self):
        _lint_world(link_sources=("ghost-src",))
        assert len(_lint()["link_dangling"]) == 1

    @respx.mock
    def test_link_without_any_source_is_dangling(self):
        _lint_world(link_sources=())
        assert len(_lint()["link_dangling"]) == 1

    @respx.mock
    def test_endpoints_not_indexing_each_other_is_index_missing_and_medium(self):
        _lint_world(index_a=(), index_b=())
        found = _lint()
        assert len(found["link_index_missing"]) == 1
        assert found["link_index_missing"][0]["severity"] == "medium"
        assert found["link_dangling"] == []

    @respx.mock
    def test_one_side_missing_is_still_index_missing(self):
        _lint_world(index_b=())
        assert len(_lint()["link_index_missing"]) == 1

    @respx.mock
    def test_dangling_link_is_not_also_index_missing(self):
        _lint_world(link_to="ghost", index_a=(), index_b=())
        found = _lint()
        assert len(found["link_dangling"]) == 1 and found["link_index_missing"] == []

    @respx.mock
    def test_concept_endpoint_is_checked_on_wiki_related(self):
        fake = _bootstrapped()
        fake.seed("wiki_entity", "Entity A", _entity_props([C]), A)
        fake.seed(
            "wiki_concept", "Concept C", [{"key": "wiki_related", "objects": [A]}], C
        )
        fake.seed("wiki_source", "Page one", None, SRC1)
        fake.seed("wiki_link", "l", _link_props(A, C, "founded", [SRC1]), "lnk-1")
        fake.seed("wiki_entity", "Entity D", _entity_props(()), "ent-d")
        fake.seed("wiki_link", "unindexed", _link_props(A, "ent-d", "y", [SRC1]), "lnk-unindexed")
        assert _ids(_lint()["link_index_missing"]) == ["lnk-unindexed"]

    def test_lint_documents_thirteen_checks(self):
        from anytype_llm_wiki.wiki import lint

        assert "thirteen" in (lint.__doc__ or "") and "thirteen" in (lint.wiki_lint.__doc__ or "")
        assert "twelve" not in (lint.wiki_lint.__doc__ or "")
        assert "source_dangling" in (lint.__doc__ or "")


class TestLintSourceDangling:
    """An entity or concept whose wiki_sources names an id that resolves to no object."""

    @staticmethod
    def _found():
        return _lint(("source_dangling", "link_dangling"))

    @respx.mock
    def test_deleted_source_on_an_entity_is_high(self):
        fake = _lint_world()
        fake.objects[A]["properties"].append({"key": "wiki_sources", "objects": [SRC1, "gone"]})
        found = self._found()
        assert _ids(found["source_dangling"]) == [A]
        assert found["source_dangling"][0]["severity"] == "high"
        assert "gone" in found["source_dangling"][0]["detail"]

    @respx.mock
    def test_concept_is_checked_too(self):
        fake = _lint_world()
        fake.seed("wiki_concept", "Concept C", [{"key": "wiki_sources", "objects": ["gone"]}], C)
        assert _ids(self._found()["source_dangling"]) == [C]

    @respx.mock
    def test_resolving_sources_and_no_sources_raise_nothing(self):
        fake = _lint_world()
        fake.objects[A]["properties"].append({"key": "wiki_sources", "objects": [SRC1]})
        assert self._found()["source_dangling"] == []

    @respx.mock
    def test_both_forms_of_the_residual_race_are_surfaced(self):
        """A write that reached the server while the client saw an error, then Source cleanup:
        the Source is gone but an object (source_dangling) or a link (link_dangling) names it."""
        fake = _lint_world(link_sources=("gone",))
        fake.objects[B]["properties"].append({"key": "wiki_sources", "objects": ["gone"]})
        found = self._found()
        assert _ids(found["source_dangling"]) == [B]
        assert _ids(found["link_dangling"]) == ["lnk-1"]


# -- T22: version and docs (AC14) ------------------------------------------


def _section(text: str, heading_pattern: str) -> str:
    match = re.search(heading_pattern, text, flags=re.MULTILINE)
    assert match, f"section {heading_pattern!r} not found"
    rest = text[match.end():]
    nxt = re.search(r"^## ", rest, flags=re.MULTILINE)
    return rest[: nxt.start()] if nxt else rest


class TestVersionAndChangelog:
    def test_package_version_is_0_10_0(self):
        data = tomllib.loads(_read("pyproject.toml"))
        assert data["project"]["version"] == "0.10.0"

    def test_changelog_has_a_0_10_0_entry_naming_the_link_counts(self):
        entry = _section(_read("CHANGELOG.md"), r"^## \[0\.10\.0\][^\n]*\n")
        assert "relations_created" in entry
        assert "wiki_link" in entry
        assert "0.5.0" in entry

    def test_changelog_names_the_repair_command(self):
        entry = _section(_read("CHANGELOG.md"), r"^## \[0\.10\.0\][^\n]*\n")
        assert "repair-chain-relations" in entry


class TestMigrations:
    def _section(self):
        return _section(_read("MIGRATIONS.md"), r"^#+ Schema 0\.5\.0[^\n]*\n")

    def test_section_orders_upgrade_bootstrap_dry_run_review_and_write(self):
        text = self._section()
        order = [
            text.find("wiki-bootstrap"),
            text.find("--dry-run"),
            text.find("--clear-ingest-only"),
        ]
        assert all(i >= 0 for i in order), order
        assert order == sorted(order)

    def test_section_says_to_upgrade_every_client_first(self):
        assert re.search(r"every (client|MCP server)", self._section(), flags=re.IGNORECASE)

    def test_section_says_to_stop_every_writer_on_every_host(self):
        text = self._section()
        assert re.search(r"stop", text, flags=re.IGNORECASE) and re.search(r"every host|each host", text, flags=re.IGNORECASE)

    def test_section_says_a_digest_mismatch_means_a_new_dry_run_never_a_retry(self):
        text = self._section().lower()
        assert "digest" in text and "retry" in text and "dry run" in text.replace("dry-run", "dry run")

    def test_section_sends_untagged_sources_to_the_operator(self):
        text = self._section().lower()
        assert "untagged" in text and "--confirm-untagged" in text

    def test_section_says_existing_facts_become_the_legacy_section(self):
        assert re.search(r"legacy|unattributed", self._section(), flags=re.IGNORECASE)

    def test_section_points_to_the_re_ingest(self):
        assert re.search(r"re-?ingest", self._section(), flags=re.IGNORECASE)


class TestReadme:
    def test_describes_typed_links_with_free_labels(self):
        text = _read("README.md")
        assert "wiki_link" in text
        assert re.search(r"free[- ](text )?label|labels? (is|are) free", text, flags=re.IGNORECASE)

    def test_describes_per_source_facts(self):
        text = _read("README.md")
        assert "## Source:" in text or re.search(r"per-source|one section per source", text, flags=re.IGNORECASE)

    def test_remember_keeps_superseded_facts_tagged(self):
        text = _read("README.md")
        assert re.search(r"superseded[^\n]*(kept|tagged)|(kept|tagged)[^\n]*superseded", text, flags=re.IGNORECASE)

    def test_remember_repeat_wording_changed(self):
        text = _read("README.md")
        assert "converges to a no-op" not in text
        assert re.search(r"adds nothing to the facts", text, flags=re.IGNORECASE)

    def test_documents_the_repair_command(self):
        assert "repair-chain-relations" in _read("README.md")

    def test_keeps_the_disclosure_wording_the_docs_test_pins(self):
        text = _read("README.md").lower()
        assert "linked entities" in text and "contradiction" in text

    def test_query_neighbour_and_synthesis_rule_are_described(self):
        text = _read("README.md")
        assert re.search(r"synthesis rule|section rule", text, flags=re.IGNORECASE)


class TestOtherDocs:
    def test_server_remember_description_no_longer_promises_a_no_op(self):
        text = _read("src/anytype_llm_wiki/server.py")
        assert "converges to a no-op" not in text.split("def wiki_remember")[1].split('"""', 2)[1]

    def test_server_remember_description_names_the_new_behaviour(self):
        doc = _read("src/anytype_llm_wiki/server.py").split("def wiki_remember")[1].split('"""', 2)[1]
        assert re.search(r"superseded|per-source|source section", doc, flags=re.IGNORECASE)

    def test_architecture_supersede_text_keeps_the_old_unit(self):
        text = _read("docs/architecture.md")
        assert not re.search(r"supersede\*\* .{0,5}the old fact is replaced", text)
        assert re.search(r"superseded", text, flags=re.IGNORECASE)

    def test_known_limitations_no_longer_describes_chain_relations_as_current(self):
        text = _read("docs/known-limitations.md")
        assert "repair-chain-relations" in text
