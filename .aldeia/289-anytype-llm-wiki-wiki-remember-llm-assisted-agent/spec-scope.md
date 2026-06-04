# Spec Scope: wiki_remember — LLM-assisted agent memory write (#289)

**Version target:** v0.3.1 (depends on #284 v0.3.0; precedes #285 wiki_query).
**Client:** anytype-llm-wiki (Aldeia-IT). Domains: infrastructure, agent-operations.

## Problem (one line)
Agents need an LLM-enhanced memory-write entry point: narrate what was learned in
natural language → extract → resolve against existing objects → **intelligently
consolidate** (merge reworded facts, supersede changed ones, dedupe, flag conflicts)
→ relations → WikiLog → reindex. The LLM consolidation is the whole point; a dumb
append already exists via the `anytype` CRUD MCP.

## Domains touched
- **agent-operations / infrastructure** (primary). No product-UI surface.
- New LLM call (consolidation) on the shared extraction stack (qwen3.5-mlx, think=false).
- Anytype typed-object writes (properties-only PATCH), select-tag pre-creation, reindex.

## Estimated complexity: **moderate**
Near-sibling of the already-shipped `wiki_ingest` pipeline (#284). ~80% reuse:
`extraction.extract`, `ingest.resolve_entity`, `_write_bidirectional_relations`,
`_write_wikilog`, `_domain_taxonomy`, `_create_source`, `_maybe_reindex`, the
patch-decision + schema-compat prechecks, the per-space lock. The genuinely new
surface is the **consolidation step** (new prompt + new deterministic LLM call +
merge/supersede/dedupe/flag logic + the "no material change → skip PATCH" guard) and
the new `remember` WikiLog action tag.

## Reuse map (verified against source — do NOT re-derive)
- `wiki/extraction.py::extract(markdown, space_id)` — best-effort, deterministic
  (`_DETERMINISTIC_OPTS` temp 0/seed 0), graceful degrade, `[CONFIG ERROR] ollama_model_not_pulled`
  short-circuit. Reuse for the entity/concept/fact extraction from `knowledge`.
- `wiki/ingest.py::resolve_entity(client, space_id, type_key, title)` — exact→fuzzy
  (0.92)→(embedding stub) match, **client-side** type filter (API filter is a no-op).
- `wiki/ingest.py::_write_bidirectional_relations` — bidirectional property links w/ rollback.
- `wiki/ingest.py::_write_wikilog` / `_resolve_wiki_action_tag` — WikiLog write + action-tag resolve.
- `wiki/ingest.py::_domain_taxonomy`, `_create_source`, `_maybe_reindex`, `_cmp_versions`.
- Prechecks: `read_patch_decision()` (AC#15), `_bootstrap._read_schema_version` schema-compat (AC-M4).
- `wiki/bootstrap.py::_WIKI_ACTION_TAGS` and `_ensure_wiki_action_tags` (idempotent, union-only re-bootstrap).

## Key schema facts (already in types_schema — no new properties needed)
- `wiki_source` already has **`wiki_source_type`** (select) — provenance (conversation/agent).
- `wiki_entity` / `wiki_concept` already have **`wiki_contradictions`** (objects),
  **`wiki_status`** (select), `wiki_last_reviewed` (date) — the conflict-flag handoff targets.
- `wiki_log` has **`wiki_action`** (select).

## Gaps the spec MUST close (design decisions to firm up)
1. **`remember` action tag missing.** `_WIKI_ACTION_TAGS = [ingest, query, lint, bootstrap, archive]`
   — add `"remember"`. Bootstrap re-run is union-only so existing spaces gain it; `wiki_remember`
   degrades gracefully if the tag is absent (mirror `_resolve_wiki_action_tag`).
2. **`wiki_status` / `wiki_source_type` selects have NO pre-created tags.** Bootstrap only
   seeds `wiki_domain_tags` + `wiki_action`. The conflict review-flag (status) and provenance
   (source_type) need tag values. Decide: which tag values (e.g. status `needs-review`/`conflicted`;
   source_type `conversation`/`agent`/`document`), pre-create them in bootstrap (Decision-3 pattern),
   and degrade gracefully when absent (never abort the write).
3. **Consolidation contract.** New `prompts/consolidate.md` + a deterministic consolidation call
   returning a structured reconciliation (merged facts text + per-fact action merge|supersede|keep|conflict
   + conflict list). Anti-injection framing identical to extraction.md (knowledge is DATA).
4. **"No material change → skip PATCH" idempotency guard** — normalized-text compare of
   consolidated vs existing property; skip the update when unchanged (action=consolidated/no-op).
5. **#287 handoff is flag-only.** #287 (cross-object contradiction detection) is v0.6.0/OPEN/unimplemented.
   #289 only **flags intra-entity conflicts durably** (set `wiki_status`, optionally record on
   `wiki_contradictions`/WikiLog notes/`conflicts_flagged`) — never silently overwrite. No detection engine here.
6. **Optional deterministic structured fast-path** (opt-in when caller passes clean fields) —
   MAY offer; NOT the headline. Spec should state in/out explicitly.

## Result shape (per ticket)
`wiki_remember(space_id, knowledge, subject_hint=None, kind=None, relations=None, domain_tags=None, source=None) -> dict`
returning per-object `action` (created|updated|consolidated), `object_id`, `deeplink`,
`relations_created`, `conflicts_flagged`, `wiki_log_id`, `warnings`, `status`.

## Surfaces to wire
- `server.py` — new `@mcp.tool() wiki_remember(...)`.
- `wiki/cli.py` — new `wiki-remember` subcommand + `SUBCOMMANDS` tuple entry + `_cmd_remember`.
- `wiki/bootstrap.py` — `remember` action tag + status/source_type tag seeding.
- New module `wiki/remember.py` (mirror `ingest.py` orchestration) + `wiki/prompts/consolidate.md`.

## Inherited locked constraints (carry as guard ACs)
- **AC-L1:** properties-only PATCH; body PATCH silently ignored; new objects empty body (AC-P7).
- **AC-L2/SF8:** client-side type filter; no `type_key` FilterExpression.
- Deterministic decoding for reproducible extraction (idempotent re-assert).
- Off-machine consent banner (`check_remote_endpoint_consent`) on the live path before any
  non-local transmit (carried from #284 post-test addendum item 1 — HARD GATE).
- Per-space lock on the entry path (carried from #284 addendum item 2 — HARD GATE).

## Prior-learning injection (Mem0, for downstream test/impl phases)
- respx 0.23.x: use no-arg `respx.get()/post()/patch()` (not `respx.patterns.M`).
- Avoid tautological "local-helper" tests; pair contract test with a `-prod` test on the real path.
- DCG blocks heredoc writes with brace+quote/backtick — write prompt files via Python string accumulation.
- "Specified but not executed" assertion → latent BLOCKING; wire helpers onto the live path + test there.

## Out of scope (per ticket)
Document/URL/file import (#284); cross-object contradiction *detection* (#287); LLM
summarization/compaction of over-large entities (future `wiki_consolidate`); multi-space
federation; bulk backfill.
