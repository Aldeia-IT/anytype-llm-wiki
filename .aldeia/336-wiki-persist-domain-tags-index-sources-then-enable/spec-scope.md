# Spec Scope: wiki-persist-domain-tags-index-sources-then-enable (#336)

**Lead pre-dispatch brief.** Deferred from #323 (OD-2); epic #140. Priority P1.

## What this ticket is
Close the two write-side gaps #323 deferred, then expose the two filters it could not ship:
1. **Persist `wiki_domain_tags`** (multi_select) onto created/updated objects in ingest + remember
   (today: validated, then discarded).
2. **Index source excerpts** — add `wiki_excerpt` to `WIKI_TEXT_PROPERTY_KEYS` so body-less
   `wiki_source` objects produce chunks and reach Qdrant (today: zero chunks → never indexed).
3. **Chunk payload** carries `source_type` + `domain_tags` (tag NAMES).
4. **Indexes + re-index** — KEYWORD payload indexes; bump `PAYLOAD_SCHEMA_VERSION` (#323's marker
   forces the one-time re-embed/backfill).
5. **Expose filters** — `source_type` + `domain_tags` on `wiki_query` and `semantic_search`;
   `domain_tags` is ANY-overlap (`MatchAny`) on the list-valued field.

## Domains touched
- **Primary:** product (a user-facing retrieval-semantics change: sources now appear in
  `semantic_search`) + infrastructure/agent-operations (chunker, indexer, Qdrant payload schema,
  migration).
- **Secondary:** security (egress/local-first unchanged — verify), data-integrity (migration).

## Estimated complexity: **complex**
End-to-end change across write side (ingest+remember), chunker, indexer/migration, Qdrant filter
build, two MCP tool surfaces, plus a one-time Anytype-side backfill and a forced re-embed. Has a
hard upstream dependency (#323) and a genuine product decision.

## HARD DEPENDENCY — #323 must merge first
#323 is **fully implemented and council-approved-to-done on branch
`aldeia/323-retrieval-metadata-filters-type-tag-scoping-for-wi`, but NOT yet merged to main.**
This branch (`aldeia/336-…`) was cut from main and does **not** contain #323's machinery:
`PAYLOAD_SCHEMA_VERSION` (=2 on the 323 branch), `_chunk_to_payload`, `_ensure_payload_indexes`,
the `semantic_search_core` `must`-list filter build, the `wiki_query`/`semantic_search` filter
param threading + validation, and the Tier-1 predicates (`_passes_type_filter`/`_passes_date_filter`).
**The spec MUST be written as an extension of #323's seams** (bump `PAYLOAD_SCHEMA_VERSION` 2→3,
extend `_chunk_to_payload`, `_ensure_payload_indexes`, the filter `must`-list, the param threading)
and MUST state the sequencing constraint explicitly: implementation rebases onto #323
(post-merge to main, or onto the 323 branch). Research reads the **323 branch** code, not main.

## Two design tensions the spec must resolve
1. **Product decision (OD-2 carryover, needs Jan at Decide):** indexing `wiki_excerpt` makes source
   excerpts appear in `semantic_search` (today: only entity/concept/comparison/query). Options:
   (a) include by default; (b) gate behind opt-in / `source_type` scoping so default semantics are
   preserved. Recommend a default-preserving design (e.g. `wiki_query` default `_WIKI_TYPE_KEYS`
   still excludes `wiki_source`; `semantic_search` callers opt sources in/out via `source_type`/
   `types`). Spec presents this as the central Open Decision with a recommendation.
2. **`domain_tags` backfill "where derivable":** existing-corpus objects carry **no recorded
   domain** anywhere (the gap is precisely that it was never persisted). The AC says backfill
   "where derivable" — research must determine whether ANY derivation signal exists (e.g. via the
   source object, wiki_log, or re-extraction). If none, the spec should state the backfill is
   best-effort/forward-only and justify it, rather than pretend a clean migration exists.

## Asymmetry to handle
- `remember.py` **already** writes `wiki_source_type` (select, line 192) and has `_resolve_select_tag`.
- `ingest.py` `_create_source` does **NOT** write `wiki_source_type`. Decide whether ingest sources
  get a source_type (and which value) or are documented as source_type-absent (filter simply won't
  match them — acceptable, not "always empty", because remember sources DO carry it).

## Key prior learnings to inject (Mem0)
- **#287 platform rule (HIGH):** *do not assume Anytype search responses hydrate objects-format
  arrays; `get_object` is the proven path.* → the **mandatory** multi_select GET-shape verification
  must use `get_object` against a live bootstrapped space, never a search response. Throwaway space
  available: `wiki-validation-throwaway` / `wiki-e2e-1` / `llm-wiki-demo`.
- **#323 impl lesson (HIGH):** a new `client.create_payload_index` call breaks older
  `FakeQdrantClient` variants lacking the method — guard with
  `getattr(client, 'create_payload_index', None)`. Applies when extending `_ensure_payload_indexes`.
- **Tier-2 selection:** `wiki_query` takes Tier-2 only when wiki-typed count ≥ `index_threshold()`;
  `index_threshold` lives on `anytype_llm_wiki.wiki.config` (NOT root config) — patch that seam.

## Existing machinery to reuse (don't reinvent)
- `_resolve_select_tag(client, space_id, property_key, tag_name) -> (id, degraded)` (remember.py:124)
  — generalize to a `multi_select` resolver (name→id, degrade-not-abort).
- `_create_tag` / `list_tags` / `_domain_taxonomy` registry pattern (bootstrap.py, remember.py:302).
- select write shape is `{"key": <k>, "select": <tag_id>}` (ingest.py:353) ⇒ multi_select write is
  (to verify) `{"key": "wiki_domain_tags", "multi_select": [<tag_id>, …]}`.
- `#323`: `_chunk_to_payload`, `_ensure_payload_indexes`, `semantic_search_core` filter build,
  Tier-1 predicates, version-marker migration in `reindex`.

## CLAUDE.md / docs at risk of staleness
- `.aldeia/context/technical.md` — payload-schema section (#323 set it to 7 fields incl.
  `last_modified_date`; #336 adds `source_type` + `domain_tags` → document the new field set).
- README tool docs — new `source_type`/`domain_tags` params on `wiki_query`/`semantic_search`.
- Release note — second payload-schema bump + forced re-embed; the new product semantics for sources.

## Out of scope (non-goals)
- `type` + `date` filters (shipped in #323).
- Filtering by exact source URL/file path, or by `wiki_last_reviewed`/`wiki_asked_at`.
