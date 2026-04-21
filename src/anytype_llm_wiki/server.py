"""MCP server exposing semantic search and reindex tools."""

from fastmcp import FastMCP

from . import config
from .embedder import embed_query
from .indexer import reindex

mcp = FastMCP("anytype-llm-wiki")


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


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
