# Technical Context

## Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| Package manager | uv |
| MCP framework | fastmcp |
| HTTP client | httpx |
| Vector DB client | qdrant-client |
| Embedding | Ollama API (bge-m3, 1024 dims) |
| Anytype API | REST, Bearer token auth |

## Architecture

```
Anytype REST API (port 31012)
        ↓ read objects (markdown bodies)
  Indexer
        ↓ chunk markdown, batch embed
  Ollama/bge-m3 (port 11434)
        ↓ store vectors + metadata
  Qdrant (port 6333, collection: anytype_semantic)
        ↑ query on search
  MCP Server (stdio, fastmcp)
        ↑
  Claude Code / IronClaw
```

## Project Structure

```
anytype-rag/
├── pyproject.toml
├── src/
│   └── anytype_rag/
│       ├── __init__.py
│       ├── server.py           # MCP server entry point + tools
│       ├── anytype_client.py   # Anytype REST API client
│       ├── chunker.py          # Markdown → chunks with metadata
│       ├── embedder.py         # Ollama embedding client
│       └── indexer.py          # Incremental index orchestrator
├── .aldeia/
│   └── context/
└── README.md
```

## Configuration (environment variables)

```
ANYTYPE_API_URL        — Anytype REST API base (default: http://127.0.0.1:31012)
ANYTYPE_API_KEY        — Bearer token for Anytype API
ANYTYPE_API_VERSION    — API version header (default: 2025-11-08)
QDRANT_URL             — Qdrant HTTP endpoint (default: http://127.0.0.1:6333)
QDRANT_API_KEY         — Qdrant API key
QDRANT_COLLECTION      — Collection name (default: anytype_semantic)
OLLAMA_URL             — Ollama API endpoint (default: http://127.0.0.1:11434)
EMBED_MODEL            — Embedding model name (default: bge-m3)
EMBED_DIMS             — Vector dimensions (default: 1024)
INDEX_STATE_FILE       — Path to index state JSON (default: ~/.local/share/anytype-rag/state.json)
```

## Infrastructure (Aldeia IT)

- **Qdrant:** Docker container, v1.17.0, port 6333, API key auth
- **Ollama:** Local, port 11434, bge-m3 model loaded
- **Anytype CLI:** v0.1.12, launchd service, port 31012

## Performance (benchmarked 2026-04-01)

| Operation | Time |
|-----------|------|
| Single query embed | 0.22s |
| Batch 20 chunks | 0.41s |
| Batch 50 chunks | 0.73s |
| Projected full index (500 chunks) | ~7s |

## Deployment

- Install: `uv tool install .` → `~/.local/bin/anytype-rag`
- MCP registration: add to `~/.claude.json` mcpServers
- Auto-reindex: launchd plist on schedule (e.g., every 30 min)
