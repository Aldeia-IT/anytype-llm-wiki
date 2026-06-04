# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### User-visible changes

- **`wiki-ingest` command / `wiki_ingest` MCP tool** — compile a source (URL or
  local file) into curated, deduplicated, interlinked wiki Objects with
  provenance. Fetches the source (with SSRF protections), derives entity
  candidates, enriches them via local Ollama extraction (`WIKI_EXTRACT_MODEL`,
  default `qwen2.5:7b`), resolves against existing objects, writes typed
  bidirectional relations, records a WikiLog entry, and auto-reindexes so the
  new knowledge is immediately retrievable via `semantic_search`.
- **Curated wiki knowledge is now searchable** — the chunker embeds designated
  wiki text properties (`wiki_facts`, `wiki_description`, `wiki_definition`, …),
  closing the v0.2.0 gap where property-only objects produced zero chunks and
  were invisible to `semantic_search`.
- **Local-first by default** — extraction targets on-device Ollama; pointing
  `WIKI_EXTRACT_ENDPOINT` at a non-local provider fires a one-time consent
  banner before any source content leaves the machine.

### Internal changes

- Schema bumped to `0.3.0`; `wiki_bootstrap` now stamps `wiki_schema_version` on
  the root Collection (authoritative, with WikiLog fallback) and creates the
  five `wiki_action` select tags — reconciling known-limitations #2 and #3.
- New modules: `wiki/fetch.py`, `wiki/extraction.py`, `wiki/ingest.py`,
  `wiki/prompts/extraction.md`. New dependencies: `markdownify`, `pydantic`.

## [0.2.0] - 2026-05-30

Initial tagged preview release. This marks the start of public semantic
versioning for `anytype-llm-wiki`.

### Added

- **`wiki-bootstrap` command** — provisions the dedicated wiki schema (Types,
  Properties, domain tags, and a root Collection) in an Anytype space. The
  operation is idempotent: it is safe to run repeatedly and reconciles the space
  to the expected schema without creating duplicates, including an in-place
  schema-upgrade path. Flags: `--space-id` (required), `--domain-tags`,
  `--dry-run`, and `--json`.
- **`doctor` command** — a read-only preflight health check that verifies
  connectivity and readiness across the Anytype API, Qdrant, and Ollama, and
  confirms the configured embedding model is available. It changes nothing and
  exits `0` only when every check passes, making it suitable for setup
  validation. Flag: `--json`.
- **Public-release collateral** — security policy (`SECURITY.md`), third-party
  attribution (`NOTICE`), contribution and licensing guidance (`CONTRIBUTING.md`),
  and documentation of the project's supply-chain posture (two-layer dependency
  pinning: exact, hashed versions in `uv.lock` for reproducible installs, with
  compatible ranges declared in `pyproject.toml`).

### Foundation

This release builds on the existing semantic-search foundation:

- The MCP server (run with `anytype-llm-wiki`, no arguments) exposes the
  `semantic_search` and `reindex_anytype` tools to MCP clients such as Claude
  Desktop, Cursor, and Claude Code.
- Indexing is incremental: only objects that changed since the last run are
  re-embedded. Trigger a reindex with the `reindex_anytype` tool (the first
  `semantic_search` also prompts a reindex when the collection is empty).

[Unreleased]: https://github.com/Aldeia-IT/anytype-llm-wiki/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Aldeia-IT/anytype-llm-wiki/releases/tag/v0.2.0
