# Spec Scope: 323 — Retrieval metadata filters + type/tag scoping

**Ticket:** aldeia-box#323 · **Repo:** anytype-llm-wiki · **Branch:** aldeia/323-retrieval-metadata-filters-type-tag-scoping-for-wi
**Epic:** aldeia-box#140 · **Sibling (deferred fusion half):** #327

## Domains touched
- infrastructure / agent-operations (retrieval, Qdrant vector store, indexer)
- MCP tool surface (`semantic_search`, `wiki_query`)

## Estimated complexity: **moderate** — gated on one scope decision (below)

## Crux: the ticket has an internal contradiction the spec MUST resolve

The ticket assumes "Qdrant already stores this metadata in the payload but it isn't
exposed as a filter." **This is only partially true.** Verified against the codebase:

- The Qdrant payload written by `chunker.chunk_object` + `indexer.reindex`/`reembed_object`
  contains **exactly**: `object_id, space_id, object_name, type_key, heading, text`
  (`src/anytype_llm_wiki/chunker.py:25-94`, `indexer.py:161-168, 218-225`).
- `domain_tags`, `source`, and any **date** field are **NOT** in the payload. They exist
  only as Anytype **object properties** (`wiki_domain_tags` multi_select on source/entity/
  concept; `wiki_ingested_at`/`wiki_source_type` on `wiki_source`; `wiki_last_reviewed`;
  `wiki_asked_at`) — `wiki/types_schema.py:69-154`.
- Therefore **only `type` (type_key) and `space_id` are filterable today.**

This directly contradicts the ticket's own **non-goal** ("Any indexing / payload-schema
change — filter only over already-indexed fields") versus its **acceptance criteria**
(domain_tags + date/source filters; "create payload index if missing"). You cannot index
or filter a payload field that the indexer never writes. The non-goal reflects a mistaken
belief about the current payload; the AC reflects the ticket's actual intent (its title is
literally "type/**tag** scoping").

### Existing precedent (reduces scope for the `type` half)
`indexer.semantic_search_core` **already** builds a Qdrant `Filter` for `space_id` (top-level
`must`) and `types` (nested AND-of-OR `should`), and `semantic_search` **already** exposes
`types`/`space_id` MCP params (`server.py:21-39`). The `type` slice is largely built; gaps
are: exposing scoping on `wiki_query`, payload indexing, input validation, and tests.

### Resolution to put before the spec writer (recommend, with fallback for Decide)
- **Recommended (Option B):** treat an *additive, backward-compatible* payload extension as
  in-scope — have the indexer write `domain_tags` (+ `source`/date where the object carries
  them) into the Qdrant payload, create payload indexes, and require a one-time reindex.
  This honors the ticket's intent/title and full ACs but deviates from the literal non-goal
  → **flag for Jan at the Decide gate.**
- **Fallback (Option A):** ship only `type` + `space` scoping now (honors the literal
  non-goal), defer `domain_tags`/`source`/date filtering to a follow-up that does the payload
  change. Smaller, but misses half the ACs and most of the ticket's value.

The spec should design for Option B with the payload-extension isolated/reversible, present
Option A as the de-scoped fallback, and surface the decision prominently so Jan adjudicates
at Decide.

## Key prior learnings to inject (Mem0)
- **#289 (HIGH):** a spec MUST pin the **wire contract** of every endpoint it calls — exact
  symbol/verb/path + the existing test mock to mirror. Here: pin the precise
  `qdrant_client.models` calls (`Filter`, `FieldCondition`, `MatchValue`, `MatchAny`,
  `Range`/`DatetimeRange`, `create_payload_index` + `PayloadSchemaType`) and mirror the
  `test_indexer.py` fake-client pattern (`upserted_points`, `query_points`).
- **#287 (HIGH):** never assume Anytype **search** responses hydrate property arrays;
  `get_object` is the proven path. The indexer already uses `get_object` — the spec must pin
  how `wiki_domain_tags` (multi_select) and select/date props deserialize from that response.

## CLAUDE.md / docs at risk of staleness if implemented
- No root `CLAUDE.md` in repo. Update `.aldeia/context/technical.md` payload-schema notes,
  README tool docs for `semantic_search`/`wiki_query` filter params, and any
  reindex-required release note (payload change ⇒ reindex).
