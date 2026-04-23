"""Tests for MCP tool registration of wiki_bootstrap — AC #11.

This file is intentionally separate from tests/test_server.py. The v0.1.0
test_server.py file has a module-level autouse fixture (check_services) that
skips every test in the module when Ollama and Qdrant are unreachable. That
means any class added to test_server.py would be silently skipped in CI where
no live services are available.

These tests do NOT require live services. They inspect the FastMCP tool
registry at import time. They will fail with ModuleNotFoundError before
wiki_bootstrap is implemented, and will fail with an assertion error if
wiki_bootstrap is implemented but not registered.
"""

import pytest


class TestWikiBootstrapRegistered:
    """Assert wiki_bootstrap is registered in the MCP server as an @mcp.tool.

    No live services needed. Fails pre-implementation with ModuleNotFoundError
    (anytype_llm_wiki.wiki not yet present). Fails post-stub if wiki_bootstrap
    is not decorated with @mcp.tool in server.py.
    """

    def test_wiki_bootstrap_is_registered_mcp_tool(self):
        """wiki_bootstrap must be registered as an @mcp.tool in server.py."""
        from anytype_llm_wiki.server import mcp
        # FastMCP stores registered tools in _tool_manager or similar.
        # Try several possible attribute paths used across FastMCP versions.
        tool_names = set()
        if hasattr(mcp, "_tool_manager") and hasattr(mcp._tool_manager, "_tools"):
            tool_names = set(mcp._tool_manager._tools.keys())
        elif hasattr(mcp, "_tools"):
            tool_names = set(mcp._tools.keys())
        elif hasattr(mcp, "tools"):
            raw_tools = mcp.tools
            if callable(raw_tools):
                raw_tools = raw_tools()
            tool_names = {
                t if isinstance(t, str) else getattr(t, "name", str(t))
                for t in raw_tools
            }
        else:
            # Fallback: use list_tools() async API
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
        """After adding wiki_bootstrap, existing tools must still be registered.

        wiki_bootstrap is an additive v0.2.0 change; it must not remove or
        shadow the pre-existing semantic_search and reindex_anytype tools.
        """
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
            tool_names = {
                t if isinstance(t, str) else getattr(t, "name", str(t))
                for t in raw_tools
            }
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
                f"The wiki module is additive -- existing tools must not be removed. "
                f"Registered tools: {sorted(tool_names)}"
            )
