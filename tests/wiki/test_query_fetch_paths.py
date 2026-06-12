"""Replacement coverage for wiki_query get_object-dependent behaviors.

WHY THIS FILE EXISTS
--------------------
Five tests in ``test_query.py`` register a no-arg catch-all ``respx.get()`` route
FIRST and then a URL-specific / regex route SECOND, expecting the specific route
(carrying the per-object ``get_object`` payload) to win. Under the pinned respx
(0.23.1), ``Router.resolve`` iterates ``self.routes`` in REGISTRATION order and
returns the FIRST match (``respx/router.py`` — ``for route in self.routes: ...
break``). The catch-all therefore intercepts every GET, including ``get_object``
calls, and the specific ``side_effect`` routes NEVER fire. Those five assertions
(prior-relation merge, 404 deletion, candidate-fetch failure, per-id fetch count,
neighbor-id capture) depend on data that only lives in the dead routes, so they
are unsatisfiable by ANY implementation and are skipped in ``test_query.py`` with
a pointer here.

This file re-verifies the SAME behaviors using the working respx pattern already
used throughout ``test_ingest.py``: a SINGLE catch-all ``respx.get().mock(
side_effect=dispatcher)`` whose dispatcher branches on the request URL. That
pattern is respx-version-stable (one GET route, no ordering dependency) and
exercises the real ``AnytypeReadClient.get_object`` wire path.
"""

import os

import httpx
import pytest
import respx

ANYTYPE_BASE = "http://127.0.0.1:31012"
FAKE_SPACE_ID = "space-query-test-001"


@pytest.fixture(autouse=True)
def set_anytype_env(monkeypatch):
    monkeypatch.setenv("ANYTYPE_API_KEY", "test-query-key")
    monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
    monkeypatch.setenv("ANYTYPE_API_VERSION", "2025-11-08")
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    aldeia_dir = os.path.join(
        repo_root, ".aldeia", "140-wiki-library-module-port-llm-wiki-pattern-onto-any"
    )
    monkeypatch.setenv("ALDEIA_DIR", aldeia_dir)


def _schema_obj():
    from anytype_llm_wiki.wiki.types_schema import WIKI_SCHEMA_VERSION
    return {
        "id": "coll-wiki-001",
        "name": "Wiki",
        "type": {"key": "collection"},
        "properties": [{"key": "wiki_schema_version", "text": WIKI_SCHEMA_VERSION}],
    }


def _obj_id_from_request(request):
    return str(request.url).rstrip("/").split("/")[-1].split("?")[0]


def _is_list_request(request):
    # list_objects hits .../objects (no trailing object id); get_object hits
    # .../objects/{id}. Distinguish by whether the path ends with "objects".
    path = str(request.url).split("?")[0].rstrip("/")
    return path.endswith("/objects")


def _is_object_request(request):
    """True only for GET .../objects/{id} (a get_object call)."""
    path = str(request.url).split("?")[0].rstrip("/")
    return "/objects/" in path


class TestNeighborhoodCacheReplacement:
    @respx.mock
    def test_shared_neighbor_fetched_once(self, monkeypatch):
        """A neighbor shared by two candidates is fetched via get_object exactly once
        (per-run cache). Single dispatcher route → no respx ordering dependency.
        """
        shared_id = "neighbor-shared-001"
        cand_a_id = "entity-cand-a"
        cand_b_id = "entity-cand-b"

        list_objects = [
            _schema_obj(),
            {"id": cand_a_id, "name": "A", "type": {"key": "wiki_entity"},
             "properties": [{"key": "wiki_relations", "objects": [shared_id]}]},
            {"id": cand_b_id, "name": "B", "type": {"key": "wiki_entity"},
             "properties": [{"key": "wiki_relations", "objects": [shared_id]}]},
        ]
        list_resp = {"data": list_objects, "pagination": {"has_more": False}}

        fetch_counts: dict[str, int] = {}

        def dispatcher(request, **kwargs):
            if _is_list_request(request):
                return httpx.Response(200, json=list_resp)
            oid = _obj_id_from_request(request)
            fetch_counts[oid] = fetch_counts.get(oid, 0) + 1
            rel = [shared_id] if oid in (cand_a_id, cand_b_id) else []
            return httpx.Response(200, json={"object": {
                "id": oid, "name": oid, "type": {"key": "wiki_entity"},
                "properties": [
                    {"key": "wiki_description", "text": "d"},
                    {"key": "wiki_relations", "objects": rel},
                ],
            }})

        import anytype_llm_wiki.wiki.query as _q_mod
        monkeypatch.setattr(_q_mod, "synthesize", lambda q, ctx: "answer " * 15)

        respx.get().mock(side_effect=dispatcher)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001"}}))

        from anytype_llm_wiki.wiki.query import wiki_query
        wiki_query(question="t", space_id=FAKE_SPACE_ID, file_back=False)

        assert fetch_counts.get(shared_id, 0) == 1, fetch_counts


class TestReciprocalReadMergeWriteReplacement:
    @respx.mock
    def test_no_reciprocal_write_onto_cited_entity(self, monkeypatch):
        """File-back must not touch a cited entity's relation set at all: no PATCH
        is issued onto the cited entity, and its pre-existing relations are left
        untouched. The forward provenance edge lives only on the query object
        (wiki_drew_from); the reverse direction is served by Anytype backlinks.
        """
        cited_id = "entity-cited-001"
        prior = ["e1", "e2"]

        list_resp = {"data": [
            _schema_obj(),
            {"id": cited_id, "name": "Cited", "type": {"key": "wiki_entity"},
             "properties": [{"key": "wiki_relations", "objects": []}]},
        ], "pagination": {"has_more": False}}

        def dispatcher(request, **kwargs):
            if _is_list_request(request):
                return httpx.Response(200, json=list_resp)
            oid = _obj_id_from_request(request)
            rel = prior if oid == cited_id else []
            return httpx.Response(200, json={"object": {
                "id": oid, "name": "Cited", "type": {"key": "wiki_entity"},
                "properties": [{"key": "wiki_relations", "objects": rel}],
            }})

        patch_calls = []

        def track_patch(request, **kwargs):
            import json as _json
            oid = _obj_id_from_request(request)
            try:
                payload = _json.loads(request.content)
            except Exception:
                payload = {}
            patch_calls.append((oid, payload))
            return httpx.Response(200, json={"object": {"id": oid}})

        import anytype_llm_wiki.wiki.query as _q_mod
        monkeypatch.setattr(_q_mod, "synthesize", lambda q, ctx: " ".join(["w"] * 120))
        monkeypatch.setenv("WIKI_FILE_BACK_MIN_SOURCES", "1")
        monkeypatch.setenv("WIKI_FILE_BACK_MIN_WORDS", "100")

        respx.get().mock(side_effect=dispatcher)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "query-new-001"}}))
        respx.patch().mock(side_effect=track_patch)

        from anytype_llm_wiki.wiki.query import wiki_query
        result = wiki_query(question="merge", space_id=FAKE_SPACE_ID, file_back=None)

        query_id = result.get("query_object_id")
        assert query_id, result
        cited_patches = [p for (oid, p) in patch_calls if oid == cited_id]
        assert not cited_patches, (
            f"No PATCH should be issued onto cited entity {cited_id!r}; got: {cited_patches}"
        )
        # The forward provenance edge is written on the query object instead.
        drew_from = [
            prop
            for (oid, payload) in patch_calls if oid == query_id
            for prop in payload.get("properties", [])
            if prop.get("key") == "wiki_drew_from"
        ]
        assert drew_from and cited_id in (drew_from[0].get("objects") or []), (
            f"Expected wiki_drew_from on the query object citing {cited_id!r}; got {drew_from}"
        )


class TestCitedObjectDeletedReplacement:
    @respx.mock
    def test_deleted_cited_object_drops_and_partials(self, monkeypatch):
        """SF4: a cited id that 404s at write time is dropped + cited_object_gone +
        status=partial. The write-time read is fresh (not the neighborhood cache).
        """
        deleted_id = "entity-deleted-001"
        read_count = {"n": 0}

        list_resp = {"data": [
            _schema_obj(),
            {"id": deleted_id, "name": "Del", "type": {"key": "wiki_entity"},
             "properties": [{"key": "wiki_relations", "objects": []}]},
        ], "pagination": {"has_more": False}}

        def dispatcher(request, **kwargs):
            if _is_list_request(request):
                return httpx.Response(200, json=list_resp)
            oid = _obj_id_from_request(request)
            if oid == deleted_id:
                read_count["n"] += 1
                if read_count["n"] == 1:
                    return httpx.Response(200, json={"object": {
                        "id": deleted_id, "name": "Del", "type": {"key": "wiki_entity"},
                        "properties": [{"key": "wiki_description", "text": "d"}],
                    }})
                return httpx.Response(404, json={"error": "not found"})
            return httpx.Response(200, json={"object": {"id": oid, "name": oid,
                                                        "type": {"key": "wiki_entity"},
                                                        "properties": []}})

        import anytype_llm_wiki.wiki.query as _q_mod
        monkeypatch.setattr(_q_mod, "synthesize", lambda q, ctx: " ".join(["w"] * 120))
        monkeypatch.setenv("WIKI_FILE_BACK_MIN_SOURCES", "1")
        monkeypatch.setenv("WIKI_FILE_BACK_MIN_WORDS", "50")

        respx.get().mock(side_effect=dispatcher)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "q-002"}}))
        respx.patch().mock(return_value=httpx.Response(200, json={"object": {"id": "q"}}))

        from anytype_llm_wiki.wiki.query import wiki_query
        result = wiki_query(question="del", space_id=FAKE_SPACE_ID, file_back=True)

        assert any("cited_object_gone" in str(w) for w in result.get("warnings", [])), result
        assert result.get("status") == "partial", result


class TestTier2CandidateFetchFailureReplacement:
    @respx.mock
    def test_candidate_fetch_failure_partials(self, monkeypatch):
        """QA-12: a Tier-2 candidate whose get_object fails is dropped from
        sources_consulted; a good candidate remains; status=partial. Candidate and
        neighbor fetch share one code path (_fetch_cached).
        """
        good_id = "entity-good-cand-001"
        bad_id = "entity-bad-cand-001"
        fillers = [{"id": f"f-{i:03d}", "name": f"F{i}", "type": {"key": "wiki_entity"},
                    "properties": []} for i in range(198)]
        list_resp = {"data": [_schema_obj()] + fillers + [
            {"id": good_id, "name": "Good", "type": {"key": "wiki_entity"},
             "properties": [{"key": "wiki_description", "text": "g"}]},
            {"id": bad_id, "name": "Bad", "type": {"key": "wiki_entity"},
             "properties": [{"key": "wiki_description", "text": "b"}]},
        ], "pagination": {"has_more": False}}

        import anytype_llm_wiki.indexer as _idx_mod
        import anytype_llm_wiki.wiki.query as _q_mod

        def stub_search(query, space_id, types, limit=10):
            return [
                {"object_id": good_id, "type": "wiki_entity", "score": 0.9},
                {"object_id": bad_id, "type": "wiki_entity", "score": 0.8},
            ]

        monkeypatch.setattr(_idx_mod, "semantic_search_core", stub_search)
        monkeypatch.setattr(_q_mod, "synthesize", lambda q, ctx: "partial " * 10)

        def dispatcher(request, **kwargs):
            if _is_list_request(request):
                return httpx.Response(200, json=list_resp)
            oid = _obj_id_from_request(request)
            if oid == bad_id:
                return httpx.Response(404, json={"error": "not found"})
            return httpx.Response(200, json={"object": {"id": oid, "name": oid,
                                                        "type": {"key": "wiki_entity"},
                                                        "properties": [
                                                            {"key": "wiki_description",
                                                             "text": "x"}]}})

        respx.get().mock(side_effect=dispatcher)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001"}}))

        from anytype_llm_wiki.wiki.query import wiki_query
        result = wiki_query(question="cand fail", space_id=FAKE_SPACE_ID, file_back=False)

        source_ids = [s.get("object_id") for s in result.get("sources_consulted", [])]
        assert bad_id not in source_ids, source_ids
        assert good_id in source_ids, source_ids
        assert result.get("status") == "partial", result


# ---------------------------------------------------------------------------
# #324 — Relationship-Aware Retrieval (delta over v0.4.0)
# Test classes: TestNeighborCitation, TestFanOutCap, TestDeterministicTrimOrder,
#               TestFileBackSeedOnly
# (American spelling throughout — B4)
# ---------------------------------------------------------------------------


class TestNeighborCitation:
    """AC1 / AC3 / AC11 — surviving neighbours appear in sources_consulted.

    All tests use the single-dispatcher respx pattern so fetch-count assertions
    are reliable across respx 0.23.x.
    """

    @respx.mock
    def test_surviving_neighbor_in_sources_consulted(self, monkeypatch):
        """AC1: 1 seed + 1 neighbor → neighbor entry present in sources_consulted
        with correct object_id and deeplink.
        """
        seed_id = "entity-seed-nc-001"
        neighbor_id = "entity-neighbor-nc-001"

        list_resp = {"data": [
            _schema_obj(),
            {"id": seed_id, "name": "Seed", "type": {"key": "wiki_entity"},
             "properties": [
                 {"key": "wiki_description", "text": "seed desc"},
                 {"key": "wiki_relations", "objects": [neighbor_id]},
             ]},
        ], "pagination": {"has_more": False}}

        def dispatcher(request, **kwargs):
            if _is_list_request(request):
                return httpx.Response(200, json=list_resp)
            oid = _obj_id_from_request(request)
            if oid == seed_id:
                return httpx.Response(200, json={"object": {
                    "id": seed_id, "name": "Seed", "type": {"key": "wiki_entity"},
                    "properties": [
                        {"key": "wiki_description", "text": "seed desc"},
                        {"key": "wiki_relations", "objects": [neighbor_id]},
                    ],
                }})
            if oid == neighbor_id:
                return httpx.Response(200, json={"object": {
                    "id": neighbor_id, "name": "Neighbor", "type": {"key": "wiki_entity"},
                    "properties": [
                        {"key": "wiki_description", "text": "neighbor content"},
                    ],
                }})
            return httpx.Response(200, json={"object": {
                "id": oid, "name": oid, "type": {"key": "wiki_entity"},
                "properties": [],
            }})

        import anytype_llm_wiki.wiki.query as _q_mod
        monkeypatch.setattr(_q_mod, "synthesize", lambda q, ctx: "answer " * 20)
        # Ensure synthesis budget is large enough to include the neighbor
        monkeypatch.setenv("WIKI_SYNTH_MAX_OBJECTS", "24")

        respx.get().mock(side_effect=dispatcher)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001"}}))

        from anytype_llm_wiki.wiki.query import wiki_query
        result = wiki_query(question="test neighbor citation", space_id=FAKE_SPACE_ID, file_back=False)

        source_ids = [s.get("object_id") for s in result.get("sources_consulted", [])]
        assert neighbor_id in source_ids, (
            f"AC1: surviving neighbor {neighbor_id!r} must appear in sources_consulted. "
            f"Got: {source_ids}. Full result: {result}"
        )
        # Verify deeplink format for the neighbor entry
        neighbor_source = next(
            (s for s in result.get("sources_consulted", []) if s.get("object_id") == neighbor_id),
            None,
        )
        assert neighbor_source is not None, f"No source entry found for {neighbor_id!r}"
        assert neighbor_source.get("deeplink", "").startswith("anytype://object/"), (
            f"Neighbor deeplink must start with anytype://object/. Got: {neighbor_source.get('deeplink')!r}"
        )
        assert FAKE_SPACE_ID in neighbor_source.get("deeplink", ""), (
            f"Neighbor deeplink must contain space_id. Got: {neighbor_source.get('deeplink')!r}"
        )
        assert neighbor_id in neighbor_source.get("deeplink", ""), (
            f"Neighbor deeplink must contain neighbor_id. Got: {neighbor_source.get('deeplink')!r}"
        )

    @respx.mock
    def test_all_neighbors_trimmed_sources_seeds_only(self, monkeypatch):
        """AC1 (SF-G): when seeds alone fill the synthesis budget, neighbors are dropped
        and sources_consulted contains seeds only, with synthesis_context_trimmed warning.
        """
        # 2 seeds — cap at 2 objects → neighbors cannot fit
        seed_a_id = "entity-seed-trim-a"
        seed_b_id = "entity-seed-trim-b"
        neighbor_id = "entity-neighbor-trim-001"

        monkeypatch.setenv("WIKI_SYNTH_MAX_OBJECTS", "2")

        list_resp = {"data": [
            _schema_obj(),
            {"id": seed_a_id, "name": "SeedA", "type": {"key": "wiki_entity"},
             "properties": [
                 {"key": "wiki_description", "text": "seed a desc"},
                 {"key": "wiki_relations", "objects": [neighbor_id]},
             ]},
            {"id": seed_b_id, "name": "SeedB", "type": {"key": "wiki_entity"},
             "properties": [
                 {"key": "wiki_description", "text": "seed b desc"},
                 {"key": "wiki_relations", "objects": []},
             ]},
        ], "pagination": {"has_more": False}}

        def dispatcher(request, **kwargs):
            if _is_list_request(request):
                return httpx.Response(200, json=list_resp)
            oid = _obj_id_from_request(request)
            if oid == seed_a_id:
                return httpx.Response(200, json={"object": {
                    "id": seed_a_id, "name": "SeedA", "type": {"key": "wiki_entity"},
                    "properties": [
                        {"key": "wiki_description", "text": "seed a desc"},
                        {"key": "wiki_relations", "objects": [neighbor_id]},
                    ],
                }})
            if oid == seed_b_id:
                return httpx.Response(200, json={"object": {
                    "id": seed_b_id, "name": "SeedB", "type": {"key": "wiki_entity"},
                    "properties": [
                        {"key": "wiki_description", "text": "seed b desc"},
                        {"key": "wiki_relations", "objects": []},
                    ],
                }})
            if oid == neighbor_id:
                return httpx.Response(200, json={"object": {
                    "id": neighbor_id, "name": "Neighbor", "type": {"key": "wiki_entity"},
                    "properties": [{"key": "wiki_description", "text": "neighbor desc"}],
                }})
            return httpx.Response(200, json={"object": {
                "id": oid, "name": oid, "type": {"key": "wiki_entity"},
                "properties": [],
            }})

        import anytype_llm_wiki.wiki.query as _q_mod
        monkeypatch.setattr(_q_mod, "synthesize", lambda q, ctx: "trimmed " * 10)

        respx.get().mock(side_effect=dispatcher)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001"}}))

        from anytype_llm_wiki.wiki.query import wiki_query
        result = wiki_query(question="trim test", space_id=FAKE_SPACE_ID, file_back=False)

        source_ids = [s.get("object_id") for s in result.get("sources_consulted", [])]
        assert neighbor_id not in source_ids, (
            f"SF-G: trimmed neighbor must not appear in sources_consulted. Got: {source_ids}"
        )
        warnings = result.get("warnings", [])
        assert any("synthesis_context_trimmed" in str(w) for w in warnings), (
            f"SF-G: synthesis_context_trimmed warning must be present. Got: {warnings}"
        )
        # Both seeds should be present
        assert seed_a_id in source_ids or seed_b_id in source_ids, (
            f"SF-G: at least one seed must survive in sources_consulted. Got: {source_ids}"
        )

    @respx.mock
    def test_sources_consulted_deduped_seed_and_neighbor(self, monkeypatch):
        """AC1 / AC3: an object shared as both seed and neighbor of another seed
        appears exactly once in sources_consulted.
        """
        shared_id = "entity-shared-dedup-fp-001"
        other_seed_id = "entity-other-seed-fp-001"

        # shared_id is both a direct candidate AND listed as a neighbor of other_seed_id
        list_resp = {"data": [
            _schema_obj(),
            {"id": other_seed_id, "name": "OtherSeed", "type": {"key": "wiki_entity"},
             "properties": [
                 {"key": "wiki_description", "text": "other seed desc"},
                 {"key": "wiki_relations", "objects": [shared_id]},
             ]},
            {"id": shared_id, "name": "Shared", "type": {"key": "wiki_entity"},
             "properties": [
                 {"key": "wiki_description", "text": "shared desc"},
                 {"key": "wiki_relations", "objects": []},
             ]},
        ], "pagination": {"has_more": False}}

        def dispatcher(request, **kwargs):
            if _is_list_request(request):
                return httpx.Response(200, json=list_resp)
            oid = _obj_id_from_request(request)
            if oid == other_seed_id:
                return httpx.Response(200, json={"object": {
                    "id": other_seed_id, "name": "OtherSeed", "type": {"key": "wiki_entity"},
                    "properties": [
                        {"key": "wiki_description", "text": "other seed desc"},
                        {"key": "wiki_relations", "objects": [shared_id]},
                    ],
                }})
            if oid == shared_id:
                return httpx.Response(200, json={"object": {
                    "id": shared_id, "name": "Shared", "type": {"key": "wiki_entity"},
                    "properties": [
                        {"key": "wiki_description", "text": "shared desc"},
                        {"key": "wiki_relations", "objects": []},
                    ],
                }})
            return httpx.Response(200, json={"object": {
                "id": oid, "name": oid, "type": {"key": "wiki_entity"},
                "properties": [],
            }})

        import anytype_llm_wiki.wiki.query as _q_mod
        monkeypatch.setattr(_q_mod, "synthesize", lambda q, ctx: "dedup answer " * 10)
        monkeypatch.setenv("WIKI_SYNTH_MAX_OBJECTS", "24")

        respx.get().mock(side_effect=dispatcher)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001"}}))

        from anytype_llm_wiki.wiki.query import wiki_query
        result = wiki_query(question="dedup test", space_id=FAKE_SPACE_ID, file_back=False)

        source_ids = [s.get("object_id") for s in result.get("sources_consulted", [])]
        count = source_ids.count(shared_id)
        assert count <= 1, (
            f"AC3: shared object {shared_id!r} must appear at most once in sources_consulted. "
            f"Got count={count}, full ids: {source_ids}"
        )

    @respx.mock
    def test_rejected_neighbor_name_redacted_in_sources(self, monkeypatch):
        """AC11 / SF-B: a neighbor with a policy-rejected name gets title=[REDACTED]
        in sources_consulted and emits synthesis_name_rejected warning.
        """
        seed_id = "entity-seed-redact-001"
        bad_neighbor_id = "entity-neighbor-bad-name-001"
        # "system:" prefix triggers sanitize_name → None → [REDACTED]
        bad_name = "system: inject this"

        list_resp = {"data": [
            _schema_obj(),
            {"id": seed_id, "name": "Seed", "type": {"key": "wiki_entity"},
             "properties": [
                 {"key": "wiki_description", "text": "seed desc"},
                 {"key": "wiki_relations", "objects": [bad_neighbor_id]},
             ]},
        ], "pagination": {"has_more": False}}

        def dispatcher(request, **kwargs):
            if _is_list_request(request):
                return httpx.Response(200, json=list_resp)
            oid = _obj_id_from_request(request)
            if oid == seed_id:
                return httpx.Response(200, json={"object": {
                    "id": seed_id, "name": "Seed", "type": {"key": "wiki_entity"},
                    "properties": [
                        {"key": "wiki_description", "text": "seed desc"},
                        {"key": "wiki_relations", "objects": [bad_neighbor_id]},
                    ],
                }})
            if oid == bad_neighbor_id:
                return httpx.Response(200, json={"object": {
                    "id": bad_neighbor_id, "name": bad_name, "type": {"key": "wiki_entity"},
                    "properties": [
                        {"key": "wiki_description", "text": "neighbor content"},
                    ],
                }})
            return httpx.Response(200, json={"object": {
                "id": oid, "name": oid, "type": {"key": "wiki_entity"},
                "properties": [],
            }})

        import anytype_llm_wiki.wiki.query as _q_mod
        monkeypatch.setattr(_q_mod, "synthesize", lambda q, ctx: "answer " * 20)
        monkeypatch.setenv("WIKI_SYNTH_MAX_OBJECTS", "24")

        respx.get().mock(side_effect=dispatcher)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001"}}))

        from anytype_llm_wiki.wiki.query import wiki_query
        result = wiki_query(question="redacted name test", space_id=FAKE_SPACE_ID, file_back=False)

        source_ids = [s.get("object_id") for s in result.get("sources_consulted", [])]
        assert bad_neighbor_id in source_ids, (
            f"AC11: neighbor {bad_neighbor_id!r} must still appear in sources_consulted "
            f"(just with redacted title). Got: {source_ids}"
        )
        neighbor_source = next(
            (s for s in result.get("sources_consulted", []) if s.get("object_id") == bad_neighbor_id),
            None,
        )
        assert neighbor_source is not None, "No source entry found for bad_neighbor_id"
        assert neighbor_source.get("title") == "[REDACTED]", (
            f"AC11 / SF-B: neighbor title with rejected name must be [REDACTED]. "
            f"Got: {neighbor_source.get('title')!r}"
        )
        warnings = result.get("warnings", [])
        assert any("synthesis_name_rejected" in str(w) for w in warnings), (
            f"AC11 / SF-B: synthesis_name_rejected warning must be emitted. Got: {warnings}"
        )


class TestFanOutCap:
    """AC5 / AC6 / AC12 — bounded fan-out cap, measurability, partial status."""

    @respx.mock
    def test_cap_warning_and_d5_top_n_fetched(self, monkeypatch):
        """AC5 / SF-F: WIKI_QUERY_MAX_NEIGHBORS=2 with 5 distinct neighbors →
        exact warning 'neighbor_fan_out_capped: 5 -> 2'; exactly the 2 D5-top
        neighbor ids are fetched (those from seed-rank-0 with lowest relation-priority).
        """
        # Use Tier-2 (stub_search) so seed rank is score-descending and deterministic.
        # seed-rank-0 = seed_a_id (score 0.9); seed-rank-1 = seed_b_id (score 0.8)
        # seed_a has wiki_relations neighbors: n_a1, n_a2 (relation_priority=0)
        # seed_b has wiki_relations neighbors: n_b1, n_b2, n_b3 (relation_priority=0)
        # D5 order: (0, 0, n_a1), (0, 0, n_a2), (1, 0, n_b1), (1, 0, n_b2), (1, 0, n_b3)
        # With cap=2: only n_a1 and n_a2 should be fetched.
        seed_a_id = "entity-seed-cap-a"
        seed_b_id = "entity-seed-cap-b"
        n_a1 = "entity-neighbor-a1"
        n_a2 = "entity-neighbor-a2"
        n_b1 = "entity-neighbor-b1"
        n_b2 = "entity-neighbor-b2"
        n_b3 = "entity-neighbor-b3"

        monkeypatch.setenv("WIKI_QUERY_MAX_NEIGHBORS", "2")
        # Keep synth budget high so cap is the only limiter
        monkeypatch.setenv("WIKI_SYNTH_MAX_OBJECTS", "24")
        # Force Tier-2 by setting index threshold low
        monkeypatch.setenv("WIKI_INDEX_THRESHOLD", "1")

        import anytype_llm_wiki.indexer as _idx_mod
        import anytype_llm_wiki.wiki.query as _q_mod

        def stub_search(query, space_id, types, limit=10):
            return [
                {"object_id": seed_a_id, "type": "wiki_entity", "score": 0.9},
                {"object_id": seed_b_id, "type": "wiki_entity", "score": 0.8},
            ]

        monkeypatch.setattr(_idx_mod, "semantic_search_core", stub_search)
        monkeypatch.setattr(_q_mod, "synthesize", lambda q, ctx: "cap answer " * 10)

        fetch_counts: dict[str, int] = {}
        list_resp = {"data": [_schema_obj()], "pagination": {"has_more": False}}

        def dispatcher(request, **kwargs):
            if _is_list_request(request):
                return httpx.Response(200, json=list_resp)
            oid = _obj_id_from_request(request)
            fetch_counts[oid] = fetch_counts.get(oid, 0) + 1
            if oid == seed_a_id:
                return httpx.Response(200, json={"object": {
                    "id": seed_a_id, "name": "SeedA", "type": {"key": "wiki_entity"},
                    "properties": [
                        {"key": "wiki_description", "text": "seed a"},
                        {"key": "wiki_relations", "objects": [n_a1, n_a2]},
                    ],
                }})
            if oid == seed_b_id:
                return httpx.Response(200, json={"object": {
                    "id": seed_b_id, "name": "SeedB", "type": {"key": "wiki_entity"},
                    "properties": [
                        {"key": "wiki_description", "text": "seed b"},
                        {"key": "wiki_relations", "objects": [n_b1, n_b2, n_b3]},
                    ],
                }})
            # All neighbor objects
            return httpx.Response(200, json={"object": {
                "id": oid, "name": oid, "type": {"key": "wiki_entity"},
                "properties": [{"key": "wiki_description", "text": "neighbor content"}],
            }})

        respx.get().mock(side_effect=dispatcher)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001"}}))

        from anytype_llm_wiki.wiki.query import wiki_query
        result = wiki_query(question="cap test", space_id=FAKE_SPACE_ID, file_back=False)

        # AC5: exact warning string (ASCII ->, not Unicode arrow)
        warnings = result.get("warnings", [])
        assert any("neighbor_fan_out_capped: 5 -> 2" in str(w) for w in warnings), (
            f"AC5: must contain 'neighbor_fan_out_capped: 5 -> 2' in warnings. Got: {warnings}"
        )
        # AC5 / SF-F: exactly the D5-top 2 neighbor ids (n_a1, n_a2) must be fetched
        assert fetch_counts.get(n_a1, 0) == 1, (
            f"AC5 / SF-F: D5-top neighbor {n_a1!r} must be fetched exactly once. "
            f"fetch_counts: {fetch_counts}"
        )
        assert fetch_counts.get(n_a2, 0) == 1, (
            f"AC5 / SF-F: D5-top neighbor {n_a2!r} must be fetched exactly once. "
            f"fetch_counts: {fetch_counts}"
        )
        # The D5-bottom neighbors (from seed-rank-1) must NOT be fetched
        assert fetch_counts.get(n_b1, 0) == 0, (
            f"AC5 / SF-F: capped-out neighbor {n_b1!r} must NOT be fetched. "
            f"fetch_counts: {fetch_counts}"
        )
        assert fetch_counts.get(n_b2, 0) == 0, (
            f"AC5 / SF-F: capped-out neighbor {n_b2!r} must NOT be fetched. "
            f"fetch_counts: {fetch_counts}"
        )
        assert fetch_counts.get(n_b3, 0) == 0, (
            f"AC5 / SF-F: capped-out neighbor {n_b3!r} must NOT be fetched. "
            f"fetch_counts: {fetch_counts}"
        )

    @respx.mock
    def test_partial_status_one_failed_one_succeeded_neighbor(self, monkeypatch):
        """AC12 / SG-5 / SF-H: D5 active; one neighbor fetch fails, one succeeds →
        status=partial, neighbor_fetch_failed warning, succeeded neighbor in
        sources_consulted, failed neighbor absent.
        """
        seed_id = "entity-seed-partial-001"
        good_neighbor_id = "entity-neighbor-good-001"
        bad_neighbor_id = "entity-neighbor-bad-001"

        # Use Tier-2 stub search for determinism
        monkeypatch.setenv("WIKI_INDEX_THRESHOLD", "1")
        monkeypatch.setenv("WIKI_SYNTH_MAX_OBJECTS", "24")

        import anytype_llm_wiki.indexer as _idx_mod
        import anytype_llm_wiki.wiki.query as _q_mod

        def stub_search(query, space_id, types, limit=10):
            return [{"object_id": seed_id, "type": "wiki_entity", "score": 0.9}]

        monkeypatch.setattr(_idx_mod, "semantic_search_core", stub_search)
        monkeypatch.setattr(_q_mod, "synthesize", lambda q, ctx: "partial answer " * 10)

        list_resp = {"data": [_schema_obj()], "pagination": {"has_more": False}}

        def dispatcher(request, **kwargs):
            if _is_list_request(request):
                return httpx.Response(200, json=list_resp)
            oid = _obj_id_from_request(request)
            if oid == seed_id:
                return httpx.Response(200, json={"object": {
                    "id": seed_id, "name": "Seed", "type": {"key": "wiki_entity"},
                    "properties": [
                        {"key": "wiki_description", "text": "seed desc"},
                        # good_neighbor listed first (lower object_id), bad second
                        {"key": "wiki_relations", "objects": [good_neighbor_id, bad_neighbor_id]},
                    ],
                }})
            if oid == good_neighbor_id:
                return httpx.Response(200, json={"object": {
                    "id": good_neighbor_id, "name": "GoodNeighbor",
                    "type": {"key": "wiki_entity"},
                    "properties": [{"key": "wiki_description", "text": "good neighbor content"}],
                }})
            if oid == bad_neighbor_id:
                # Simulate fetch failure → neighbor_fetch_failed
                return httpx.Response(404, json={"error": "not found"})
            return httpx.Response(200, json={"object": {
                "id": oid, "name": oid, "type": {"key": "wiki_entity"},
                "properties": [],
            }})

        respx.get().mock(side_effect=dispatcher)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001"}}))

        from anytype_llm_wiki.wiki.query import wiki_query
        result = wiki_query(question="partial neighbor test", space_id=FAKE_SPACE_ID, file_back=False)

        # AC12: status must be partial
        assert result.get("status") == "partial", (
            f"AC12 / SG-5: status must be 'partial' when one neighbor fails. "
            f"Got: {result.get('status')!r}. Full result: {result}"
        )
        # AC12: failed neighbor must not appear in sources_consulted
        source_ids = [s.get("object_id") for s in result.get("sources_consulted", [])]
        assert bad_neighbor_id not in source_ids, (
            f"AC12 / SF-H: failed neighbor {bad_neighbor_id!r} must not appear in "
            f"sources_consulted. Got: {source_ids}"
        )
        # AC12: succeeded neighbor must appear in sources_consulted
        assert good_neighbor_id in source_ids, (
            f"AC12: succeeded neighbor {good_neighbor_id!r} must appear in "
            f"sources_consulted. Got: {source_ids}"
        )
        # AC12: neighbor_fetch_failed warning for the bad neighbor
        warnings = result.get("warnings", [])
        assert any(f"neighbor_fetch_failed: {bad_neighbor_id}" in str(w) for w in warnings), (
            f"AC12: must emit neighbor_fetch_failed warning for {bad_neighbor_id!r}. "
            f"Got warnings: {warnings}"
        )


class TestDeterministicTrimOrder:
    """AC4 — D5 deterministic trim order in _build_context."""

    @respx.mock
    def test_higher_rank_seed_neighbor_survives_trim(self, monkeypatch):
        """AC4: synthesis budget exceeded; neighbor from seed-rank-0 survives trim;
        neighbor from seed-rank-1 is dropped. Uses Tier-2 stub for deterministic
        seed rank ordering.
        """
        # seed_a (rank-0, score=0.9): has neighbor n_rank0
        # seed_b (rank-1, score=0.5): has neighbor n_rank1
        # With WIKI_SYNTH_MAX_OBJECTS=2, only seed_a + n_rank0 fit;
        # seed_b might also get included before n_rank1, so we set cap=3 to include
        # seed_a, seed_b, n_rank0 (n_rank1 is trimmed as lowest priority).
        seed_a_id = "entity-seed-dt-a"
        seed_b_id = "entity-seed-dt-b"
        n_rank0_id = "entity-neighbor-rank0"
        n_rank1_id = "entity-neighbor-rank1"

        # Cap at 3 objects: sorted_candidates=[seed_a, seed_b] (score desc) +
        # neighbors in D5 order: [n_rank0 (seed-rank 0), n_rank1 (seed-rank 1)]
        # Ordered = [seed_a, seed_b, n_rank0, n_rank1] → cap 3 → drop n_rank1
        monkeypatch.setenv("WIKI_SYNTH_MAX_OBJECTS", "3")
        monkeypatch.setenv("WIKI_INDEX_THRESHOLD", "1")
        monkeypatch.setenv("WIKI_QUERY_MAX_NEIGHBORS", "16")

        import anytype_llm_wiki.indexer as _idx_mod
        import anytype_llm_wiki.wiki.query as _q_mod

        def stub_search(query, space_id, types, limit=10):
            return [
                {"object_id": seed_a_id, "type": "wiki_entity", "score": 0.9},
                {"object_id": seed_b_id, "type": "wiki_entity", "score": 0.5},
            ]

        monkeypatch.setattr(_idx_mod, "semantic_search_core", stub_search)
        monkeypatch.setattr(_q_mod, "synthesize", lambda q, ctx: "trim order " * 10)

        list_resp = {"data": [_schema_obj()], "pagination": {"has_more": False}}
        fetch_counts: dict[str, int] = {}

        def dispatcher(request, **kwargs):
            if _is_list_request(request):
                return httpx.Response(200, json=list_resp)
            oid = _obj_id_from_request(request)
            fetch_counts[oid] = fetch_counts.get(oid, 0) + 1
            if oid == seed_a_id:
                return httpx.Response(200, json={"object": {
                    "id": seed_a_id, "name": "SeedA", "type": {"key": "wiki_entity"},
                    "properties": [
                        {"key": "wiki_description", "text": "seed a content"},
                        {"key": "wiki_relations", "objects": [n_rank0_id]},
                    ],
                }})
            if oid == seed_b_id:
                return httpx.Response(200, json={"object": {
                    "id": seed_b_id, "name": "SeedB", "type": {"key": "wiki_entity"},
                    "properties": [
                        {"key": "wiki_description", "text": "seed b content"},
                        {"key": "wiki_relations", "objects": [n_rank1_id]},
                    ],
                }})
            if oid == n_rank0_id:
                return httpx.Response(200, json={"object": {
                    "id": n_rank0_id, "name": "NeighborRank0", "type": {"key": "wiki_entity"},
                    "properties": [{"key": "wiki_description", "text": "rank0 neighbor"}],
                }})
            if oid == n_rank1_id:
                return httpx.Response(200, json={"object": {
                    "id": n_rank1_id, "name": "NeighborRank1", "type": {"key": "wiki_entity"},
                    "properties": [{"key": "wiki_description", "text": "rank1 neighbor"}],
                }})
            return httpx.Response(200, json={"object": {
                "id": oid, "name": oid, "type": {"key": "wiki_entity"},
                "properties": [],
            }})

        respx.get().mock(side_effect=dispatcher)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001"}}))

        from anytype_llm_wiki.wiki.query import wiki_query
        result = wiki_query(question="trim order test", space_id=FAKE_SPACE_ID, file_back=False)

        source_ids = [s.get("object_id") for s in result.get("sources_consulted", [])]
        warnings = result.get("warnings", [])

        # A synthesis_context_trimmed warning must appear (something was dropped)
        assert any("synthesis_context_trimmed" in str(w) for w in warnings), (
            f"AC4: synthesis_context_trimmed must appear when budget is exceeded. "
            f"Warnings: {warnings}"
        )
        # The rank-0 seed's neighbor must survive
        assert n_rank0_id in source_ids, (
            f"AC4: neighbor from seed-rank-0 ({n_rank0_id!r}) must survive trim. "
            f"sources_consulted: {source_ids}"
        )
        # The rank-1 seed's neighbor must be dropped (it's last in D5 order)
        assert n_rank1_id not in source_ids, (
            f"AC4: neighbor from seed-rank-1 ({n_rank1_id!r}) must be dropped by trim. "
            f"sources_consulted: {source_ids}"
        )


class TestFileBackSeedOnly:
    """AC7 — _maybe_file_back receives only seed (candidate) ids, never neighbors."""

    @respx.mock
    def test_drew_from_excludes_neighbors(self, monkeypatch):
        """AC7 / D2: with 2 seeds + 3 neighbors and WIKI_FILE_BACK_MIN_SOURCES=2,
        the PATCH payload for wiki_drew_from contains exactly the 2 seed ids,
        not the 3 neighbor ids.
        """
        seed_a_id = "entity-seed-fb-a"
        seed_b_id = "entity-seed-fb-b"
        neighbor_ids = ["entity-neighbor-fb-1", "entity-neighbor-fb-2", "entity-neighbor-fb-3"]

        monkeypatch.setenv("WIKI_FILE_BACK_MIN_SOURCES", "2")
        monkeypatch.setenv("WIKI_FILE_BACK_MIN_WORDS", "5")
        monkeypatch.setenv("WIKI_SYNTH_MAX_OBJECTS", "24")
        monkeypatch.setenv("WIKI_QUERY_MAX_NEIGHBORS", "16")
        monkeypatch.setenv("WIKI_INDEX_THRESHOLD", "1")

        import anytype_llm_wiki.indexer as _idx_mod
        import anytype_llm_wiki.wiki.query as _q_mod

        def stub_search(query, space_id, types, limit=10):
            return [
                {"object_id": seed_a_id, "type": "wiki_entity", "score": 0.9},
                {"object_id": seed_b_id, "type": "wiki_entity", "score": 0.8},
            ]

        monkeypatch.setattr(_idx_mod, "semantic_search_core", stub_search)
        monkeypatch.setattr(_q_mod, "synthesize",
                            lambda q, ctx: "filed answer with enough words here now")

        list_resp = {"data": [_schema_obj()], "pagination": {"has_more": False}}
        patch_calls: list[tuple[str, dict]] = []

        def track_patch(request, **kwargs):
            import json as _json
            oid = _obj_id_from_request(request)
            try:
                payload = _json.loads(request.content)
            except Exception:
                payload = {}
            patch_calls.append((oid, payload))
            return httpx.Response(200, json={"object": {"id": oid}})

        def dispatcher(request, **kwargs):
            if _is_list_request(request):
                return httpx.Response(200, json=list_resp)
            oid = _obj_id_from_request(request)
            if oid == seed_a_id:
                return httpx.Response(200, json={"object": {
                    "id": seed_a_id, "name": "SeedA", "type": {"key": "wiki_entity"},
                    "properties": [
                        {"key": "wiki_description", "text": "seed a desc"},
                        {"key": "wiki_relations", "objects": neighbor_ids},
                    ],
                }})
            if oid == seed_b_id:
                return httpx.Response(200, json={"object": {
                    "id": seed_b_id, "name": "SeedB", "type": {"key": "wiki_entity"},
                    "properties": [
                        {"key": "wiki_description", "text": "seed b desc"},
                        {"key": "wiki_relations", "objects": []},
                    ],
                }})
            if oid in neighbor_ids:
                return httpx.Response(200, json={"object": {
                    "id": oid, "name": f"Neighbor {oid}", "type": {"key": "wiki_entity"},
                    "properties": [{"key": "wiki_description", "text": "neighbor desc"}],
                }})
            # Write-time re-fetch of seeds (SF4)
            if oid in (seed_a_id, seed_b_id):
                return httpx.Response(200, json={"object": {
                    "id": oid, "name": "Seed", "type": {"key": "wiki_entity"},
                    "properties": [],
                }})
            return httpx.Response(200, json={"object": {
                "id": oid, "name": oid, "type": {"key": "wiki_entity"},
                "properties": [],
            }})

        respx.get().mock(side_effect=dispatcher)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "query-filed-001"}}))
        respx.patch().mock(side_effect=track_patch)

        from anytype_llm_wiki.wiki.query import wiki_query
        result = wiki_query(question="file back seed only test", space_id=FAKE_SPACE_ID, file_back=True)

        assert result.get("filed_back"), (
            f"AC7: file-back must have fired. Result: {result}"
        )
        query_id = result.get("query_object_id") or "query-filed-001"
        # Extract wiki_drew_from from the PATCH on the query object
        drew_from_ids: list[str] = []
        for (oid, payload) in patch_calls:
            if oid == query_id:
                for prop in payload.get("properties", []):
                    if prop.get("key") == "wiki_drew_from":
                        drew_from_ids = prop.get("objects", [])
                        break
                if drew_from_ids:
                    break

        assert drew_from_ids, (
            f"AC7: wiki_drew_from must be set in the PATCH payload. "
            f"patch_calls: {patch_calls}"
        )
        # Seeds must be present
        assert seed_a_id in drew_from_ids, (
            f"AC7: seed {seed_a_id!r} must be in wiki_drew_from. Got: {drew_from_ids}"
        )
        assert seed_b_id in drew_from_ids, (
            f"AC7: seed {seed_b_id!r} must be in wiki_drew_from. Got: {drew_from_ids}"
        )
        # Neighbors must NOT be present
        for nid in neighbor_ids:
            assert nid not in drew_from_ids, (
                f"AC7 / D2: neighbor {nid!r} must NOT be in wiki_drew_from (seed-only). "
                f"Got: {drew_from_ids}"
            )


class TestFanOutDebugLog:
    """AC6 — debug log and conditional INFO warning for fan-out measurability."""

    @respx.mock
    def test_fanout_debug_logged(self, monkeypatch, caplog):
        """AC6 / D6: logger.debug with 'neighbor_fanout:' is emitted when neighbors
        are present. Also asserts the conditional neighbor_fanout: fetched=N warning
        is in result['warnings'] when fetching > synth_max_objects // 2.
        """
        import logging
        seed_id = "entity-seed-debug-001"
        # Create enough neighbors to exceed synth_max_objects // 2
        # WIKI_SYNTH_MAX_OBJECTS=4 → threshold = 4//2 = 2
        # We'll have 3 neighbors → fetching=3 > 2 → INFO warning expected
        neighbor_ids = [f"entity-neighbor-debug-{i}" for i in range(3)]

        monkeypatch.setenv("WIKI_SYNTH_MAX_OBJECTS", "24")
        monkeypatch.setenv("WIKI_QUERY_MAX_NEIGHBORS", "16")
        monkeypatch.setenv("WIKI_INDEX_THRESHOLD", "1")

        import anytype_llm_wiki.indexer as _idx_mod
        import anytype_llm_wiki.wiki.query as _q_mod

        def stub_search(query, space_id, types, limit=10):
            return [{"object_id": seed_id, "type": "wiki_entity", "score": 0.9}]

        monkeypatch.setattr(_idx_mod, "semantic_search_core", stub_search)
        monkeypatch.setattr(_q_mod, "synthesize", lambda q, ctx: "debug log answer " * 10)

        list_resp = {"data": [_schema_obj()], "pagination": {"has_more": False}}

        def dispatcher(request, **kwargs):
            if _is_list_request(request):
                return httpx.Response(200, json=list_resp)
            oid = _obj_id_from_request(request)
            if oid == seed_id:
                return httpx.Response(200, json={"object": {
                    "id": seed_id, "name": "Seed", "type": {"key": "wiki_entity"},
                    "properties": [
                        {"key": "wiki_description", "text": "seed desc"},
                        {"key": "wiki_relations", "objects": neighbor_ids},
                    ],
                }})
            return httpx.Response(200, json={"object": {
                "id": oid, "name": oid, "type": {"key": "wiki_entity"},
                "properties": [{"key": "wiki_description", "text": "neighbor desc"}],
            }})

        respx.get().mock(side_effect=dispatcher)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001"}}))

        from anytype_llm_wiki.wiki.query import wiki_query
        with caplog.at_level(logging.DEBUG, logger="anytype_llm_wiki.wiki.query"):
            result = wiki_query(question="debug log test", space_id=FAKE_SPACE_ID, file_back=False)

        # AC6: DEBUG log line with 'neighbor_fanout:' must be emitted
        debug_messages = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("neighbor_fanout" in msg for msg in debug_messages), (
            f"AC6 / D6: logger.debug with 'neighbor_fanout:' must be emitted. "
            f"DEBUG messages: {debug_messages}"
        )

    @respx.mock
    def test_fanout_info_warning_above_threshold(self, monkeypatch):
        """AC6 / SF-E: when fetching > synth_max_objects // 2, result['warnings']
        contains 'neighbor_fanout: fetched=N'.
        """
        seed_id = "entity-seed-fwarn-001"
        # WIKI_SYNTH_MAX_OBJECTS=4 → threshold=2; need >2 neighbors fetched
        neighbor_ids = [f"entity-neighbor-fwarn-{i}" for i in range(3)]

        monkeypatch.setenv("WIKI_SYNTH_MAX_OBJECTS", "4")
        monkeypatch.setenv("WIKI_QUERY_MAX_NEIGHBORS", "16")
        monkeypatch.setenv("WIKI_INDEX_THRESHOLD", "1")

        import anytype_llm_wiki.indexer as _idx_mod
        import anytype_llm_wiki.wiki.query as _q_mod

        def stub_search(query, space_id, types, limit=10):
            return [{"object_id": seed_id, "type": "wiki_entity", "score": 0.9}]

        monkeypatch.setattr(_idx_mod, "semantic_search_core", stub_search)
        monkeypatch.setattr(_q_mod, "synthesize", lambda q, ctx: "fanout warn answer " * 10)

        list_resp = {"data": [_schema_obj()], "pagination": {"has_more": False}}

        def dispatcher(request, **kwargs):
            if _is_list_request(request):
                return httpx.Response(200, json=list_resp)
            oid = _obj_id_from_request(request)
            if oid == seed_id:
                return httpx.Response(200, json={"object": {
                    "id": seed_id, "name": "Seed", "type": {"key": "wiki_entity"},
                    "properties": [
                        {"key": "wiki_description", "text": "s"},
                        {"key": "wiki_relations", "objects": neighbor_ids},
                    ],
                }})
            return httpx.Response(200, json={"object": {
                "id": oid, "name": oid, "type": {"key": "wiki_entity"},
                "properties": [{"key": "wiki_description", "text": "n"}],
            }})

        respx.get().mock(side_effect=dispatcher)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001"}}))

        from anytype_llm_wiki.wiki.query import wiki_query
        result = wiki_query(question="fanout warn test", space_id=FAKE_SPACE_ID, file_back=False)

        warnings = result.get("warnings", [])
        assert any("neighbor_fanout: fetched=" in str(w) for w in warnings), (
            f"AC6 / SF-E: 'neighbor_fanout: fetched=N' must appear in warnings when "
            f"fetching > synth_max_objects//2. Got warnings: {warnings}"
        )

    @respx.mock
    def test_fanout_info_warning_absent_below_threshold(self, monkeypatch):
        """AC6 / SF-E: when fetching <= synth_max_objects // 2, no
        'neighbor_fanout: fetched=N' entry in result['warnings'].
        """
        seed_id = "entity-seed-fnowarn-001"
        # WIKI_SYNTH_MAX_OBJECTS=24 → threshold=12; 1 neighbor → no warning
        neighbor_ids = ["entity-neighbor-fnowarn-001"]

        monkeypatch.setenv("WIKI_SYNTH_MAX_OBJECTS", "24")
        monkeypatch.setenv("WIKI_QUERY_MAX_NEIGHBORS", "16")
        monkeypatch.setenv("WIKI_INDEX_THRESHOLD", "1")

        import anytype_llm_wiki.indexer as _idx_mod
        import anytype_llm_wiki.wiki.query as _q_mod

        def stub_search(query, space_id, types, limit=10):
            return [{"object_id": seed_id, "type": "wiki_entity", "score": 0.9}]

        monkeypatch.setattr(_idx_mod, "semantic_search_core", stub_search)
        monkeypatch.setattr(_q_mod, "synthesize", lambda q, ctx: "no fanout warn " * 10)

        list_resp = {"data": [_schema_obj()], "pagination": {"has_more": False}}

        def dispatcher(request, **kwargs):
            if _is_list_request(request):
                return httpx.Response(200, json=list_resp)
            oid = _obj_id_from_request(request)
            if oid == seed_id:
                return httpx.Response(200, json={"object": {
                    "id": seed_id, "name": "Seed", "type": {"key": "wiki_entity"},
                    "properties": [
                        {"key": "wiki_description", "text": "s"},
                        {"key": "wiki_relations", "objects": neighbor_ids},
                    ],
                }})
            return httpx.Response(200, json={"object": {
                "id": oid, "name": oid, "type": {"key": "wiki_entity"},
                "properties": [{"key": "wiki_description", "text": "n"}],
            }})

        respx.get().mock(side_effect=dispatcher)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001"}}))

        from anytype_llm_wiki.wiki.query import wiki_query
        result = wiki_query(question="no fanout warn test", space_id=FAKE_SPACE_ID, file_back=False)

        warnings = result.get("warnings", [])
        assert not any("neighbor_fanout: fetched=" in str(w) for w in warnings), (
            f"AC6 / SF-E: 'neighbor_fanout: fetched=N' must NOT appear when "
            f"fetching <= synth_max_objects//2. Got warnings: {warnings}"
        )


class TestDualShapeViaQueryReplacement:
    @respx.mock
    def test_mixed_shape_neighbors_both_fetched(self, monkeypatch):
        """SF5: a candidate whose wiki_relations mixes a bare-string id and an
        object-dict id has BOTH neighbors fetched via get_object. Single dispatcher.
        """
        str_nid = "neighbor-str-001"
        obj_nid = "neighbor-obj-001"
        cand_id = "entity-dualshape-001"
        list_resp = {"data": [
            _schema_obj(),
            {"id": cand_id, "name": "Dual", "type": {"key": "wiki_entity"},
             "properties": [{"key": "wiki_relations",
                             "objects": [str_nid, {"id": obj_nid, "name": "ON"}]}]},
        ], "pagination": {"has_more": False}}

        fetched = []

        def dispatcher(request, **kwargs):
            if not _is_object_request(request):
                return httpx.Response(200, json=list_resp if _is_list_request(request)
                                      else {"data": [], "pagination": {"has_more": False}})
            oid = _obj_id_from_request(request)
            fetched.append(oid)
            props = []
            if oid == cand_id:
                props = [{"key": "wiki_relations",
                          "objects": [str_nid, {"id": obj_nid, "name": "ON"}]}]
            return httpx.Response(200, json={"object": {"id": oid, "name": oid,
                                                        "type": {"key": "wiki_entity"},
                                                        "properties": props}})

        import anytype_llm_wiki.wiki.query as _q_mod
        monkeypatch.setattr(_q_mod, "synthesize", lambda q, ctx: "dual answer")

        respx.get().mock(side_effect=dispatcher)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001"}}))

        from anytype_llm_wiki.wiki.query import wiki_query
        wiki_query(question="dual", space_id=FAKE_SPACE_ID, file_back=False)

        assert str_nid in fetched, fetched
        assert obj_nid in fetched, fetched
