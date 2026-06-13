# Product Context

## Elevator Pitch

An MCP server that gives AI assistants semantic search over Anytype vaults — find content by meaning, not just keywords.

## Key Capabilities

| Capability | Description |
|-----------|-------------|
| **Semantic search** | Embed a query, find relevant Anytype objects by vector similarity |
| **Incremental indexing** | Track object timestamps, only re-embed changed/new content |
| **Auto-reindex** | Scheduled background reindexing via launchd/cron |
| **Manual reindex** | MCP tool to trigger reindex on demand |
| **Metadata filtering** | Filter by space and object type, with date-range filtering; tag/source filtering planned (see #336) |

## Product Principles

- **Local-first by default** — all processing happens on-device (Ollama embeddings, Qdrant storage, Anytype API). No cloud dependencies by default. The one explicit opt-in exception is remote LLM extraction via `WIKI_EXTRACT_ENDPOINT` (off by default, on-device Ollama otherwise); pointing it at a non-local endpoint sends fetched source content off-machine and is gated by a first-run consent banner.
- **Zero-config for Aldeia** — works out of the box with our existing infrastructure via environment variables.
- **Configurable for others** — any Qdrant instance, any Ollama-compatible embedding model, any Anytype vault.
- **MCP-native** — designed as an MCP server from the start, not a CLI with MCP bolted on.
