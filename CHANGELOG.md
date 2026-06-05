# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.0] - 2026-06-05

### User-visible changes

- **`wiki-lint` command / `wiki_lint` MCP tool** — a read-only structural health
  check over a bootstrapped wiki space. Params: `space_id`, `severity_threshold?`
  (`all` | `low` | `medium` | `high` | `critical`, default `all`),
  `include_duplicates?` (default `False`). Enumerates the wiki **once** and runs a
  ten-check battery — `asymmetric_relation` (Critical), `orphan` /
  `pipeline_orphan` / `unreviewed_needs_review` / `contradiction_unresolved`
  (High), `stale` / `stale_needs_review` (Medium), `oversized` (Low), and
  `empty_type` / `potential_duplicate` (Informational) — returning a
  severity-ranked LintReport and filing a single `wiki_log` receipt
  (`wiki_action=lint`). The tool mutates nothing else; there is no auto-fix.
- **Duplicate sweep is opt-in.** The `potential_duplicate` Qdrant sweep runs only
  with `--include-duplicates` / `include_duplicates=True`, and is hard-skipped
  above `WIKI_LINT_MAX_OBJECTS`. The advertised ≤60s / ≤500-Object performance
  budget describes the **default sweep-off path**; the opt-in sweep can exceed it.
- **`contradiction_unresolved` is passive in v0.5.0.** `wiki_contradictions` is not
  yet auto-populated (lands in v0.6.0 / #287), so a green contradiction result is
  not a guarantee — the check only fires on manually recorded contradictions.

### Configuration

- Six new optional knobs (sensible defaults; none required):
  `WIKI_LINT_OVERSIZED_CHARS` (2000), `WIKI_LINT_ORPHAN_GRACE_DAYS` (7),
  `WIKI_LINT_STALE_NEEDS_REVIEW_DAYS` (30), `WIKI_LINT_MAX_OBJECTS` (2000),
  `WIKI_LINT_PIPELINE_WINDOW_SECONDS` (300), and `WIKI_LINT_DUPLICATE_MAX_SCORE`
  (0.85, clamped to `[0, 1]`).

### Internal changes

- No schema change: `WIKI_SCHEMA_VERSION` stays at `0.4.1`; `wiki_lint` requires a
  space bootstrapped at the current schema but adds no new Types or Properties.

## [0.4.1] - 2026-06-05

### Internal changes

- **All wiki property display names are now prefixed `Wiki …`** (e.g. `Wiki
  Status`, `Wiki Timestamp`, `Wiki Description`). The bare names (`Status`,
  `Description`, `Timestamp`) collided with Anytype's bundled relations: an
  Anytype native space **export→import silently dropped the colliding
  properties' values** (e.g. every WikiLog `Wiki Timestamp`) by remapping them
  onto the bundled relation. Prefixing every property name makes the schema
  backup/restore-safe and future-proof. Property **keys** (`wiki_*`) are
  unchanged — display-name only. Schema version `0.3.1` → `0.4.1`; re-bootstrap
  each space to adopt the new names (idempotent, additive).

## [0.4.0] - 2026-06-05

### User-visible changes

- **`wiki-query` command / `wiki_query` MCP tool** — query the compiled wiki and
  get a synthesized, source-cited answer. Params: `question`, `space_id`,
  `file_back?`. **Tiered retrieval** picks a strategy by wiki Object count,
  flipping at `WIKI_INDEX_THRESHOLD` (default 200): Tier 1 (index-navigation)
  enumerates the wiki directly below the threshold; Tier 2 (vector-augmented) uses
  semantic search at/above it. Each candidate's 1-hop neighborhood is expanded
  (deduplicated via a per-run object cache), the context is bounded
  (`WIKI_SYNTH_MAX_OBJECTS` / `_MAX_OBJECT_TOKENS` / `_MAX_INPUT_TOKENS`), and a
  local LLM synthesizes a prose answer **only from the retrieved context**, citing
  each Object used. Reuses the extraction model/endpoint/timeout — no second
  resident model.
- **Compounding loop (file-back).** On a clean answer that meets the gate
  (`file_back=True`, or default ≥ `WIKI_FILE_BACK_MIN_SOURCES` cited sources AND
  ≥ `WIKI_FILE_BACK_MIN_WORDS` words), the question/answer is filed back as a typed
  Query Object (`wiki_question`/`wiki_answer`/`wiki_asked_at`/`wiki_drew_from`). On
  the next `reindex_anytype`, the filed answer becomes a Tier-2 retrieval candidate
  for future queries. **Latency caveat:** a filed answer surfaces in retrieval only
  after the next reindex — see `docs/known-limitations.md` §7.
- **Multi-type `semantic_search` fix.** A multi-type `semantic_search` call
  (`types=[...]` with more than one type) previously returned zero results due to
  AND-semantics on the type filter; it now uses a nested AND-of-OR filter ("space
  AND (type ∈ list)"). Single-type behavior is unchanged.
- **New config:** `WIKI_INDEX_THRESHOLD` (200), `WIKI_FILE_BACK_MIN_SOURCES` (3),
  `WIKI_FILE_BACK_MIN_WORDS` (100), `WIKI_SYNTH_MAX_INPUT_TOKENS` (8192),
  `WIKI_SYNTH_MAX_OBJECTS` (24), `WIKI_SYNTH_MAX_OBJECT_TOKENS` (1024). Zero/negative
  values fall back to defaults. No schema bump — `wiki_answer` already exists
  (schema stays `0.3.1`); no re-bootstrap required.

### Security

- `wiki_query` wraps all retrieved Object content and names in a single `<context>`
  fence under a "DATA, not INSTRUCTIONS" preamble; names pass a name-policy filter;
  the question is sanitized before the prompt. No SSRF surface (Objects fetched by
  ID over localhost; only the local Ollama endpoint is called). The file-back loop
  is documented as an injection amplifier, bounded by the clean-synthesis gate plus
  the min-sources/min-words thresholds (README → Prompt injection and the file-back loop).
- Reciprocal relation writes onto pre-existing cited Objects use an explicit
  read-merge-write (`prior ∪ [query_id]`) — never a full overwrite — to avoid
  clobbering an Object's persisted relations.

### Internal changes

- New module `wiki/query.py` (tiered retrieval, 1-hop cache, synthesis transport,
  file-back, WikiLog) and prompt `wiki/prompts/synthesis.md`.
- `indexer.py` gains `semantic_search_core` (the nested-filter search core);
  `server.py`'s `semantic_search` tool now delegates to it.
- `error_category` and the >500-row `filterexpression_fallback` warning are
  surfaced to the operator log stream, not only the per-query result.

### Release checklist (carry-forward, not gated by CI)

- Run the live smoke test once against **real Qdrant v1.17.0** and **Aldeia's own
  vault** before any community tag (internal-dogfood-first) to confirm the
  nested-`should`-in-`must` filter on that Qdrant version and to **pin the live
  relation read-back element shape** (the one wire contract with no read-side code
  to mirror; the dual-shape parser accepts both `"id"` and `{"id": …}` forms).
- Capture the maintainer-measured **p95 < 5s on Mac Mini M4** as an explicit
  release-checklist item (the mocked `test_mocked_query_completes_under_5s` is a
  no-pathology gate, not the production SLO).

## [0.3.1] - 2026-06-04

### User-visible changes

- **`wiki-remember` command / `wiki_remember` MCP tool** — consolidate an
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

### Internal changes

- Schema bumped to `0.3.1`; `wiki_bootstrap` now seeds the `remember` action tag
  (six total), the three `wiki_status` tags (`needs-review`/`reviewed`/`archived`)
  and the three `wiki_source_type` tags (`document`/`conversation`/`agent`).
- New modules: `wiki/remember.py`, `wiki/prompts/consolidate.md`.
- `extraction.py` gains `consolidate()` and a `_call_ollama_prompt` helper;
  `_call_ollama` now delegates to it with byte-identical wire behavior.

## [0.3.0] - 2026-06-04

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
  `wiki_action` select tags — reconciling known-limitations #2 and #3.
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

[Unreleased]: https://github.com/Aldeia-IT/anytype-llm-wiki/compare/v0.4.1...HEAD
[0.4.1]: https://github.com/Aldeia-IT/anytype-llm-wiki/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/Aldeia-IT/anytype-llm-wiki/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/Aldeia-IT/anytype-llm-wiki/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/Aldeia-IT/anytype-llm-wiki/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Aldeia-IT/anytype-llm-wiki/releases/tag/v0.2.0
