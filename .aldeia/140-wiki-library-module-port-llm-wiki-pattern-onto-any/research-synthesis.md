# Research Synthesis: Wiki Library Module — Port LLM Wiki Pattern onto Anytype

**Date:** 2026-04-13
**Lead:** research-lead
**Ticket:** #140
**Agents dispatched:** technical-researcher, market-researcher

## Executive Summary

The proposed wiki library module — extending anytype-rag from semantic search into an agent-maintained knowledge base using the Karpathy LLM Wiki pattern — is **technically feasible** with the current Anytype REST API (v2025-11-08). The Anytype data model provides structural advantages over every filesystem-based LLM Wiki implementation studied: typed Relations eliminate broken cross-references, closed-option tags enforce taxonomy at the data layer, and native property queries replace file-heuristic lint rules.

The anytype-rag codebase is well-structured and read-only today. Extending it requires adding Anytype write capabilities (object/type/property creation), the ingest pipeline, query pipeline, and lint suite. The existing semantic search and Qdrant indexing integrate with zero code changes for new wiki types — `type_key` filtering is already built in.

Key risks: (1) the Properties API is flagged "experimental" and may have breaking changes, (2) bidirectional relations must be managed at the application layer (no native support), (3) a community report claims PATCH body updates are silently ignored (contradicts API docs — needs verification before spec), and (4) N+1 REST calls for relation neighborhood traversal limits query depth.

The competitive landscape (Zep/Graphiti, Mem0, Letta, MemPalace, A-MEM) validates the approach: all general-purpose agent memory systems lack typed bidirectional relations, closed-option taxonomies, and multi-device sync without cloud — precisely Anytype's native strengths.

## Key Findings

### Finding 1: Anytype API Fully Supports Type Schema Bootstrap
**Source:** technical-researcher
**Implication:** The entire wiki type schema (Source, Entity, Concept, Comparison, Query, WikiLog) can be created programmatically. Types are created via `POST /v1/spaces/{space_id}/types` with linked Properties. Tags for select/multi_select Properties are created inline or via dedicated endpoints. This means the type schema can be versioned in code and bootstrapped per-space — answering the ticket's open question in favor of "code-first."

### Finding 2: "Relations" Are Objects-Format Properties — No Separate Relation Primitive
**Source:** technical-researcher
**Implication:** Anytype's inter-object links are Properties of format `objects`. This is conceptually different from a dedicated relation/edge model. There is no type constraint on targets (any object can be linked), no cardinality enforcement, and no native bidirectional sync. The wiki module must enforce all of these at the application layer. This is workable but adds implementation complexity.

### Finding 3: Bidirectional Relations Require Dual Writes
**Source:** technical-researcher
**Implication:** When Entity A links to Entity B, the ingest pipeline must write the link on both objects. Anytype's read-only `Backlinks` system property tracks inbound links in the UI but is not a reliable programmatic primitive. This doubles write operations and creates a consistency risk: if one write fails, the graph is asymmetric. The ingest pipeline needs atomic-style write-both-or-rollback logic.

### Finding 4: The Hermes Implementation Is the Best Reference — and Its Limitations Are Exactly What Anytype Solves
**Source:** market-researcher
**Implication:** Hermes' llm-wiki skill (PR #5635) is the most complete reference implementation. Its documented limitations — broken wikilinks, freeform tag drift, static index.md maintenance, and session orientation brittleness — map precisely to Anytype's structural advantages. The Hermes design decisions (page thresholds, cross-link minimums, lint severity tiers, contradiction handling) should be carried forward verbatim; only the storage mechanism changes.

### Finding 5: Seven Documented Failure Modes — Anytype Eliminates Three Entirely
**Source:** market-researcher (cross-referenced with technical-researcher)
**Implication:** Of seven failure modes documented across all implementations studied:
- **Eliminated by Anytype:** broken cross-references (Relations use object IDs), schema drift / tag violations (closed-option enforcement), wikilink-as-interface coupling (no string-based linking)
- **Mitigated by Anytype:** stale content (native `updated_at` property queries), session orientation (live Collections replace static index)
- **Not addressed by Anytype:** entity duplication (requires embedding similarity at application layer), information quality degradation (requires source citation enforcement at application layer)

### Finding 6: Semantic Search Integrates with Zero Code Changes
**Source:** technical-researcher
**Implication:** The existing anytype-rag indexer stores `type_key` in Qdrant payloads. `semantic_search` already accepts a `types` filter. Once wiki types are created in Anytype and indexed, `semantic_search(query, types=["entity"])` just works. Embedding refresh on object update is confirmed automatic via timestamp-based incremental indexing.

### Finding 7: No Webhooks — Polling-Based Integration Only
**Source:** technical-researcher
**Implication:** The Anytype API has no event/webhook/SSE mechanism. After the ingest pipeline writes objects, it must explicitly call `reindex_anytype` for near-real-time search freshness. The existing 30-minute launchd schedule handles background updates. This is acceptable but means ingest → query has a manual step.

## Domain Summaries

### Technical

**anytype-rag architecture:** Python MCP server (fastmcp), two tools (`semantic_search`, `reindex_anytype`), read-only Anytype client using REST API at `localhost:31012`. Modular codebase: `anytype_client.py` (REST), `chunker.py` (heading-based markdown splitting, 1500-char max), `embedder.py` (Ollama/bge-m3, 1024-dim), `indexer.py` (incremental with JSON state tracking), `server.py` (FastMCP entry point).

**API surface:** Full CRUD for Objects, Types, Properties, Tags. Search via `POST /v1/search` with FilterExpression (though one source reports this as no-op — needs verification). List-objects with property-predicate query params confirmed working. Auth via bearer token + API version header.

**Key constraints:** Properties API is "experimental." No bidirectional relations. No type constraints on object-property targets. No graph traversal endpoint (N+1 calls). No webhooks. Anytype desktop must be running for API access.

### Market / Prior Art

**Karpathy pattern (original):** Three-layer architecture (immutable raw sources / LLM-maintained wiki / schema config). Core insight: compile knowledge once rather than re-derive per query. ~200 page scale works with index file; beyond that, hybrid retrieval (BM25 + vector + graph) needed.

**Hermes implementation:** Most complete reference. Key design decisions portable to Anytype: page threshold (2+ sources), cross-link minimum (≥2 outbound), severity-graded lint (broken links=critical, orphans=high, stale=medium), contradiction flagging with source preservation, append-only log, mandatory session orientation.

**MemPalace:** Different problem (verbatim conversation replay). Not relevant as a design reference for this module. Notable for metadata-filtering benchmark: structured metadata + hierarchy achieves 94.8% recall vs 60.9% unfiltered.

**Competitive landscape:** Zep/Graphiti (temporal knowledge graph, 63.8% LongMemEval), Mem0 (49.0% LongMemEval), Letta/MemGPT (tiered memory), Cognee (poly-store, air-gapped), A-MEM (Zettelkasten, NeurIPS 2025, 2x multi-hop reasoning gains). All lack Anytype's typed relations, closed-option tags, and native multi-device sync.

**LLM Wiki v2 (community):** Adds confidence scoring, supersession tracking, tiered memory consolidation, and event-driven automation. Worth considering for later iterations but increases complexity beyond the initial scope.

## Risk Assessment

| Risk | Severity | Source | Mitigation |
|------|----------|--------|------------|
| Properties API "experimental" — breaking changes | High | technical-researcher | Idempotent bootstrap that checks for existing properties before creating. Pin API version in client. |
| PATCH body updates silently ignored | High | market-researcher (community report) | **Must verify before spec.** If confirmed, workaround via delete+recreate. Blocks ingest pipeline design. |
| Bidirectional relation consistency | Medium | technical-researcher | Write-both-or-rollback logic in ingest pipeline. Lint rule for asymmetric relations. |
| N+1 REST calls for relation neighborhoods | Medium | technical-researcher | Limit query depth to 1 hop. Cache fetched objects within a pipeline run. |
| Entity duplication (near-duplicates) | Medium | market-researcher | Embedding similarity check (existing anytype-rag) + exact title match before creating. Configurable auto-upsert threshold. |
| Anytype desktop must be running | Low | technical-researcher | Already a constraint for anytype-rag. Mac Mini runs Anytype persistently. |
| No webhooks for real-time sync | Low | technical-researcher | Explicit `reindex_anytype` call post-ingest. Existing 30-min launchd schedule as fallback. |
| FilterExpression may be a no-op | Medium | market-researcher | Verify in testing. Fallback: client-side filtering on list-objects results with property query params. |

## Contradictions and Open Questions

### Contradiction: PATCH Body Updates

The technical researcher documents `PATCH /v1/spaces/{space_id}/objects/{object_id}` as supporting "name, markdown body, icon, type_key, properties" updates. The market researcher found a community report (anytype-mcp-plus v1.1.0) stating "Body (rich text) updates via PATCH are silently ignored in current API."

**Resolution needed:** This must be tested against the actual API before spec writing proceeds. If body updates are silently ignored, the ingest pipeline cannot update Entity/Concept descriptions — a fundamental requirement. Workaround would be delete+recreate, which loses object IDs and breaks all inbound Relations.

### Contradiction: FilterExpression in Search

The technical researcher states `POST /v1/search` with FilterExpression supports property-predicate filtering. The market researcher found a community source noting "TODO: Add support for filters" in the search source code.

**Resolution needed:** Test the actual API. Fallback is property query params on list-objects endpoint, confirmed working.

### Open Questions (from ticket, now informed by research)

1. **One space per wiki domain vs. shared space?** Research supports one-space-per-domain. MemPalace's wing-per-project and Hermes' single-path-per-wiki both validate this isolation. Cross-domain queries go through the query pipeline, not shared graph. **Recommendation: one space per wiki domain.**

2. **Code-first type schema vs. Anytype-first?** API supports full programmatic type creation. **Recommendation: code-first** — enables versioning, cross-space reuse, and idempotent bootstrap.

3. **Auto-upsert vs. always-propose for entity resolution?** Hermes relies on LLM judgment. We have an additional signal: embedding similarity score. **Recommendation: auto-upsert above configurable confidence threshold (e.g., 0.92 exact-title match or 0.85 embedding similarity), propose below.** The threshold should be tunable per space.

4. **Embedding refresh on object update?** **Confirmed:** the existing timestamp-based incremental indexer handles this automatically on next reindex.

## Recommendations

1. **Proceed to product/spec phase.** The module is technically feasible. The Anytype API covers all core requirements. Application-layer workarounds for bidirectional relations and type constraints are well-understood patterns.

2. **Verify the PATCH body update behavior before spec finalization.** This is the single highest-risk technical question. A 15-minute manual API test resolves it. If body updates are broken, the spec must account for delete+recreate semantics (significant complexity increase).

3. **Verify FilterExpression search behavior.** Lower risk — the list-objects endpoint with property query params is a confirmed fallback.

4. **Start with Deliverable 1 (Type Schema) as standalone.** As the ticket suggests, the type schema can be shipped independently to unblock content collection while pipelines are built. The bootstrap script is a natural first PR.

5. **Port Hermes design decisions wholesale.** Page thresholds, cross-link minimums, lint severity tiers, contradiction handling, and append-only logging are battle-tested in Hermes. Adapt the storage mechanism, keep the policies.

6. **Defer LLM Wiki v2 enhancements (confidence scoring, supersession tracking, tiered consolidation) to a follow-up ticket.** These are valuable but increase scope significantly. The base Hermes-parity implementation is the right first target.

## Decision Required

**Should we proceed to spec, and if so, which scope?**

- **Option A (recommended): Full scope spec** — Type schema + ingest pipeline + query pipeline + lint suite. The research validates feasibility for all four deliverables. Single spec, phased implementation (schema first, then ingest, then query, then lint).
- **Option B: Schema-only spec** — Ship the type schema bootstrap as a standalone first ticket. Lower risk, but delays pipeline work and may require re-speccing the schema once pipeline requirements are concrete.
- **Option C: Rework needed** — If PATCH body updates are confirmed broken, the spec needs a fundamentally different approach to object updates (delete+recreate with relation migration). This is doable but significantly more complex.

The PATCH body question (Contradiction #1 above) should be verified before committing to Option A vs Option C. This can be done as a targeted technical test during the product phase or early spec phase.
