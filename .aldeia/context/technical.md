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
helper (used by both `reindex` and `reembed_object`). As of `PAYLOAD_SCHEMA_VERSION = 3`
the payload is **up to 9 fields**: the 6 base fields (`object_id`, `space_id`,
`object_name`, `type_key`, `heading`, `text`) plus three optional fields, each written
only when the source object carries the corresponding property:
- `last_modified_date` (ISO-8601 string) — date filter (`ingested_after` /
  `ingested_before`) → Qdrant `DatetimeRange` condition.
- `source_type` (string, from `wiki_source_type` select `name`) — `source_type` filter →
  KEYWORD `MatchAny` condition.
- `domain_tags` (list[str], from `wiki_domain_tags` multi_select `name`s) — `domain_tags`
  filter → KEYWORD `MatchAny` (ANY-overlap) condition.
The chunker extracts these from object properties (tags hydrate with `name` inline — no
id→name resolution at read) and injects them into every chunk; absent properties leave
the key absent from the payload (Qdrant filter-miss-on-absent). A `_payload_schema_version`
marker in the index state file drives a one-time forced full re-embed when the code
version exceeds the stored version, so the new fields are backfilled across the corpus on
the first post-upgrade reindex. NOTE (#336 OD-A, forward-only): the re-embed only carries
`domain_tags`/`source_type` for objects that ALREADY have those Anytype properties — the
original `domain_hint` for pre-#336 objects is recoverable nowhere, so existing objects
are NOT retroactively tagged. Only objects created/updated after the upgrade carry
`domain_tags`; `wiki_source` objects are stamped `source_type` on next ingest/remember.

## Retrieval: hybrid dense + lexical (BM25) fusion (#327)

Retrieval is **hybrid**: the dense (bge-m3 cosine) signal is fused with a lexical
**BM25** signal via app-level **Reciprocal Rank Fusion (RRF, k=60)** in
`indexer.hybrid_search_core` (the shared core behind the `semantic_search` MCP tool
and `wiki_query` Tier-2). The dense path is unchanged (`_dense_search_with_ids`
reuses `semantic_search_core`'s filter construction via the extracted
`_build_search_filter`). The BM25 index is a **lazy, in-memory** `_BM25Index` built
on the first hybrid query after a corpus change or process restart by scrolling
Qdrant. Cross-process freshness is signalled by a monotonic `bm25_corpus_version`
integer stamped into the index state file on every reindex/reembed; the long-lived
server reads it on each query and rebuilds when it changes (the cron reindexes in a
separate interpreter and only bumps the stamp). BM25 failures degrade gracefully to
dense-only; a Qdrant outage on the dense path propagates. `rank-bm25` (Apache-2.0,
numpy-only) is the only new dependency.

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
