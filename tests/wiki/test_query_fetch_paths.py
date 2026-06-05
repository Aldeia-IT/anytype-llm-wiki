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
    def test_reciprocal_merge_preserves_prior(self, monkeypatch):
        """N1: reciprocal back-reference onto a cited entity reads the LIVE relation
        array (prior=['e1','e2'], distinct from the stale enumeration snapshot) and
        writes prior ∪ [query_id]. Single dispatcher route.
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
        assert cited_patches, [oid for oid, _ in patch_calls]
        for payload in cited_patches:
            for prop in payload.get("properties", []):
                if prop.get("key") in ("wiki_relations", "wiki_related"):
                    merged = prop.get("objects", [])
                    assert "e1" in merged and "e2" in merged, merged
                    assert query_id in merged, merged


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
