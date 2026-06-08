"""Tests for prune_stale_citation_edges — the M1 remediation that strips stale
wiki_query citation edges left by the OLD wiki_query file-back."""

import json

import httpx
import respx

ANYTYPE_BASE = "http://127.0.0.1:31012"
FAKE_SPACE_ID = "space-prune-test-001"


def _env(monkeypatch):
    monkeypatch.setenv("ANYTYPE_API_KEY", "test-prune-key")
    monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
    monkeypatch.setenv("ANYTYPE_API_VERSION", "2025-11-08")


def _entity(oid, name, relations):
    return {
        "id": oid, "name": name, "type": {"key": "wiki_entity"},
        "properties": [{"key": "wiki_relations", "objects": relations}],
    }


def _query(oid, name):
    return {
        "id": oid, "name": name, "type": {"key": "wiki_query"},
        "properties": [{"key": "wiki_answer", "text": "an answer"}],
    }


@respx.mock
def test_prune_strips_query_ids_keeps_real_relations(monkeypatch):
    _env(monkeypatch)
    # entity-1 has a real relation (e-2) AND a stale citation edge (q-1).
    objects = [
        _entity("e-1", "Entity One", ["q-1", "e-2"]),
        _entity("e-2", "Entity Two", ["e-1"]),
        _query("q-1", "What is X?"),
    ]
    respx.get(f"{ANYTYPE_BASE}/v1/spaces/{FAKE_SPACE_ID}/objects").mock(
        return_value=httpx.Response(200, json={"data": objects, "pagination": {"has_more": False}})
    )
    patches = []

    def track_patch(request, **kwargs):
        oid = str(request.url).rstrip("/").split("/")[-1]
        patches.append((oid, json.loads(request.content)))
        return httpx.Response(200, json={"object": {"id": oid}})

    respx.patch(url__regex=rf"{ANYTYPE_BASE}/v1/spaces/{FAKE_SPACE_ID}/objects/.+").mock(
        side_effect=track_patch
    )

    from anytype_llm_wiki.wiki.query import prune_stale_citation_edges
    result = prune_stale_citation_edges(space_id=FAKE_SPACE_ID)

    assert result["status"] == "ok", result
    assert result["edges_pruned"] == 1, result
    assert result["objects_modified"] == 1, result
    # Only e-1 was patched, and its wiki_relations now exclude q-1 but keep e-2.
    e1_patches = [p for oid, p in patches if oid == "e-1"]
    assert len(e1_patches) == 1, patches
    rel = next(
        prop["objects"] for prop in e1_patches[0]["properties"]
        if prop["key"] == "wiki_relations"
    )
    assert rel == ["e-2"], f"q-1 must be stripped, e-2 kept; got {rel}"
    # e-2 (no stale edge) must not be patched.
    assert not [oid for oid, _ in patches if oid == "e-2"], patches


@respx.mock
def test_prune_is_noop_on_clean_space(monkeypatch):
    _env(monkeypatch)
    objects = [
        _entity("e-1", "Entity One", ["e-2"]),
        _entity("e-2", "Entity Two", ["e-1"]),
    ]  # no wiki_query objects at all
    respx.get(f"{ANYTYPE_BASE}/v1/spaces/{FAKE_SPACE_ID}/objects").mock(
        return_value=httpx.Response(200, json={"data": objects, "pagination": {"has_more": False}})
    )
    patched = []
    respx.patch(url__regex=rf"{ANYTYPE_BASE}/v1/spaces/{FAKE_SPACE_ID}/objects/.+").mock(
        side_effect=lambda request, **k: patched.append(1) or httpx.Response(200, json={"object": {"id": "x"}})
    )

    from anytype_llm_wiki.wiki.query import prune_stale_citation_edges
    result = prune_stale_citation_edges(space_id=FAKE_SPACE_ID)

    assert result["status"] == "ok", result
    assert result["edges_pruned"] == 0
    assert result["objects_modified"] == 0
    assert not patched, "a clean space must trigger no PATCH"
