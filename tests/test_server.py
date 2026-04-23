"""Tests for MCP server tools.

Live-API tests (TestSemanticSearch, TestReindexTool) require all services
running — they skip automatically via the check_services fixture.

v0.2.0 additions:
  TestWikiBootstrapRegistered — asserts wiki_bootstrap is registered as an @mcp.tool.
  No live API required for this test.
"""

import pytest

from anytype_llm_wiki import config


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


# ---------------------------------------------------------------------------
# v0.2.0 additions — AC #11 (wiki_bootstrap registered as @mcp.tool)
# These tests do NOT require live services.
# ---------------------------------------------------------------------------


class TestWikiBootstrapRegistered:
    """Assert wiki_bootstrap is registered in the MCP server as a tool.

    This test does NOT use the check_services fixture.
    It fails before v0.2.0 is implemented (wiki_bootstrap does not exist in server.py yet).
    """

    def test_wiki_bootstrap_is_registered_mcp_tool(self):
        """wiki_bootstrap must be registered as an @mcp.tool in server.py."""
        from anytype_llm_wiki.server import mcp
        # FastMCP stores registered tools in _tool_manager or similar
        # Try several possible attribute names used by FastMCP versions
        tool_names = set()
        if hasattr(mcp, "_tool_manager") and hasattr(mcp._tool_manager, "_tools"):
            tool_names = set(mcp._tool_manager._tools.keys())
        elif hasattr(mcp, "_tools"):
            tool_names = set(mcp._tools.keys())
        elif hasattr(mcp, "tools"):
            raw_tools = mcp.tools
            if callable(raw_tools):
                raw_tools = raw_tools()
            tool_names = {t if isinstance(t, str) else getattr(t, "name", str(t)) for t in raw_tools}
        else:
            # Fallback: try to get tool list via the list_tools method
            import asyncio
            try:
                loop = asyncio.new_event_loop()
                tools = loop.run_until_complete(mcp.list_tools())
                loop.close()
                tool_names = {t.name for t in tools}
            except Exception:
                pass

        assert "wiki_bootstrap" in tool_names, (
            f"wiki_bootstrap is not registered as an MCP tool. "
            f"Registered tools: {sorted(tool_names)}"
        )

    def test_existing_tools_still_registered(self):
        """After adding wiki_bootstrap, existing tools semantic_search and reindex_anytype must still be registered."""
        from anytype_llm_wiki.server import mcp
        tool_names = set()
        if hasattr(mcp, "_tool_manager") and hasattr(mcp._tool_manager, "_tools"):
            tool_names = set(mcp._tool_manager._tools.keys())
        elif hasattr(mcp, "_tools"):
            tool_names = set(mcp._tools.keys())
        elif hasattr(mcp, "tools"):
            raw_tools = mcp.tools
            if callable(raw_tools):
                raw_tools = raw_tools()
            tool_names = {t if isinstance(t, str) else getattr(t, "name", str(t)) for t in raw_tools}
        else:
            import asyncio
            try:
                loop = asyncio.new_event_loop()
                tools = loop.run_until_complete(mcp.list_tools())
                loop.close()
                tool_names = {t.name for t in tools}
            except Exception:
                pass

        for existing_tool in ("semantic_search", "reindex_anytype"):
            assert existing_tool in tool_names, (
                f"Existing tool '{existing_tool}' is no longer registered after v0.2.0 changes. "
                f"The wiki module is additive — existing tools must not be removed."
            )
