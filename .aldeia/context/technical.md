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

## Retrieval: name-aware hybrid search (Aldeia-IT/aldeia-box#327)

`indexer.hybrid_search_core` (behind the `semantic_search` MCP tool and `wiki_query`
Tier-2; `wiki_lint` stays on `semantic_search_core`) runs the dense query first, outside
any `try` (a Qdrant outage propagates). For a scoped call it then fuses the dense list
with the space's **BM25** list by RRF (k=60, keyed on the Qdrant point id, depth
`max(limit * 2, 50)`), applies the **name tier** and scores
`tier_offset (2.0 exact name / 1.0 all words / 0) + first-chunk bonus (0.5) + RRF`, so
the score is monotone with the output order. Non-dense chunks pass the
`types`/`source_type`/`domain_tags` gate in code and are dropped under any date filter.
Unscoped calls (falsy `space_id`) are dense-only.

- **Index:** one `_SpaceIndex` per space in `_bm25_indexes`, built lazily from a Qdrant
  scroll filtered on `space_id` (per-space IDF), under `_bm25_build_lock` (FastMCP runs
  sync tools in a thread pool). It keeps per chunk the point id, a hit payload
  (`text[:500]`, `wiki_url`), `source_type`, `domain_tags`, and a per-object name table.
- **Freshness:** `state.json` key `_bm25_corpus_versions` (`{space_id: int}`), bumped by
  `_run_reindex` for each space it indexed, removed or backfilled in, and by
  `reembed_object` under `_reindex_lock()`. A server rebuilds a space when its on-disk
  version differs from the one it built against.
- **Tokenizer (`_tokenize`):** NFKD fold + casefold, `[a-z0-9]+` joined by `-_.'` (whole
  token plus parts), EN + PT stopwords, no stemming. **Name key (`strip_name`):** fold,
  drop a trailing `(...)`, normalise, drop one leading title word
  (`config.NAME_TIER_TITLE_WORDS`, read at call time; `None` = built-in list).
- Any BM25-side failure (including a missing `rank-bm25`) gives the dense list with
  cosine scores and one WARN `bm25_fallback`.

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
