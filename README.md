# anytype-llm-wiki

**The first open-source LLM wiki that uses a typed knowledge-graph store — [Anytype](https://anytype.io)'s native Objects, Types, and Relations — instead of a filesystem of markdown files.**

> **Status — April 2026.** This repo was previously named `anytype-rag` (semantic-search MCP server for Anytype). It is being extended into a full LLM wiki: typed ingest, entity/concept synthesis, bidirectional Relations, lint suite. See [Aldeia-IT/aldeia-box#140](https://github.com/Aldeia-IT/aldeia-box/issues/140) for the roadmap. The current v0.1.0 (semantic search only) is the foundation; the wiki pipeline lands in v0.2.0+.

Anytype's built-in search only matches object titles and snippets. It doesn't search body content at all. This means your AI tools can't find information by *what it says* — only by what it's called.

**anytype-llm-wiki** fixes this. It indexes your Anytype objects into a local vector database and exposes semantic search as an [MCP](https://modelcontextprotocol.io) tool. Your AI assistant can now search your notes, docs, and knowledge base by meaning.

```
You: "What did we decide about the council delegation system?"

anytype-llm-wiki: DAO Governance → The Council (score: 0.57)
  "Research of past DAOs shows that you simply cannot expect all members
   to be engaged constantly in the decision making process. It's better
   to allow a core group of people to step up as delegates..."
```

## How it works (v0.1 — semantic search foundation)

```
Anytype vault (local API)
    ↓  read objects, get markdown
Chunker (split by headings/paragraphs)
    ↓  text chunks with metadata
Ollama (local embeddings, e.g. bge-m3)
    ↓  vectors + payload
Qdrant (vector database)
    ↑  similarity search
MCP Server (semantic_search, reindex)
    ↑  tool calls
Claude Code / Cursor / any MCP client
```

Everything runs locally. No data leaves your machine.

## Quick start

### Prerequisites

- [Anytype](https://anytype.io) desktop (REST API on port 31012) or [anytype-cli](https://github.com/anyproto/anytype-ts/tree/main/dist/cli)
- [Ollama](https://ollama.ai) with an embedding model: `ollama pull bge-m3`
- [Qdrant](https://qdrant.tech): `docker run -p 6333:6333 qdrant/qdrant`

### Install

```bash
# With uv (recommended)
uv tool install anytype-llm-wiki

# With pip
pip install anytype-llm-wiki
```

### Configure

Create a `.env` file or set environment variables:

```bash
# Required
ANYTYPE_API_KEY=your-anytype-api-key    # from Anytype settings → API

# Optional (defaults shown)
ANYTYPE_API_URL=http://127.0.0.1:31012
QDRANT_URL=http://127.0.0.1:6333
QDRANT_API_KEY=                         # if Qdrant requires auth
OLLAMA_URL=http://127.0.0.1:11434
EMBED_MODEL=bge-m3                      # any Ollama embedding model
EMBED_DIMS=1024                         # must match model output
QDRANT_COLLECTION=anytype_semantic
```

### Register as MCP server

**Claude Code:**
```bash
claude mcp add anytype-llm-wiki -e ANYTYPE_API_KEY=your-key -- anytype-llm-wiki
```

**Claude Desktop / Cursor / other MCP clients** — add to your MCP config:
```json
{
  "anytype-llm-wiki": {
    "command": "anytype-llm-wiki",
    "env": {
      "ANYTYPE_API_KEY": "your-key"
    }
  }
}
```

### Index and search

```bash
# First run: index all objects across all spaces
# (subsequent runs are incremental — only changed objects are re-indexed)
```

Once registered, your AI assistant has two new tools (v0.1):

| Tool | Description |
|------|-------------|
| `semantic_search` | Search by meaning. Params: `query`, `space_id?`, `types?`, `limit?` |
| `reindex_anytype` | Trigger incremental reindex. Params: `space_id?` |

The first `semantic_search` call will prompt a reindex if the collection is empty. For background indexing, see [Auto-reindex](#auto-reindex).

## Auto-reindex

For continuous indexing, set up a cron job or launchd service:

**macOS (launchd) — every 30 minutes:**
```bash
cp com.aldeia.anytype-llm-wiki-reindex.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.aldeia.anytype-llm-wiki-reindex.plist
```

**Linux/macOS (cron):**
```bash
# Edit with: crontab -e
*/30 * * * * ANYTYPE_API_KEY=your-key anytype-llm-wiki-reindex
```

## Performance

Benchmarked on a Mac Mini (Apple Silicon):

| Operation | Time |
|-----------|------|
| Single search query | **0.22s** |
| Index 50 chunks | 0.73s |
| Full reindex (500 chunks) | ~7s |

Search is fast enough for interactive use. Indexing is fast enough to run frequently.

## Configuration reference

| Variable | Default | Description |
|----------|---------|-------------|
| `ANYTYPE_API_URL` | `http://127.0.0.1:31012` | Anytype REST API endpoint |
| `ANYTYPE_API_KEY` | *(required)* | Bearer token from Anytype settings |
| `ANYTYPE_API_VERSION` | `2025-11-08` | API version header |
| `QDRANT_URL` | `http://127.0.0.1:6333` | Qdrant endpoint |
| `QDRANT_API_KEY` | *(empty)* | Qdrant API key (if auth enabled) |
| `QDRANT_COLLECTION` | `anytype_semantic` | Qdrant collection name |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama API endpoint |
| `EMBED_MODEL` | `bge-m3` | Ollama embedding model |
| `EMBED_DIMS` | `1024` | Vector dimensions (must match model) |
| `INDEX_STATE_DIR` | `~/.local/share/anytype-llm-wiki` | Where index state is stored |

## Architecture

**Anytype client** — reads objects via the REST API, handles pagination and auth.

**Chunker** — splits markdown by headings (`##`, `###`, `####`), falls back to paragraph splitting for large sections. Each chunk carries metadata: object ID, space ID, object name, type, heading.

**Embedder** — calls Ollama's `/api/embed` endpoint. Supports batch embedding for efficient indexing.

**Indexer** — incremental by default. Tracks `last_modified_date` per object in a JSON state file. Only fetches and re-embeds objects that changed since the last run. Cleans up vectors for deleted objects.

**MCP server** — [FastMCP](https://github.com/jlowin/fastmcp) server exposing `semantic_search` and `reindex_anytype` as tools over stdio.

## Roadmap

v0.1 ships semantic search over Anytype content. v0.2+ extends into a full LLM wiki (see [#140](https://github.com/Aldeia-IT/aldeia-box/issues/140)):

**v0.1 (foundation, shipped)**
- [x] Semantic search via MCP
- [x] Incremental indexing with change detection
- [x] Auto-reindex (launchd/cron)

**v0.2+ (LLM wiki pipeline, in design)**
- [ ] `wiki.bootstrap` — create typed schema (Entity / Concept / Comparison / Query / Source / WikiLog) in an Anytype space
- [ ] `wiki.ingest` — LLM-driven extraction of entities + concepts from source URLs/files, upserted as typed Anytype Objects with bidirectional Relations
- [ ] `wiki.query` — synthesized answer with object citations; optional file-back as a Query object
- [ ] `wiki.lint` — orphans, stale, contradiction drift, oversized objects, tag-taxonomy violations

Longer-term (beyond v0.2):
- [ ] Hybrid search — semantic similarity + keyword matching + metadata filters
- [ ] Cross-space federation with access control
- [ ] Relationship-aware retrieval — follow Anytype Relations to pull connected context
- [ ] Configurable chunking strategies per object type
- [ ] npm / PyPI publishing
- [ ] Webhook-based indexing when Anytype adds webhook support

## Comparison with alternatives

| | anytype-llm-wiki | [wethegreenpeople/anytype-mcp](https://github.com/wethegreenpeople/anytype-mcp) |
|---|---|---|
| Vector DB | Qdrant (production-grade) | ChromaDB |
| Embedding | Any Ollama model (default: bge-m3, multilingual) | mxbai-embed-large |
| Incremental indexing | Yes (timestamp-based) | Full re-embed on start |
| MCP framework | FastMCP v3 | fastmcp |
| Python version | 3.11+ | 3.13+ |
| Package manager | uv / pip | uv |
| Body content search | Yes | Yes |
| **Typed wiki pipeline (v0.2+)** | **Planned** | — |

## Contributing

Contributions welcome! This project is maintained by [Aldeia IT](https://github.com/Aldeia-IT).

```bash
# Clone and set up dev environment
git clone https://github.com/Aldeia-IT/anytype-llm-wiki.git
cd anytype-llm-wiki
uv sync --extra dev

# Create .env with your API keys (see .env.example)
cp .env.example .env

# Run tests (requires Anytype, Ollama, and Qdrant running locally)
uv run --extra dev pytest tests/ -v
```

Areas where help is most welcome:
- **Typed wiki pipeline** (v0.2+) — contributors who have followed Karpathy's LLM-wiki pattern on filesystem will find the design familiar
- **Chunking strategies** for different Anytype object types
- **Hybrid search** implementation (semantic + BM25/keyword)
- **Testing** with large vaults (1000+ objects)
- **Documentation** and examples for different MCP clients

## License

MIT
