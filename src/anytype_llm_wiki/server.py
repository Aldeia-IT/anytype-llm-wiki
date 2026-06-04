"""MCP server exposing semantic search, reindex, and wiki bootstrap tools."""

import sys
from importlib.metadata import PackageNotFoundError, version as _pkg_version

from fastmcp import FastMCP

from . import config
from .embedder import embed_query
from .indexer import reindex
from .wiki.bootstrap import wiki_bootstrap as _wiki_bootstrap

try:
    _VERSION = _pkg_version("anytype-llm-wiki")
except PackageNotFoundError:  # running from a source tree without install metadata
    _VERSION = "0.2.0"

# Report the package version over MCP (serverInfo.version) instead of falling
# back to FastMCP's own version.
mcp = FastMCP("anytype-llm-wiki", version=_VERSION)


@mcp.tool()
def semantic_search(
    query: str,
    space_id: str | None = None,
    types: list[str] | None = None,
    limit: int = 10,
) -> list[dict]:
    """Search Anytype objects by semantic similarity.

    Args:
        query: Natural language search query.
        space_id: Optional space ID to filter results.
        types: Optional list of type keys to filter (e.g. ["page", "note"]).
        limit: Max results to return (default 10).

    Returns:
        List of matching chunks with object name, type, heading, text snippet, and score.
    """
    from qdrant_client import QdrantClient
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    vector = embed_query(query)
    client = QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY or None)

    # Build filter
    conditions = []
    if space_id:
        conditions.append(FieldCondition(key="space_id", match=MatchValue(value=space_id)))
    if types:
        for t in types:
            conditions.append(FieldCondition(key="type_key", match=MatchValue(value=t)))

    search_filter = Filter(must=conditions) if conditions else None

    results = client.query_points(
        collection_name=config.QDRANT_COLLECTION,
        query=vector,
        query_filter=search_filter,
        limit=limit,
        with_payload=True,
    )

    return [
        {
            "object_name": r.payload.get("object_name", ""),
            "object_id": r.payload.get("object_id", ""),
            "type": r.payload.get("type_key", ""),
            "heading": r.payload.get("heading", ""),
            "text": r.payload.get("text", "")[:500],
            "score": round(r.score, 4),
        }
        for r in results.points
    ]


@mcp.tool()
def reindex_anytype(space_id: str | None = None) -> dict:
    """Trigger incremental reindex of Anytype objects.

    Args:
        space_id: Optional space ID to reindex. If omitted, reindexes all spaces.

    Returns:
        Stats: spaces checked, objects indexed, chunks created, objects removed.
    """
    return reindex(space_id=space_id)


@mcp.tool()
def wiki_bootstrap(space_id: str, domain_tags: list[str] | None = None) -> dict:
    """Idempotently create the wiki schema (Types, Properties, tags, Collection) in a space.

    Args:
        space_id: Target Anytype space ID.
        domain_tags: Optional domain-tag taxonomy. On a first bootstrap these
            replace the defaults; on a re-bootstrap they are union-only (existing
            tags preserved, only new tags created).

    Returns:
        A BootstrapResult dict with per-element created/skipped breakdowns, the
        root Collection id + deeplink, a WikiLog id + deeplink, and a status of
        "ok" | "partial" | "error".
    """
    return _wiki_bootstrap(space_id=space_id, domain_tags=domain_tags)


@mcp.tool()
def wiki_ingest(source: str, space_id: str, domain_hint: str | None = None) -> dict:
    """Ingest a source (URL or local file) into the wiki compile pipeline.

    Fetches the source, extracts/derives entities and concepts, resolves them
    against existing wiki objects, creates/updates typed objects (properties
    only, empty body), writes bidirectional relations, records a WikiLog entry,
    and triggers an incremental reindex.

    Args:
        source: An http(s) URL or an absolute local file path.
        space_id: Target Anytype space ID.
        domain_hint: Optional domain tag; must be in the space's taxonomy.

    Returns:
        An IngestResult dict (source/objects created/updated/skipped, relations,
        wiki_log_id, warnings, status).
    """
    from .wiki.ingest import wiki_ingest as _wiki_ingest

    return _wiki_ingest(source=source, space_id=space_id, domain_hint=domain_hint)


@mcp.tool()
def wiki_remember(
    space_id: str,
    knowledge: str,
    subject_hint: str | None = None,
    kind: str | None = None,
    relations: list[dict] | None = None,
    domain_tags: list[str] | None = None,
    source: str | None = None,
) -> dict:
    """Consolidate narrated, conversational knowledge into typed wiki objects.

    Unlike wiki_ingest (which fetches a URL/file), wiki_remember takes an agent's
    natural-language narration and runs the extract -> resolve -> LLM-consolidate
    -> relations -> WikiLog -> reindex pipeline. The consolidation step merges new
    facts into an existing entity/concept's wiki_facts/wiki_definition rather than
    overwriting them: equivalent facts are deduplicated, genuinely new facts are
    added, superseding facts replace old ones (audited in the WikiLog), and
    contradictions are flagged (wiki_status=needs-review, never silently
    overwritten). Re-asserting the same knowledge converges to a no-op.

    Args:
        space_id: Target Anytype space ID (must be bootstrapped at schema >= 0.3.1).
        knowledge: Natural-language narration (non-empty; <= 32000 characters).
        subject_hint: Optional title to seed entity resolution if extraction is empty.
        kind: Optional "entity" or "concept" hint for the subject_hint fallback.
        relations: Optional [{"from", "to", "label"}] links between named subjects.
        domain_tags: Optional domain tags; each must exist in the space taxonomy.
        source: Optional provenance note; "conversation" in it selects the
            conversation source type, otherwise the agent source type is used.

    Returns:
        A dict with source_object_id, per-object results (objects[]),
        relations_created, conflicts_flagged, wiki_log_id, warnings, and a status
        of "ok" | "partial" | "error".
    """
    from .wiki.remember import wiki_remember as _wiki_remember

    return _wiki_remember(
        space_id=space_id,
        knowledge=knowledge,
        subject_hint=subject_hint,
        kind=kind,
        relations=relations,
        domain_tags=domain_tags,
        source=source,
    )


def main():
    # Route known CLI subcommands to the wiki CLI; otherwise run the MCP server.
    from .wiki import cli as wiki_cli

    if len(sys.argv) > 1 and sys.argv[1] in wiki_cli.SUBCOMMANDS:
        sys.exit(wiki_cli.main(sys.argv[1:]))

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
