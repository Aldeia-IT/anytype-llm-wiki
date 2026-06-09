# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.7.3] - 2026-06-09

### Added

- **LLM alias adjudication in entity resolution (`resolve_entity` Step 3) —
  EXPERIMENTAL, off by default.** When exact-title (Step 1) and fuzzy
  `SequenceMatcher` ≥ 0.92 (Step 2) both miss, a local LLM is asked whether the
  candidate denotes the **same real-world entity** as one of the same-type lexical
  search hits — catching aliases / abbreviations / renames that title matching
  can't (e.g. `axedao` → `Axé DAO`). **Enable at your own risk:** even the vetted
  model over-merges distinct entities on real data (~7–10% in a real-graph eval),
  and a merge is destructive. The recommended, non-destructive curation path is
  `wiki_lint --include-duplicates` (human-reviewed suggestions). It is:
  - **Conservative** — returns null unless confident; a part-of / related entity
    stays distinct (`Gnosis Safe` ≠ `Gnosis`, `Finance Agent` ≠ `Finance`), with a
    prompt-injection guard and a hallucinated-id filter (only an id from the
    candidate set can win).
  - **Best-effort** — any LLM/transport/parse failure resolves to *create*; it
    **never blocks ingest** (same posture as contradiction detection). Also runs
    in `wiki_remember`, which shares `resolve_entity`.
  - **Scoped** to `wiki_entity`/`wiki_concept`; `wiki_source` dedup stays
    exact/fuzzy. Candidate pool is the lexical search hits already in hand (no
    extra fetch, no Qdrant dependency); an embedding-neighbour pass remains a
    possible future recall improvement.
- **Model-vetting fail-safe for alias adjudication.** A small model over-merges
  distinct entities, so the feature is **off by default** (`WIKI_ALIAS_ADJUDICATION`,
  default off) and only runs on a **vetted** extraction model (prefix match;
  built-in `qwen3.5-mlx`, extend via `WIKI_ALIAS_VETTED_MODELS` — a comma-separated
  prefix list is the override; there is no force flag). Because the config is fixed
  at start time, **the MCP server refuses to start (exit 2, loud `[CONFIG ERROR]`
  on stderr) when adjudication is enabled on an unvetted model** — not lazily on
  first ingest. `wiki_ingest`/`wiki_remember` keep the same guard at their entry
  for one-shot CLI invocations that bypass server startup.

## [0.7.2] - 2026-06-08

### Fixed

- **`asymmetric_relation` lint no longer false-flags backlink-reachable directed
  edges.** The check confirmed reciprocity by reading the **source** object's
  `backlinks` (plus the target's forward outbound) — but a directed `A → B`
  relation written only on `A`'s forward array surfaces its reverse as an Anytype
  **backlink on `B`**, which the check never read. Result: every healthy directed
  edge whose reverse lived only as a backlink (common on merge-target hub
  entities) was reported as a false Critical. The check now confirms reciprocity
  when the **target** references the source via its `backlinks` **or** its forward
  outbound (the source-side backlink remains an additional signal). Only genuinely
  dangling edges (target gone / no reverse at all) are reported. On a real
  4-document space this took the count from 22 false Criticals to 0.

### Changed

- **Severity recalibration.** `asymmetric_relation` is now **High** (was Critical)
  and `contradiction_unresolved` is now **Critical** (was High) — a semantic
  conflict in asserted knowledge is the most user-visible defect and now outranks
  structural plumbing. (`check` names are unchanged.)
- **Document headings are no longer promoted to wiki objects when LLM extraction
  succeeds.** `wiki_ingest` derived one candidate entity per markdown heading
  (the document title + every section heading like "Overview"/"Open Questions").
  That heading-derived set is now the deterministic **fallback** only: when
  `extract()` returns real entities/concepts, those become the object set and the
  scaffolding is dropped — removing document-structure noise from the graph and
  from dedup. When extraction is unavailable/empty, heading candidates are
  retained, preserving the "works without the LLM" durability guarantee.

## [0.7.1] - 2026-06-08

### Fixed

- **`prune-citations` and `wiki-drain` CLI commands are now reachable.** Both were
  registered in the argument parser in 0.7.0 but omitted from the `SUBCOMMANDS`
  routing gate in `server.main()`, so invoking `anytype-llm-wiki prune-citations`
  / `wiki-drain` silently started the MCP server instead of running the command.
  Added them to the gate, plus a guard test that pins the routing registry to the
  parser's subcommands so the two can't drift again. (v0.7.0 shipped these two
  commands unreachable; use 0.7.1.)

## [0.7.0] - 2026-06-08

### Breaking

- **`wiki_remember` no longer caps at 8 subjects or emits the
  `subject_cap_exceeded` warning.** It now processes *every* extracted subject
  and writes a durable work-log under `WIKI_WORKLOG_DIR`. Anything depending on
  the ≤8-object ceiling or that warning must adapt. (Mechanism under *Changed*.)
- **`wiki_remember` is now queue-submit (no read-after-write); a held lock no
  longer returns `ingest_in_progress`.** A concurrent same-space `wiki_remember`
  now durably queues its subjects and returns `queued_for_drain` (status `ok`)
  instead of erroring; a `wiki_query` issued immediately after may not see the
  just-submitted subjects until they drain. `wiki_ingest` waits (bounded retry)
  instead of failing fast, and only returns `ingest_in_progress` if the lock
  stays held for the whole budget. (Concurrency model under *Changed*.)

### Added

- **Queue-submit concurrency for `wiki_remember`** — independent agents on
  separate PIDs/terminals (a fleet running `/wiki-learn`) writing the *same*
  space no longer block or lose writes. A submit appends its extracted subjects
  to the durable work-log lock-free and returns; whichever PID holds the
  per-space lock drains the queue **drain-until-dry**, sweeping up subjects other
  PIDs appended mid-drain. `wiki_ingest` drains the queue before its own work
  (holding the lock obligates draining). Same-host only — see *Migration* /
  known-limitations §10 for the cross-host constraint.
- **`wiki-drain` CLI command** (`anytype-llm-wiki wiki-drain --space-id <id>`) —
  backstop that drains any queued `wiki_remember` subjects on demand (for the
  pathological case where a submitter crashed between append and drain).
- **`prune-citations` CLI command** (`anytype-llm-wiki prune-citations
  --space-id <id>`) — a one-time, idempotent sweep that removes stale
  `wiki_query` citation edges left in entity/concept relation arrays by old
  file-back. See *Migration* below.

### Migration

- If you ran `wiki_query` file-back on a space **before** this release, run
  `prune-citations` once to clear the stale citation edges (now reported by
  `wiki_lint` as `stale_citation_edge`). Fresh spaces need no action. Full steps
  in [MIGRATIONS.md](MIGRATIONS.md).

### Changed

- **`wiki_remember` no longer silently drops subjects.** Previously a narration
  that extracted more than a fixed number of subjects (a hard `_MAX_SUBJECTS = 8`
  "fan-out cap") had the remainder **truncated and discarded** with only a
  `subject_cap_exceeded` warning — unbounded, irrecoverable data loss with no
  record of *what* was lost, and applied inconsistently (`wiki_ingest` had no
  such cap). The cap is removed. Every extracted subject is now recorded in a
  durable per-space **work-log** (`wiki/worklog.py`) before the drain begins, and
  any subjects left pending by an interrupted run (crash, kill, timeout) are
  folded back in and finished on the next run. Consolidation is idempotent, so
  resuming a partially-applied subject converges to a no-op. **No subject is ever
  dropped.** The work-log is a stdlib-only JSONL file under `WIKI_WORKLOG_DIR`
  (defaults beside the lock dir) — no new runtime dependency and no service.

### Fixed

- **`wiki_query` file-back no longer pollutes the graph with citation edges that
  `wiki_lint` flags as critical.** Filing a query answer back used to write a
  reciprocal back-reference from every cited entity/concept into its
  `wiki_relations`/`wiki_related` set. That conflated "semantically relates to"
  with "was cited by", surfaced query objects as entity neighbours / duplicate
  candidates, and — because the reverse edge lives under a different key
  (`wiki_drew_from`) than lint's symmetry check reads — produced a wave of false
  `asymmetric_relation` findings (one per cited-object × query). File-back now
  writes only the forward `wiki_drew_from` on the query object; the reverse
  "cited by" direction is served by Anytype backlinks (auto-derived).
- **`wiki_lint` no longer false-flags genuinely symmetric relations** when an
  object's `backlinks` list is non-empty but omits the peer. The
  `asymmetric_relation` check now treats backlinks and symmetric-outbound as two
  independent confirmations (either suffices) instead of trusting backlinks
  alone when present.
- **`wiki_lint` duplicate sweep catches real duplicates instead of Query
  objects.** The sweep is now scoped to knowledge objects (entity/concept) — a
  filed Query is never a source or a candidate (and a non-knowledge candidate is
  dropped defensively even if the search backend ignores the type scope) — which
  removes the false-positive class where every filed query looked like a
  near-duplicate of its subject. A new embedding-independent **title pass** flags
  identical normalized titles (including cross-kind entity/concept twins) and
  token-subset pairs ("axe" ⊂ "axe token") that the 0.92 fuzzy threshold and the
  vector pass miss (with a stopword/length floor so generic single-token subsets
  like "the" ⊂ "the project" don't generate noise). Detection only — it never
  mutates.
- **`wiki_lint` flags stale citation edges.** A new `stale_citation_edge` (High)
  check reports entity/concept relations that point at a `wiki_query` object —
  the leftover pollution from old file-back — and no longer double-reports them
  as `asymmetric_relation`. Remediated by `prune-citations` (see *Added*).
- **No-drop work-log hardening.** The first write to a new work-log now fsyncs
  the parent directory (so the new file survives a crash, not just its data);
  `wiki_remember` resume now resolves relation endpoints against existing objects
  so a relation spanning a crash boundary is rewritten rather than lost; and the
  work-log's locking contract (all ops under the per-space lock) is documented.

### Documentation

- Added [`docs/architecture.md`](docs/architecture.md) — the internals/architecture
  orientation for contributors and agents: the write pipeline, consolidation and
  how reality gets corrected, entity-resolution & duplicate handling, the
  concurrency model (and why extraction stays inside the lock, plus the deferred
  blocking-acquire/chunked-release design), the no-drop work-log, the file-back
  citation model, and structural-health checks. `docs/known-limitations.md`
  updated for the cap removal, the new dedup detection, and the lock-fairness
  trade-off.

## [0.6.1] - 2026-06-07

### Fixed

- **Removed a leftover precondition that made the wiki tools unusable for any
  client.** `wiki_ingest`, `wiki_query`, `wiki_remember`, and `wiki_lint` each
  ran a `read_patch_decision()` precheck and hard-failed with
  `[CONFIG ERROR] patch_decision_missing_or_invalid` unless a
  `patch-decision.md` was found in the server's working directory (under
  `$ALDEIA_DIR` or `./.aldeia/140-…/`). That file only exists inside this
  repo's own working tree, so every MCP client running the server from any
  other directory was blocked from all write/query paths. The precheck was a
  `#140` migration-era scaffold that should never have gated normal operation;
  it is now removed from all four tool paths.

## [0.6.0] - 2026-06-06

### User-visible changes

- **Automated cross-object contradiction detection.** On an entity update, the
  `wiki_ingest` pipeline now compares the entity's new facts against the
  `wiki_facts` of its already-linked peer entities via the LLM and records any
  contradiction by setting `wiki_contradictions` **bidirectionally** on both
  objects. Neither object's facts are ever overwritten (both positions are
  retained), and `wiki_last_reviewed` is left null to signal the contradiction
  awaits operator review. The result dict gains a `contradictions_detected` count.
- **`contradiction_unresolved` lint check is now active.** Because the pipeline
  populates `wiki_contradictions`, the `wiki_lint` `contradiction_unresolved`
  (High) check is no longer passive — it fires on auto-detected contradictions.
  The in-product "PASSIVE" caveat is removed from the finding detail and report
  notes.
- **Detection scope limitations (read before trusting a clean result).**
  v0.6.0 detects contradictions between **linked entities only** — contradictions
  between unlinked entities are not yet caught (planned via a semantic
  pre-filter). Detection is **entity-only**; `wiki_concept` scope is deferred. A
  green contradiction column therefore does not guarantee no contradictions exist.
- **Widened off-machine egress disclosure.** Enabling a remote
  `WIKI_EXTRACT_ENDPOINT` now also transmits the `wiki_facts` of already-linked
  peer entities (content distilled from earlier ingests), not only the current
  source. The existing remote-extraction consent gate continues to govern **all**
  off-machine egress including this new peer-fact class; no new gate is added and
  no re-consent is forced (banner copy updated for the widened scope). See the
  README "Privacy and data flow" section.
- **`resumed_partial_ingest` WikiLog marker.** When a re-ingest reuses an existing
  Source object, the WikiLog `notes` now record `resumed_partial_ingest`.

### Internal changes

- No schema change: `WIKI_SCHEMA_VERSION` stays at `0.4.1`. Detection uses the
  existing `wiki_contradictions` / `wiki_last_reviewed` properties; the
  `resumed_partial_ingest` marker is a WikiLog notes string, not a new property.
- Text/relation property readers (`_existing_text`, `_parse_relation_elements`,
  and a new `_relation_ids`) consolidated into `wiki/util.py` to keep the new
  contradiction readers circular-import-safe; `query.py` re-exports
  `_parse_relation_elements`.

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

[Unreleased]: https://github.com/Aldeia-IT/anytype-llm-wiki/compare/v0.6.1...HEAD
[0.6.1]: https://github.com/Aldeia-IT/anytype-llm-wiki/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/Aldeia-IT/anytype-llm-wiki/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/Aldeia-IT/anytype-llm-wiki/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/Aldeia-IT/anytype-llm-wiki/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/Aldeia-IT/anytype-llm-wiki/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/Aldeia-IT/anytype-llm-wiki/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/Aldeia-IT/anytype-llm-wiki/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Aldeia-IT/anytype-llm-wiki/releases/tag/v0.2.0
