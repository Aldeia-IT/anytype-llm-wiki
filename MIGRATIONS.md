# Migration Guide

This guide describes the steps to take when upgrading between versions of
`anytype-llm-wiki`. Each release that requires action documents its upgrade path
here. Versions not listed require no migration steps.

## Upgrading to v0.2.0

v0.2.0 is the first public release, so there is no prior public version to
migrate **from**. There is, however, a one-time setup step that v0.2.0
introduces, and which every user should follow before indexing.

### 1. Configure your environment

Create a `.env` (or set the equivalent environment variables). At minimum you
need `ANYTYPE_API_KEY`; the Anytype, Qdrant, and Ollama endpoints default to
`localhost`. See the [README](README.md) configuration reference and
[`.env.example`](.env.example) for the full list.

### 2. Provision the wiki schema

Run the bootstrap command to provision the dedicated wiki schema (Types,
Properties, domain tags, and a root Collection) in your Anytype space:

```bash
uv run anytype-llm-wiki wiki-bootstrap --space-id <your-space-id>
```

This command is **idempotent** — it is safe to run on a fresh space or an
existing one, and re-running it will not create duplicates. Add `--dry-run` to
preview the planned changes without calling Anytype, `--domain-tags a,b,c` to
override the default domain-tag taxonomy on first bootstrap, or `--json` for
machine-readable output.

### 3. Confirm the environment is healthy

Run the read-only health check to confirm everything is wired up correctly:

```bash
uv run anytype-llm-wiki doctor
```

`doctor` verifies the Anytype API, Qdrant, Ollama, and embedding-model
availability without modifying anything. It exits `0` only when all checks pass.
Resolve any reported issues before proceeding.

### 4. Run the MCP server

Register the MCP server with your client and let it index your space (the first
`semantic_search` triggers a reindex when the collection is empty; you can also
invoke the `reindex_anytype` tool explicitly). To run the server directly:

```bash
uv run anytype-llm-wiki
```

See the [README](README.md) for client registration (Claude Desktop, Cursor,
Claude Code) and background/auto-reindex setup.

## Upgrading to v0.3.0

v0.3.0 bumps `WIKI_SCHEMA_VERSION` to `0.3.0`. The schema gains the five
`wiki_action` select tag options and moves the authoritative
`wiki_schema_version` marker onto the root Collection. **Re-run
`wiki_bootstrap`** on each existing space before using `wiki_ingest`:

```bash
uv run anytype-llm-wiki wiki-bootstrap --space-id <your-space-id>
```

Bootstrap is idempotent and non-destructive — it adds the new `wiki_action`
tags, stamps `wiki_schema_version=0.3.0` on the root Collection, and preserves
all existing data. Running `wiki_ingest` against a space still on the `0.2.0`
schema returns `[CONFIG ERROR] wiki_schema_outdated` directing you to re-run
bootstrap. No data backfill is required.

### New: content ingestion

```bash
uv run anytype-llm-wiki wiki-ingest --source <url-or-file> --space-id <your-space-id>
```

Extraction runs on local Ollama by default (`WIKI_EXTRACT_MODEL`, default
`qwen2.5:7b`). If you set `WIKI_EXTRACT_ENDPOINT` to a non-local provider, source
content is transmitted off-machine — a one-time consent banner is shown and an
acknowledgement file is written under
`~/.local/share/anytype-llm-wiki/extraction-endpoint-acknowledged-*`.

## Future versions

Migration notes for v0.4.0 and later releases will be appended to this file as
those versions ship. When upgrading, check this guide for any steps that apply
to the version you are moving to.
