"""Call every MCP tool through the FastMCP server with an in-memory client.

Why this exists (Aldeia-IT/aldeia-box#1425): registration tests only inspect the
tool registry; they do not run FastMCP's call path. A FastMCP major bump or a
registration change that breaks tool *calls* must fail CI. Each tool body is
stubbed, so no network, Anytype, Qdrant or Ollama is touched. Lives outside
tests/test_server.py, whose autouse ``check_services`` fixture skips the module
when live services are down.
"""

import asyncio
import importlib

import pytest
from fastmcp import Client

from anytype_llm_wiki import server

EXPECTED_TOOLS = {
    "semantic_search",
    "reindex_anytype",
    "wiki_bootstrap",
    "wiki_ingest",
    "wiki_remember",
    "wiki_query",
    "wiki_lint",
}

# tool name -> (call args, expected keyword args reaching the stub)
CALLS = {
    "semantic_search": ({"query": "q", "space_id": "s"}, {"query": "q", "space_id": "s"}),
    "reindex_anytype": ({"space_id": "s"}, {"space_id": "s"}),
    "wiki_bootstrap": ({"space_id": "s"}, {"space_id": "s"}),
    "wiki_ingest": ({"source": "src", "space_id": "s"}, {"source": "src", "space_id": "s"}),
    "wiki_remember": ({"space_id": "s", "knowledge": "k"}, {"space_id": "s", "knowledge": "k"}),
    "wiki_query": ({"question": "q", "space_id": "s"}, {"question": "q", "space_id": "s"}),
    "wiki_lint": ({"space_id": "s"}, {"space_id": "s"}),
}

# Lazily imported wiki entry points: (module, function); function name == tool name.
LAZY_TARGETS = [
    ("ingest", "wiki_ingest"),
    ("remember", "wiki_remember"),
    ("query", "wiki_query"),
    ("lint", "wiki_lint"),
]


@pytest.fixture
def stubbed(monkeypatch):
    """Replace every tool body with a stub that records its kwargs."""
    calls: dict[str, dict] = {}

    def make_stub(tool: str):
        def stub(*args, **kwargs):
            calls[tool] = kwargs
            if tool == "semantic_search":
                return [{"stub": tool}]
            return {"stub": tool}

        return stub

    monkeypatch.setattr(server, "reindex", make_stub("reindex_anytype"))
    monkeypatch.setattr(server.indexer, "hybrid_search_core", make_stub("semantic_search"))
    monkeypatch.setattr(server, "_wiki_bootstrap", make_stub("wiki_bootstrap"))
    for module, func in LAZY_TARGETS:
        mod = importlib.import_module(f"anytype_llm_wiki.wiki.{module}")
        monkeypatch.setattr(mod, func, make_stub(func))
    return calls


async def _list_tools():
    async with Client(server.mcp) as client:
        return await client.list_tools()


async def _call(name: str, args: dict):
    async with Client(server.mcp) as client:
        return await client.call_tool(name, args)


def test_list_tools_returns_exactly_the_seven_tools():
    tools = asyncio.run(_list_tools())
    assert {t.name for t in tools} == EXPECTED_TOOLS
    assert len(tools) == len(EXPECTED_TOOLS)
    for tool in tools:
        assert isinstance(tool.input_schema, dict)


def test_every_tool_has_a_call_case():
    assert set(CALLS) == EXPECTED_TOOLS


@pytest.mark.parametrize("name", sorted(EXPECTED_TOOLS))
def test_tool_call_goes_through_server_to_stub(stubbed, name):
    args, expected_kwargs = CALLS[name]
    result = asyncio.run(_call(name, args))

    assert not result.is_error
    expected = [{"stub": name}] if name == "semantic_search" else {"stub": name}
    assert result.data == expected
    assert name in stubbed, f"{name} did not reach its stub"
    for key, value in expected_kwargs.items():
        assert stubbed[name][key] == value
