"""Tests for MCP server tools (requires all services running + indexed data)."""

import pytest

from anytype_rag import config


def _services_available() -> bool:
    import httpx

    try:
        httpx.get(f"{config.OLLAMA_URL}/api/tags", timeout=3)
        httpx.get(f"{config.QDRANT_URL}/collections", headers={
            "api-key": config.QDRANT_API_KEY,
        }, timeout=3)
        return True
    except (httpx.ConnectError, httpx.TimeoutException):
        return False


@pytest.fixture(autouse=True)
def check_services():
    if not _services_available():
        pytest.skip("Required services not reachable")


class TestSemanticSearch:
    def test_returns_results(self):
        from anytype_rag.server import semantic_search

        results = semantic_search("capoeira governance council")
        assert isinstance(results, list)
        assert len(results) > 0

    def test_result_shape(self):
        from anytype_rag.server import semantic_search

        results = semantic_search("token design")
        if results:
            r = results[0]
            assert "object_name" in r
            assert "object_id" in r
            assert "type" in r
            assert "heading" in r
            assert "text" in r
            assert "score" in r
            assert isinstance(r["score"], float)

    def test_limit(self):
        from anytype_rag.server import semantic_search

        results = semantic_search("capoeira", limit=3)
        assert len(results) <= 3

    def test_type_filter(self):
        from anytype_rag.server import semantic_search

        results = semantic_search("capoeira", types=["page"])
        for r in results:
            assert r["type"] == "page"

    def test_irrelevant_query_lower_scores(self):
        from anytype_rag.server import semantic_search

        relevant = semantic_search("capoeira DAO governance")
        irrelevant = semantic_search("quantum computing black holes")
        if relevant and irrelevant:
            assert relevant[0]["score"] > irrelevant[0]["score"]


class TestReindexTool:
    def test_reindex_returns_stats(self):
        from anytype_rag.server import reindex_anytype

        stats = reindex_anytype()
        assert isinstance(stats, dict)
        assert "spaces" in stats
