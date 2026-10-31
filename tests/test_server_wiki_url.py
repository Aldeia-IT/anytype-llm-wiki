"""Offline tests for wiki_url in server.semantic_search hits (Aldeia-IT/aldeia-box#1413).

Kept apart from tests/test_server.py because that module's autouse
check_services fixture skips every test when live services are unreachable.
All collaborators here are faked; nothing talks to Qdrant or Ollama.
"""

import pytest

from anytype_llm_wiki import config
from tests.test_indexer import FakeQdrantClientWithSearch, _FakePoint
from tests.test_indexer import _source_payload as _payload


def _patch_backend(monkeypatch, points):
    import anytype_llm_wiki.indexer as _indexer

    fake = FakeQdrantClientWithSearch(mock_results=points)
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(_indexer, "embed_query", lambda q: [0.1] * config.EMBED_DIMS)


def test_server_semantic_search_returns_wiki_url_for_url_source(monkeypatch):
    """#1413 AC1b: server.semantic_search(types=["wiki_source"]) returns wiki_url."""
    _patch_backend(monkeypatch, [_FakePoint(_payload(wiki_url="https://example.org/page"))])
    from anytype_llm_wiki.server import semantic_search

    hits = semantic_search(query="q", types=["wiki_source"])
    assert len(hits) == 1
    assert hits[0].get("wiki_url") == "https://example.org/page"


def test_server_semantic_search_no_wiki_url_key_without_property(monkeypatch):
    """#1413 AC2: source without wiki_url, and an entity hit: no wiki_url key, six base keys."""
    entity = _payload(type_key="wiki_entity", object_id="ent-1", heading="Facts")
    _patch_backend(monkeypatch, [_FakePoint(_payload()), _FakePoint(entity)])
    from anytype_llm_wiki.server import semantic_search

    hits = semantic_search(query="q", types=["wiki_source", "wiki_entity"])
    assert len(hits) == 2
    for hit in hits:
        assert "wiki_url" not in hit
        assert set(hit) == {"object_name", "object_id", "type", "heading", "text", "score"}


def test_server_semantic_search_hits_do_not_expose_source_type(monkeypatch):
    """#1413 D5: no source_type / domain_tags in hits; wiki_url is the only addition."""
    payload = _payload(wiki_url="https://example.org/page", source_type="document", domain_tags=["ai"])
    _patch_backend(monkeypatch, [_FakePoint(payload)])
    from anytype_llm_wiki.server import semantic_search

    hit = semantic_search(query="q", types=["wiki_source"])[0]
    assert hit.get("wiki_url") == "https://example.org/page"
    assert "source_type" not in hit
    assert "domain_tags" not in hit


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=abc123",
    "https://pt.wikipedia.org/wiki/Mestre_Bimba#Vida",
])
def test_server_semantic_search_wiki_url_keeps_query_and_fragment(monkeypatch, url):
    """#1413 D3 (revised), end to end: Anytype object -> chunk -> payload -> hit keeps the
    link openable (query parameter and fragment survive unchanged)."""
    import anytype_llm_wiki.indexer as _indexer
    from anytype_llm_wiki.chunker import chunk_object
    from anytype_llm_wiki.server import semantic_search

    obj = {
        "id": "src-1", "space_id": "sp-1", "name": "S",
        "type": {"key": "wiki_source"}, "markdown": "",
        "properties": [
            {"key": "wiki_excerpt", "text": "Some text."},
            {"key": "wiki_url", "format": "url", "url": url},
        ],
    }
    chunks = chunk_object(obj)
    assert [c.get("wiki_url") for c in chunks] == [url] * len(chunks)
    payloads = [_indexer._chunk_to_payload(c) for c in chunks]
    assert [p.get("wiki_url") for p in payloads] == [url] * len(payloads)
    _patch_backend(monkeypatch, [_FakePoint(p) for p in payloads])

    hits = semantic_search(query="q", types=["wiki_source"])
    assert hits
    assert [h.get("wiki_url") for h in hits] == [url] * len(hits)
