"""Tests for MCP server tools.

Live-API tests (TestSemanticSearch, TestReindexTool) require all services
running — they skip automatically via the check_services fixture.

v0.2.0 wiki_bootstrap registration test lives in:
  tests/wiki/test_server_registration.py
It is kept separate because the module-level autouse check_services fixture
here would silence it when live services are absent (BLOCKING-B2).
"""

import pytest

from anytype_llm_wiki import config


def _services_available() -> bool:
    import httpx

    try:
        resp = httpx.get(f"{config.OLLAMA_URL}/api/tags", timeout=3)
        resp.raise_for_status()
        resp = httpx.get(f"{config.QDRANT_URL}/collections", headers={
            "api-key": config.QDRANT_API_KEY,
        }, timeout=3)
        resp.raise_for_status()
        return True
    except httpx.HTTPError:
        return False


@pytest.fixture(autouse=True)
def check_services():
    if not _services_available():
        pytest.skip("Required services not reachable")


class TestSemanticSearch:
    def test_returns_results(self):
        from anytype_llm_wiki.server import semantic_search

        results = semantic_search("capoeira governance council")
        assert isinstance(results, list)
        assert len(results) > 0

    def test_result_shape(self):
        from anytype_llm_wiki.server import semantic_search

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
        from anytype_llm_wiki.server import semantic_search

        results = semantic_search("capoeira", limit=3)
        assert len(results) <= 3

    def test_type_filter(self):
        from anytype_llm_wiki.server import semantic_search

        results = semantic_search("capoeira", types=["page"])
        for r in results:
            assert r["type"] == "page"

    def test_irrelevant_query_lower_scores(self):
        from anytype_llm_wiki.server import semantic_search

        relevant = semantic_search("capoeira DAO governance")
        irrelevant = semantic_search("quantum computing black holes")
        if relevant and irrelevant:
            assert relevant[0]["score"] > irrelevant[0]["score"]


class TestReindexTool:
    def test_reindex_returns_stats(self):
        from anytype_llm_wiki.server import reindex_anytype

        stats = reindex_anytype()
        assert isinstance(stats, dict)
        assert "spaces" in stats


class TestServerStartupAdjudicationGate:
    """v0.7.3: the MCP server REFUSES TO START (exit 2) when alias adjudication is
    enabled on an unvetted model — the config is fixed at start time, so it fails
    loud and early rather than lazily on the first ingest."""

    def _patch_run(self, monkeypatch):
        import sys as _sys
        from anytype_llm_wiki import server
        ran = {"n": 0}
        monkeypatch.setattr(server.mcp, "run", lambda **k: ran.__setitem__("n", ran["n"] + 1))
        monkeypatch.setattr(_sys, "argv", ["anytype-llm-wiki"])  # no subcommand → server path
        return server, ran

    def test_refuses_start_when_enabled_unvetted(self, monkeypatch):
        monkeypatch.setenv("WIKI_ALIAS_ADJUDICATION", "on")
        monkeypatch.setenv("WIKI_EXTRACT_MODEL", "qwen2.5:7b")
        monkeypatch.delenv("WIKI_ALIAS_VETTED_MODELS", raising=False)
        server, ran = self._patch_run(monkeypatch)
        with pytest.raises(SystemExit) as ei:
            server.main()
        assert ei.value.code == 2
        assert ran["n"] == 0, "server must NOT start the MCP transport with an unapproved config"

    def test_starts_when_enabled_and_vetted(self, monkeypatch):
        monkeypatch.setenv("WIKI_ALIAS_ADJUDICATION", "on")
        monkeypatch.setenv("WIKI_EXTRACT_MODEL", "qwen3.5-mlx:latest")
        server, ran = self._patch_run(monkeypatch)
        server.main()  # must not raise
        assert ran["n"] == 1

    def test_starts_when_disabled_even_if_model_unvetted(self, monkeypatch):
        monkeypatch.delenv("WIKI_ALIAS_ADJUDICATION", raising=False)  # off (default)
        monkeypatch.setenv("WIKI_EXTRACT_MODEL", "qwen2.5:7b")
        server, ran = self._patch_run(monkeypatch)
        server.main()
        assert ran["n"] == 1

    def test_starts_when_unvetted_model_whitelisted(self, monkeypatch):
        monkeypatch.setenv("WIKI_ALIAS_ADJUDICATION", "on")
        monkeypatch.setenv("WIKI_EXTRACT_MODEL", "qwen2.5:7b")
        monkeypatch.setenv("WIKI_ALIAS_VETTED_MODELS", "qwen2.5")
        server, ran = self._patch_run(monkeypatch)
        server.main()
        assert ran["n"] == 1
