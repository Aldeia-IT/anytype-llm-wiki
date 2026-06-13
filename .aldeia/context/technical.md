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
anytype-llm-wiki/
├── pyproject.toml
├── src/
│   └── anytype_llm_wiki/
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

## Qdrant chunk payload schema

Each Qdrant point carries a payload built by the shared `indexer._chunk_to_payload`
helper (used by both `reindex` and `reembed_object`). As of `PAYLOAD_SCHEMA_VERSION = 2`
the payload is **7 fields**: the 6 base fields (`object_id`, `space_id`, `object_name`,
`type_key`, `heading`, `text`) plus `last_modified_date` (ISO-8601 string), written only
when the source object carries that date property. The chunker extracts
`last_modified_date` from object properties and injects it into every chunk; the date
filter (`ingested_after` / `ingested_before`) translates to a Qdrant `DatetimeRange`
condition on this field. A `_payload_schema_version` marker in the index state file drives
a one-time forced full re-embed when the code version exceeds the stored version, so the
new field is backfilled across the historical corpus on the first post-upgrade reindex.

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
INDEX_STATE_FILE       — Path to index state JSON (default: ~/.local/share/anytype-llm-wiki/state.json)
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

- Install: `uv tool install .` → `~/.local/bin/anytype-llm-wiki`
- MCP registration: add to `~/.claude.json` mcpServers
- Auto-reindex: launchd plist on schedule (e.g., every 30 min)
