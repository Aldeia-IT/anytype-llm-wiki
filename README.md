# anytype-rag

Semantic search MCP server for [Anytype](https://anytype.io). Indexes Anytype objects into a vector database and exposes search as an MCP tool for AI assistants.

## How it works

1. Reads objects from the Anytype REST API (markdown bodies)
2. Chunks content by headings/paragraphs
3. Embeds chunks locally via Ollama (bge-m3)
4. Stores vectors in Qdrant
5. Exposes `semantic_search` and `reindex_anytype` as MCP tools

## Prerequisites

- [Anytype](https://anytype.io) desktop or CLI running locally (REST API on port 31012)
- [Ollama](https://ollama.ai) with an embedding model (default: `bge-m3`)
- [Qdrant](https://qdrant.tech) vector database (default: `localhost:6333`)

## Install

```bash
uv tool install .
```

## Configure

Set environment variables:

```bash
# Required
ANYTYPE_API_KEY=<your-anytype-api-key>

# Optional (defaults shown)
ANYTYPE_API_URL=http://127.0.0.1:31012
ANYTYPE_API_VERSION=2025-11-08
QDRANT_URL=http://127.0.0.1:6333
QDRANT_API_KEY=<your-qdrant-api-key>
QDRANT_COLLECTION=anytype_semantic
OLLAMA_URL=http://127.0.0.1:11434
EMBED_MODEL=bge-m3
EMBED_DIMS=1024
INDEX_STATE_DIR=~/.local/share/anytype-rag
```

## Register as MCP server

### Claude Code

```bash
claude mcp add anytype-rag -- anytype-rag
```

Or add to `~/.claude.json`:

```json
{
  "mcpServers": {
    "anytype-rag": {
      "type": "stdio",
      "command": "anytype-rag",
      "env": {
        "ANYTYPE_API_KEY": "<key>",
        "QDRANT_API_KEY": "<key>"
      }
    }
  }
}
```

## MCP Tools

### `semantic_search`

Search Anytype objects by meaning.

- `query` (required): Natural language search query
- `space_id` (optional): Filter to a specific space
- `types` (optional): Filter by object type keys (e.g., `["page", "note"]`)
- `limit` (optional): Max results (default: 10)

### `reindex_anytype`

Trigger incremental reindex of Anytype objects.

- `space_id` (optional): Reindex a specific space. Omit for all spaces.

## License

MIT
