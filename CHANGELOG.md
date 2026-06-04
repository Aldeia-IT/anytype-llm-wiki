# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.1] - 2026-06-04

### User-visible changes

- **`wiki-remember` command / `wiki_remember` MCP tool** (v0.3.1) — consolidate an
  agent's natural-language narration into typed wiki Objects. Runs the local
  extraction stack, resolves each subject, then for existing objects calls a local
  LLM **consolidation** step that merges equivalent facts (no duplicate line),
  appends genuinely new facts, replaces superseding facts (recording the removed
  prior text in the WikiLog for recoverability), and flags contradictions
  (`wiki_status=needs-review`, both facts kept, never silently overwritten).
  Re-asserting identical knowledge converges to a no-op (normalized-text compare).
  Reuses the same model/endpoint/timeout as extraction — no second resident model.
  **Upgrade:** re-bootstrap each space (`wiki-bootstrap --space-id <id>`) to seed
  the new `remember`/`wiki_status`/`wiki_source_type` tags; idempotent and
  union-only, with a clean additive rollback. See the README "Operating notes for
  sustained agent writes" for the auto-reindex cost model, monotonic WikiLog
  growth/pruning, the shared-lock `ingest_in_progress` back-pressure semantics, and
  the as-is `knowledge` storage / notify-once consent caveats.
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

- Schema bumped to `0.3.1`; `wiki_bootstrap` now seeds the `remember` action tag
  (six total), the three `wiki_status` tags (`needs-review`/`reviewed`/`archived`)
  and the three `wiki_source_type` tags (`document`/`conversation`/`agent`).
- Schema bumped to `0.3.0`; `wiki_bootstrap` now stamps `wiki_schema_version` on
  the root Collection (authoritative, with WikiLog fallback) and creates the
  `wiki_action` select tags — reconciling known-limitations #2 and #3.
- New modules: `wiki/remember.py`, `wiki/prompts/consolidate.md` (v0.3.1);
  `wiki/fetch.py`, `wiki/extraction.py`, `wiki/ingest.py`,
  `wiki/prompts/extraction.md`. New dependencies: `markdownify`, `pydantic`.
- `extraction.py` gains `consolidate()` and a `_call_ollama_prompt` helper;
  `_call_ollama` now delegates to it with byte-identical wire behavior.

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

[Unreleased]: https://github.com/Aldeia-IT/anytype-llm-wiki/compare/v0.3.1...HEAD
[0.3.1]: https://github.com/Aldeia-IT/anytype-llm-wiki/compare/v0.3.0...v0.3.1
[0.2.0]: https://github.com/Aldeia-IT/anytype-llm-wiki/releases/tag/v0.2.0
