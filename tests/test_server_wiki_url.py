"""Offline tests for wiki_url in server.semantic_search hits (Aldeia-IT/aldeia-box#1413).

Kept apart from tests/test_server.py because that module's autouse
check_services fixture skips every test when live services are unreachable.
All collaborators here are faked; nothing talks to Qdrant or Ollama.
"""

from anytype_llm_wiki import config


class _FakePoint:
    def __init__(self, payload, score=0.9):
        self.payload = payload
        self.score = score


class _FakeQdrant:
    def __init__(self, points):
        self._points = points

    def query_points(self, collection_name, query, query_filter=None, limit=10, with_payload=True):
        class _Result:
            pass

        _Result.points = self._points
        return _Result()


def _payload(**extra):
    payload = {
        "object_id": "src-1", "space_id": "sp-1", "object_name": "S",
        "type_key": "wiki_source", "heading": "Excerpt", "text": "Body text.",
    }
    payload.update(extra)
    return payload


def _patch_backend(monkeypatch, points):
    import anytype_llm_wiki.indexer as _indexer

    monkeypatch.setattr(_indexer, "_qdrant", lambda: _FakeQdrant(points))
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
    assert hit.get("wiki_url") == "https://example.org/page"  # red now: proves the hit was read
    assert "source_type" not in hit
    assert "domain_tags" not in hit
