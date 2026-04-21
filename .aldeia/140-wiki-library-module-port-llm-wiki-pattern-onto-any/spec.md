---
name: wiki-library-module-port-llm-wiki-pattern-onto-any
status: PRODUCT
issue: 140
repo: aldeia-box
target_repo: anytype-rag
review_rounds: 1
date: 2026-04-14
author: prod-spec-writer agent
---

# Wiki Library Module: Port LLM Wiki Pattern onto Anytype

## Problem Statement

Agents and knowledge workers rediscover the same information repeatedly. Every query to an LLM re-derives facts that were already derived from the same sources. There is no compiled, compounding, interlinked knowledge that carries forward from one session to the next. The result is wasted tokens, inconsistent synthesis, and an ever-growing raw source library that never becomes more queryable over time.

The Karpathy LLM Wiki pattern solves this: compile knowledge once into a structured wiki maintained by the LLM rather than re-deriving it per query. Cross-references, contradictions, and synthesis are materialized at ingest time. Queries then become structured lookups over a growing, interlinked knowledge base rather than expensive from-scratch retrievals.

All seven existing open-source implementations of this pattern (nashsu/llm_wiki, lucasastorian/llmwiki, Ar9av/obsidian-wiki, ScrapingArt/Karpathy-LLM-Wiki-Stack, and three others appearing in the week after Karpathy's April 2026 tweet reached 16 million views) are built on the filesystem + Obsidian stack. Every one of them shares the same structural failure modes: broken cross-references when entity names change, freeform tag drift that erodes taxonomy over sessions, a static index.md that lags behind the actual content, and lint rules that must compensate for what the data layer cannot enforce.

anytype-rag already indexes Anytype objects into Qdrant for semantic search. Anytype's native data model eliminates three of these failure modes at the data layer: typed Relations that use object IDs (not strings) cannot break when an entity is renamed; closed-option tag properties enforced by the API prevent taxonomy drift entirely; and live Collections always reflect the current state of the knowledge base without requiring a maintained index file.

The opportunity is to be, to our knowledge, the first Anytype-native LLM wiki implementation — combining Karpathy's pattern, Hermes' battle-tested operational policies, and Anytype's structural advantages into a publicly installable, community-facing module. (Note: This "first" claim must be verified before the README ships by searching the Anytype community forum, the anytype-mcp repo issues, and GitHub for any prior Anytype-based LLM wiki attempt. If a prior implementation is found, adjust the positioning accordingly.)

**Specific user scenarios that drive this:**

- Jan has ingested 40+ AI research papers into Anytype over 6 months. Asking an agent "how does the attention mechanism in Mamba compare to classic transformers?" currently triggers a cold retrieval from Qdrant. There is no compiled synthesis of this already-read material to draw from.
- An agent supporting Jan's consulting work needs to answer "what is our current position on agentic memory architectures?" but has no persistent knowledge base to consult — only a semantic search over raw objects.
- A community developer landing on the anytype-rag GitHub repo today finds two MCP tools and no path toward structured knowledge management. They want a clean module to try the Karpathy pattern without migrating away from Anytype.

---

## Product Context

**Business goal:** Extend anytype-rag from a utility tool (semantic search) into a knowledge platform with compounding value — where each ingested source makes future queries smarter. Simultaneously, use this as a public signal of Aldeia IT's technical seriousness and community relevance in the growing agent knowledge space.

**Target users:**

- **Primary — Jan (Aldeia IT operator):** Solo technical consultant, Mac Mini M4, already runs anytype-rag. Uses Anytype as primary personal knowledge base. Needs a knowledge system that compounds over time without manual curation overhead. Budget-conscious on hosted LLM tokens — Ollama on local hardware is the default. Comfortable configuring and operating Python MCP servers. Currently lacks a structured way to compile research into a queryable knowledge graph.

- **Secondary — Anytype community developer:** Technically sophisticated user tracking the Anytype ecosystem and the LLM wiki space. Frustrated that every existing implementation assumes Obsidian. Wants a clean, installable module — not a personal script to adapt. Will evaluate the module by reading the README, trying the quick-start, and checking the positioning against known alternatives.

- **Tertiary — Aldeia IT reputation signal (not a user, a product goal):** The anytype-rag repo is public. Visitors should immediately understand the module's value, how to install it, and why Anytype is the right substrate for an LLM wiki.

**User stories:**

- As Jan, I want to ingest a research paper URL and have the module extract entities and concepts, create or update Anytype objects, and wire their relations, so that future queries draw on compiled synthesis rather than raw retrieval.
- As Jan, I want to ask a structured question against my wiki and receive a synthesized answer with citations to specific Anytype objects, so that I can trace the reasoning and jump directly to source material.
- As Jan, I want to run a lint check on my wiki space and see a severity-grouped report with Anytype deeplinks, so that I can identify and fix structural problems (orphans, stale objects, unresolved contradictions) without manually scanning objects.
- As an Anytype community developer, I want to run one command to bootstrap the wiki type schema into my Anytype space and a second command to ingest my first source, so that I can evaluate the module within 15 minutes of `pip install` (with prerequisites already running) on my own data.
- As an Anytype community developer, I want clear documentation explaining how this module compares to Obsidian-based implementations, so that I can make an informed choice about adopting it.
- As Jan, I want to bootstrap a new wiki domain (e.g., "Axé DAO research") into a fresh Anytype space using the same type schema, so that each domain has its own isolated knowledge graph without cross-contamination.

**Success metrics:**

- Bootstrap time: `wiki.bootstrap` completes and creates all schema elements in under 30 seconds on a space with no existing wiki types.
- Quick-start time: A new user with all prerequisites met (Anytype desktop running, Qdrant running, Ollama running with bge-m3 pulled, Python 3.11+) can have the schema bootstrapped and one source ingested in under 15 minutes from `pip install anytype-rag`, following the README alone.
- Object creation accuracy: Ingest pipeline applies the page threshold policy correctly — creates objects for entities mentioned in 2+ sources or central to one source; skips passing mentions. Measurable by running the lint suite's empty-type and orphan checks after ingest.
- Relation integrity: All Relations created by ingest are bidirectional. Zero asymmetric Relations after any ingest run (lint rule: asymmetric Relations = 0).
- Community traction: At least one GitHub star or community post referencing the wiki module from outside Aldeia IT within 30 days of public release.

**Roadmap alignment:** This extends anytype-rag's existing foundation (Qdrant, bge-m3, FastMCP) without replacing or breaking the two current tools (`semantic_search`, `reindex_anytype`). It is additive. The wiki module ships as new MCP tools within the same pip package. It is the first step toward anytype-rag becoming a full knowledge platform rather than a search utility.

---

## User Experience

**Workflows:**

The module has four distinct user-facing workflows, each corresponding to a phase of the wiki lifecycle:

**Workflow 1: Bootstrap a new wiki space**

1. User has an Anytype space designated for a wiki domain (e.g., "AI Research").
2. User runs `wiki.bootstrap(space_id="<id>")` via MCP client or `anytype-rag wiki-bootstrap --space-id <id>` via CLI. Optionally passes `domain_tags` to customize the tag taxonomy for their domain.
3. The tool creates: 6 object Types (Source, Entity, Concept, Comparison, Query, WikiLog), all Properties for each Type, the tag taxonomy as closed-option multi_select properties, and a root Collection.
4. Tool responds with a structured summary listing every object created, every property created, and a confirmation that the schema is ready. Anytype deeplinks to each new Type are included in the response.
5. User opens Anytype and sees the new Types in their space, populated with the correct properties. The wiki is ready to receive content.
6. Bootstrap is idempotent: running it again on a space that already has wiki types skips existing elements (checks by key before creating), creates any missing elements, and reports what was skipped vs. created.

**Workflow 2: Ingest a source**

1. User runs `wiki.ingest(source="https://arxiv.org/abs/2502.12110", space_id="<id>")` or passes a local file path.
2. The tool fetches the source content, creates a Source object in Anytype, runs LLM extraction to identify entities, concepts, and relationships mentioned.
3. For each identified entity/concept, the tool checks Anytype for an existing object (exact title match, then embedding similarity). If found above the auto-upsert threshold, the existing object is updated with new facts and the new Source added to its `sources` relation. If no match, a new object is created if it meets the page threshold policy (2+ source mentions or central to this source).
4. Relations between objects are wired bidirectionally. Each new Entity that relates to existing Entities gets its `relations` property updated; the target Entities get the reciprocal update.
5. A WikiLog entry is created recording the ingest operation (source, objects created, objects updated, timestamp).
6. Tool responds with a structured summary: source object ID + deeplink, list of objects created (with deeplinks), list of objects updated (with deeplinks), list of entities skipped (with reason), count of relations created.
7. User calls `reindex_anytype(space_id="<id>")` after ingest to update the Qdrant index for near-real-time query availability. (This step may be automated by the ingest tool as a post-ingest call if configured.)

**Workflow 3: Query the wiki**

1. User runs `wiki.query(question="How does Mamba's attention mechanism compare to classic transformers?", space_id="<id>")` via MCP client.
2. For wikis under the configured size threshold (default: 200 objects), the tool uses index-navigation mode: queries Anytype Collections by type to identify candidate objects, reads full object content and 1-hop relation neighborhoods.
3. For wikis above the threshold, vector search (bge-m3 + Qdrant) identifies candidate objects first, then full object fetch + 1-hop relation neighborhoods.
4. The tool synthesizes an answer from the fetched content, citing specific objects by title and Anytype deeplink.
5. If the synthesis meets the file-back threshold (default: draws from 3+ objects and produces 100+ words), a Query object is created in Anytype with `drew_from` relations to the cited objects, recording the question, answer, and timestamp.
6. Tool responds with the synthesized answer, a "Sources consulted" section listing object titles and deeplinks, and a note if a Query object was filed back.

**Workflow 4: Lint the wiki**

1. User runs `wiki.lint(space_id="<id>")` via MCP client or CLI.
2. The tool queries Anytype for structural health: orphaned objects (no inbound relations), stale objects (updated_at more than 90 days older than newest related source's ingested_at), objects with unresolved contradiction flags, objects exceeding the size threshold (candidates to split), and types with zero objects (empty Types indicating incomplete schema).
3. Report is returned as a severity-grouped list: critical, high, medium, low, informational.
4. Each item includes: object title, issue description, severity, and Anytype deeplink for immediate navigation.
5. Potential duplicate pairs (objects above embedding similarity threshold but below auto-upsert threshold) are surfaced as a separate section.

**UX implications:** The user's mental model shifts from "I search my Anytype objects" to "I query a compiled knowledge base that understands relationships between topics." The Anytype app becomes the visual browsing surface — the user navigates wiki objects in Anytype the same way they would navigate a wiki, while the MCP tools handle all creation and maintenance. The user should rarely need to manually edit wiki objects.

**Accessibility:** N/A — the module's user-facing surface is MCP tool calls (text-based, no visual interface beyond the Anytype app which has its own accessibility support) and CLI commands.

**Error states and error message design:**

All four tools must distinguish between two error categories with distinct messaging:

| Category | Examples | Message pattern |
|----------|----------|-----------------|
| API errors | Anytype unreachable, auth failure, space not found | `[API ERROR] Could not reach Anytype API at {url}. Ensure the Anytype desktop app is running. Details: {http_status} {message}` |
| Data errors | Entity resolution conflict below threshold, relation type mismatch, PATCH body update failure | `[DATA ERROR] {specific issue}. Suggested action: {action}` |
| Configuration errors | Bootstrap not run in space, missing env vars, invalid space_id | `[CONFIG ERROR] Wiki schema not found in space {space_id}. Run wiki.bootstrap(space_id="{space_id}") first.` |

Ingest partial failures (e.g., 3 of 5 entities created before a failure) must report what completed and what failed, not silently discard partial work. The WikiLog entry should be written even for partial ingests, noting the failure.

---

## Market Analysis

### Competitors and Prior Art

**Karpathy LLM Wiki (original pattern, April 2026)**

The reference pattern from which all implementations derive. Three-layer architecture: immutable raw sources, LLM-maintained wiki markdown files, schema config. Scale claim from the tweet: ~100 articles / ~400K words works without RAG — the LLM reads index files and navigates by structure. File-back of query outputs as a first-class compounding mechanism. Karpathy explicitly identified the gap: "I think there is room here for an incredible new product instead of a hacky collection of scripts."

**Hermes llm-wiki skill (NousResearch, PR #5635)**

The most complete reference implementation. Adds mandatory session orientation (read SCHEMA → index → log before any operation), page lifecycle formalization, severity-graded lint, contradiction handling, and append-only logging. The Anytype wiki module should port Hermes' operational policies wholesale — they are battle-tested design decisions. What changes is only the storage mechanism.

**Community implementations (all filesystem + Obsidian, appearing within one week of Karpathy's tweet):**

- nashsu/llm_wiki (680 stars): basic filesystem implementation
- lucasastorian/llmwiki: MCP-based with full read/write/search tools
- ScrapingArt/Karpathy-LLM-Wiki-Stack: adds qmd semantic search (BM25 + vector + LLM reranking)
- Ar9av/obsidian-wiki: automated cross-linker, delta-driven ingest with `.manifest.json`
- skyllwt/OmegaWiki: most complete (23 Claude Code skills, full research lifecycle), achieves 95.4% on LongMemEval

Every one of these shares the Obsidian dependency and the structural limitations that come with it.

**OMEGA (OmegaWiki)**

The closest benchmark peer to the Anytype approach: compiled wiki + index-based navigation, no embeddings for navigation. Achieves 95.4% on LongMemEval. Confirms that compiled knowledge + index navigation is a viable high-performance alternative to vector retrieval at this scale.

**Supermemory ASMR (experimental)**

Multi-agent orchestrated retrieval achieving ~97-99% on LongMemEval by replacing vector search with active LLM reasoning agents. Relevant as future art for the query pipeline design, not a direct competitor — addresses conversation-history retrieval, not knowledge graph construction. Open-source release announced but not confirmed as of 2026-04-14.

**General-purpose agent memory systems (Mem0, Zep/Graphiti, Cognee, A-MEM):**

These are the broader competitive landscape. None solve the wiki pattern's specific use case. They lack typed bidirectional relations, closed-option taxonomies, and native multi-device sync without cloud dependency — precisely Anytype's strengths.

### Positioning

The anytype-rag wiki module occupies a unique position: it is the only implementation that:
1. Uses a structured typed-object graph rather than markdown files
2. Eliminates broken cross-references and tag drift at the data-model layer rather than through lint rules
3. Provides native multi-device sync (Anytype's E2E encrypted sync) without Obsidian Sync subscription
4. Ships as a pip-installable module with a documented quick-start, not a script to copy

The positioning statement for the README: "To our knowledge, the first Anytype-native LLM wiki — combining Karpathy's pattern, Hermes' battle-tested operational policies, and Anytype's typed knowledge graph into an installable module. Three common LLM wiki failure modes eliminated at the data layer. No Obsidian required."

**Claim verification (required before README publication):** Search the Anytype community forum, the anytype-mcp repo issues/PRs, and GitHub for any prior Anytype-based LLM wiki attempt. If none is found, the "first" claim stands. If one is found, revise the positioning to differentiate on specific features rather than priority.

---

## Research Summary

### Primary findings informing this spec

**The Karpathy pattern is validated and the tooling gap is explicit.** The tweet at 16M views and 7 community implementations in one week confirm strong developer demand. Karpathy himself named the gap: "room for an incredible new product." The Anytype-native angle is differentiated because every community response uses filesystem + Obsidian.

**Hermes' design decisions are the operational blueprint.** Page threshold policy (2+ mentions or central to one source), cross-link minimum (≥2 outbound relations per object), severity-graded lint (critical/high/medium/low), contradiction handling (document both positions, flag for review, never silently overwrite), append-only WikiLog. These are portable verbatim — only the storage mechanism changes.

**Anytype eliminates 3 of 7 documented LLM wiki failure modes at the data layer.** Broken cross-references (Relations use object IDs), schema drift/tag violations (closed-option enforcement), wikilink-as-interface coupling (no string-based linking). Two more are mitigated: stale content (native `updated_at` property queries) and session orientation brittleness (live Collections replace static index.md). Entity duplication and information quality degradation still require application-layer solutions.

**Anytype API supports all required operations.** Full CRUD for Types, Properties, Tags, Objects. Programmatic type schema bootstrap is fully feasible. The existing anytype-rag pipeline integrates with zero code changes for new wiki types via `type_key` filtering already built into Qdrant payloads.

**The PATCH body update risk is the highest-risk technical question.** Community report from anytype-mcp-plus v1.1.0: "Body (rich text) updates via PATCH are silently ignored in current API." This contradicts the official API docs. If confirmed, the ingest pipeline cannot use PATCH to update Entity/Concept descriptions. This must be verified against the live API before implementation begins. The spec designs for both paths.

**Index-navigation is sufficient at personal wiki scale.** Karpathy's own scale claim: ~100 articles / ~400K words works without RAG. OMEGA achieves 95.4% on LongMemEval using compiled wiki + index navigation. The query pipeline should default to index-navigation for small wikis and add vector search as augmentation at medium scale.

**File-back of query outputs is the primary compounding mechanism.** Karpathy: "my own explorations and queries always add up in the knowledge base." This is not an optional log entry — it is the mechanism by which questions improve future answers. The Query type and its `drew_from` relations are a first-class design concern.

---

## Proposed Solution

### Architecture Overview

The wiki module adds four MCP tools and one CLI entry point to the existing anytype-rag package. All wiki tools share a `wiki_client.py` module that extends `anytype_client.py` with write capabilities. The existing `semantic_search` and `reindex_anytype` tools are unchanged.

```
anytype-rag package (after this module)
├── src/anytype_rag/
│   ├── [existing: config.py, anytype_client.py, chunker.py, embedder.py, indexer.py]
│   ├── wiki/
│   │   ├── __init__.py
│   │   ├── wiki_client.py      — Anytype write client (types, properties, tags, objects)
│   │   ├── bootstrap.py        — wiki.bootstrap implementation
│   │   ├── ingest.py           — wiki.ingest implementation
│   │   ├── query.py            — wiki.query implementation
│   │   ├── lint.py             — wiki.lint implementation
│   │   ├── entity_resolver.py  — exact-match + embedding similarity resolution
│   │   ├── policies.py         — page threshold, cross-link minimum, contradiction policy
│   │   └── schema.py           — canonical type/property definitions (the "SCHEMA.md" equivalent)
│   └── server.py               — [modified] adds wiki tools to FastMCP server
```

This is a product-level description of the module's structure. The tech team will finalize the file layout during implementation.

### Type Schema (Deliverable: wiki.bootstrap)

Six types with their properties. All type keys and property keys are prefixed `wiki_` to avoid conflicts with existing space objects.

**Source** — immutable record of a raw input document
- `wiki_url` (url): origin URL if web source
- `wiki_file_path` (text): local file path if file source
- `wiki_excerpt` (text): first 500 characters of content, for quick reference
- `wiki_ingested_at` (date): timestamp of ingest
- `wiki_domain_tags` (multi_select): domain classification tags (closed option set)
- `wiki_source_type` (select): article | paper | transcript | repo | other

**Entity** — a person, organization, product, model, or other named entity
- `wiki_description` (text): synthesized description maintained by the ingest pipeline
- `wiki_facts` (text): bullet-list of key facts, updated on each relevant ingest
- `wiki_relations` (objects): linked Entity or Concept objects (bidirectional)
- `wiki_sources` (objects): Source objects that mention this entity
- `wiki_domain_tags` (multi_select): shared domain tag taxonomy
- `wiki_contradictions` (objects): other Entity/Concept objects with contradicting claims
- `wiki_status` (select): active | archived | stub
- `wiki_last_reviewed` (date): date a human last reviewed this object

**Concept** — a topic, technique, methodology, or abstract idea
- `wiki_definition` (text): synthesized definition
- `wiki_open_questions` (text): unresolved questions flagged during ingest
- `wiki_related` (objects): linked Concept or Entity objects (bidirectional)
- `wiki_sources` (objects): Source objects that discuss this concept
- `wiki_domain_tags` (multi_select): shared domain tag taxonomy
- `wiki_contradictions` (objects): objects with contradicting claims
- `wiki_status` (select): active | archived | stub

**Comparison** — side-by-side analysis of two or more entities or concepts
- `wiki_subjects` (objects): the Entity/Concept objects being compared
- `wiki_dimensions` (text): the comparison axes (structured as markdown table or bullets)
- `wiki_verdict` (text): synthesized conclusion
- `wiki_sources` (objects): Source objects supporting the comparison

*Note:* The Comparison type is not auto-created by the ingest pipeline. Ingest extracts entities and concepts only. Comparisons are created in two ways: (1) manually by the user when they want to compare entities, or (2) by `wiki.query` when a query produces a comparison-style synthesis that meets the file-back threshold. The type is included in v1 because the bootstrap schema should be complete for manual use from day one, and because the query pipeline's file-back mechanism may produce comparison objects. If usage data from Phase 2-3 shows Comparisons remain consistently empty, the type can be reconsidered.

**Query** — a filed synthesis from a wiki.query call (the compounding mechanism)
- `wiki_question` (text): the question asked
- `wiki_answer` (text): the synthesized answer
- `wiki_drew_from` (objects): Entity/Concept/Comparison objects cited in the answer
- `wiki_asked_at` (date): timestamp

**WikiLog** — append-only operational record
- `wiki_action` (select): ingest | query | lint | bootstrap | archive
- `wiki_subject` (text): the source URL, object title, or operation description
- `wiki_objects_created` (number): count of objects created in this operation
- `wiki_objects_updated` (number): count of objects updated
- `wiki_timestamp` (date): operation timestamp
- `wiki_notes` (text): any errors, skips, or noteworthy events

**Tag taxonomy (closed-option, enforced by Anytype API):**

Domain tags (wiki_domain_tags, shared across all types) are configurable at bootstrap time via an optional `domain_tags` parameter. The defaults are:
`wiki_ai-research`, `wiki_infrastructure`, `wiki_business`, `wiki_engineering`, `wiki_governance`, `wiki_science`, `wiki_other`

These defaults reflect Jan's domains. Community users building wikis for other domains (e.g., cooking, law, music) should pass their own tag list at bootstrap:
```
wiki.bootstrap(space_id="<id>", domain_tags=["wiki_cooking-techniques", "wiki_ingredients", "wiki_cuisines", "wiki_other"])
```

If `domain_tags` is not provided, the defaults above are used. Tags created at bootstrap can be extended later by adding new tags via the Anytype API or by re-running bootstrap with an expanded list (bootstrap is idempotent — existing tags are skipped, new ones are created).

The `wiki_` key prefix convention prevents tag collisions with any existing tags in the user's space.

### Ingest Pipeline (wiki.ingest)

**MCP tool signature:**
```
wiki.ingest(
  source: str,           # URL or absolute file path
  space_id: str,         # Anytype space ID
  domain_hint?: str      # optional tag to pre-apply (e.g. "wiki_ai-research")
) -> IngestResult
```

**IngestResult schema:**
```json
{
  "source_object_id": "string",
  "source_object_deeplink": "anytype://object/{space_id}/{object_id}",
  "objects_created": [
    {"title": "string", "type": "entity|concept|comparison", "object_id": "string", "deeplink": "string"}
  ],
  "objects_updated": [
    {"title": "string", "type": "entity|concept|comparison", "object_id": "string", "deeplink": "string", "update_summary": "string"}
  ],
  "objects_skipped": [
    {"name": "string", "reason": "below_threshold|duplicate_proposed|out_of_scope"}
  ],
  "relations_created": 12,
  "wiki_log_id": "string",
  "warnings": ["string"]
}
```

**Ingest pipeline steps:**

1. Fetch source content (URL via httpx, file via local read). Create Source object in Anytype.
   **Supported source types:** Plain text, Markdown, and HTML. For URLs, httpx fetches the page and HTML is converted to markdown (using a library such as html2text or markdownify) before extraction. **Unsupported source types:** PDFs, paywalled articles, and JavaScript-rendered pages (SPAs) are not handled in v1. If a URL serves a PDF `Content-Type`, or if the fetched HTML contains no meaningful text content (common with JS-rendered pages), the ingest tool returns a `[DATA ERROR]` explaining the limitation and suggesting the user provide the content as a local markdown or text file instead. Future versions may add PDF parsing (via pymupdf or similar) and headless browser fetching, but these are out of scope for the initial release.
2. Run LLM extraction prompt against source content. Extract: entities (with descriptions), concepts (with definitions), relationships between extracted entities/concepts. The extraction model is configurable separately from the embedding model (env var `WIKI_EXTRACT_MODEL`, default: same as Ollama instance configured for anytype-rag).
3. For each extracted entity/concept:
   a. Exact title search via Anytype API search endpoint.
   b. If no exact match: embedding similarity check via bge-m3 against existing wiki objects of the same type.
   c. If match above auto-upsert threshold (configurable, default: 0.92 exact-title, 0.85 embedding): update existing object. **Note:** These thresholds are provisional defaults adopted from the research synthesis examples, not empirically validated against bge-m3 similarity data on actual entity pairs. They should be tuned during Phase 2 testing against real ingest data. If 0.85 proves too low (merging distinct entities), raise it; if too high (surfacing too many manual-review proposals), lower it.
   d. If match below auto-upsert threshold: add to `objects_skipped` as `duplicate_proposed`. The user must manually review.
   e. If no match: apply page threshold policy. Create object if entity appears in 2+ sources OR is central to this source. Skip otherwise.
4. Apply cross-link minimum: each new or updated object must have ≥2 outbound wiki_relations before the pipeline completes. If fewer than 2 can be identified from the source, flag in WikiLog `wiki_notes`.
5. Write bidirectional relations: for every A→B relation, also write B→A. If either write fails, roll back both writes and record the failure in the WikiLog.
6. Create WikiLog entry.
7. Call `reindex_anytype(space_id=space_id)` post-ingest (configurable, default: enabled).

**PATCH body update dual-path design (critical):**

The ingest pipeline is designed to handle both confirmed API behaviors:

- **Primary path (PATCH works):** When updating an existing Entity or Concept, use `PATCH /v1/spaces/{space_id}/objects/{object_id}` with the updated description/facts in the body. This is the standard path per the API docs.
- **Fallback path (PATCH body silently ignored):** If the implementation team confirms that PATCH body updates are silently ignored by the current Anytype API version, the pipeline must use Properties-only updates. Specifically: store descriptions and facts in dedicated text Properties (`wiki_description`, `wiki_facts`) rather than the markdown body. PATCH updates to Properties are confirmed to work. The markdown body is treated as a human-readable display surface, not the programmatic data store. This path avoids delete+recreate because that would break all inbound Relations.

The implementation team must test the PATCH body behavior against a live API before choosing the path. This test is a blocking prerequisite for implementing `wiki.ingest`. See Open Questions.

### Query Pipeline (wiki.query)

**MCP tool signature:**
```
wiki.query(
  question: str,         # natural language question
  space_id: str,         # Anytype space ID
  file_back?: bool       # override file-back policy (default: uses configured threshold)
) -> QueryResult
```

**QueryResult schema:**
```json
{
  "answer": "string",
  "sources_consulted": [
    {"title": "string", "type": "entity|concept|comparison|query", "object_id": "string", "deeplink": "string"}
  ],
  "filed_back": false,
  "query_object_id": "string|null",
  "query_object_deeplink": "string|null",
  "retrieval_mode": "index_navigation|vector_augmented"
}
```

**Tiered retrieval strategy:**

- **Tier 1 — index-navigation mode (default for wikis under 200 wiki objects):** Query Anytype Collections/Sets by type to enumerate candidates. Read object descriptions and 1-hop relation neighborhoods directly from Anytype. No Qdrant query needed. Synthesize answer from fetched content. This matches Karpathy's explicit claim that at ~100 articles / ~400K words, index-navigation is sufficient.
- **Tier 2 — vector-augmented mode (default for wikis 200+ wiki objects):** Run `semantic_search(question, types=["wiki_entity", "wiki_concept", "wiki_comparison"])` to identify candidate objects. Fetch full objects + 1-hop relation neighborhoods from Anytype. Synthesize answer. The threshold (200 objects) is configurable via `WIKI_QUERY_INDEX_THRESHOLD`.

**Relation neighborhood traversal:** Limited to 1 hop to avoid N+1 call explosion. For each candidate object, fetch the objects linked in its `wiki_relations`, `wiki_related`, and `wiki_drew_from` properties. Cache fetched objects within the pipeline run to avoid duplicate API calls.

**File-back policy:** A Query object is created when the synthesis draws from 3+ objects AND produces 100+ words. Both thresholds are configurable (`WIKI_FILEBACK_MIN_SOURCES`, `WIKI_FILEBACK_MIN_WORDS`). Users can override per call with `file_back=true` or `file_back=false`.

**Query compounding:** Filed Query objects are indexed by `reindex_anytype` on the next cycle and become available as sources for future queries via `semantic_search`. This is the mechanism by which asking questions improves future answers — a Query about "Mamba vs. Transformers" filed back today makes tomorrow's query about attention mechanisms richer.

**FilterExpression dual-path design:**

The `POST /v1/search` FilterExpression may not be fully implemented (community report: "TODO: Add support for filters" in search source code). The query pipeline should:
- Attempt FilterExpression-based filtering in Tier 1 for performance.
- Fall back to list-objects with property query params and client-side filtering if FilterExpression returns unexpected results (empty or non-filtered results).
- The implementation team must verify FilterExpression behavior during testing. See Open Questions.

### Lint Suite (wiki.lint)

**MCP tool signature:**
```
wiki.lint(
  space_id: str,
  severity_threshold?: str   # "critical"|"high"|"medium"|"low"|"all" (default: "all")
) -> LintReport
```

**LintReport schema:**
```json
{
  "space_id": "string",
  "timestamp": "iso8601",
  "object_counts": {"entity": 0, "concept": 0, "comparison": 0, "query": 0, "wiki_log": 0, "source": 0},
  "findings": [
    {
      "severity": "critical|high|medium|low|informational",
      "check": "orphan|stale|contradiction_unresolved|oversized|empty_type|asymmetric_relation|potential_duplicate",
      "object_title": "string",
      "object_id": "string",
      "deeplink": "anytype://object/{space_id}/{object_id}",
      "detail": "string"
    }
  ],
  "potential_duplicates": [
    {
      "object_a": {"title": "string", "deeplink": "string"},
      "object_b": {"title": "string", "deeplink": "string"},
      "similarity_score": 0.87,
      "recommendation": "review_manually"
    }
  ],
  "summary": {"critical": 0, "high": 0, "medium": 0, "low": 0, "informational": 0}
}
```

**Lint checks, severity, and detection method:**

| Check | Severity | Detection Method |
|-------|----------|-----------------|
| Broken/asymmetric relation (A→B exists, B→A missing) | Critical | Fetch all wiki objects, verify each `wiki_relations` entry has a reciprocal |
| Pipeline orphan (zero relations, created by a failed ingest) | High | Cross-reference WikiLog entries with `wiki_notes` containing failure/partial-failure text against objects created in the same ingest run. Objects created by a pipeline run that logged a partial failure and that have zero `wiki_relations` are flagged immediately (no grace period). |
| Orphan entity/concept (zero inbound relations, manually created or from successful ingest) | High | List objects where `wiki_relations` is empty AND `wiki_ingested_at < now - 7 days`. The 7-day grace period allows time for manually created objects to be wired. |
| Unresolved contradiction (has `wiki_contradictions` entries, `wiki_last_reviewed` null) | High | Filter objects with non-empty `wiki_contradictions` AND null `wiki_last_reviewed` |
| Stale object (updated_at > 90 days older than newest related source's `wiki_ingested_at`) | Medium | Property predicate query: compare `last_modified_date` to `wiki_ingested_at` of linked sources |
| Oversized description (wiki_description or wiki_facts exceeds ~2000 chars) | Low | String length check client-side after fetch |
| Empty type (wiki type defined but zero objects) | Informational | Object count by type_key |
| Potential duplicates (embedding similarity 0.70–0.85) | Informational | Qdrant similarity query against existing wiki object embeddings |

The lint suite leverages Anytype's native property queries rather than file scanning. Anytype's `updated_at` (exposed as `last_modified_date` in the API) is a system property available without any application-layer tracking.

### MCP Tool Interface Design

All four tools share these conventions:

- **Tool naming:** `wiki_bootstrap`, `wiki_ingest`, `wiki_query`, `wiki_lint` (underscores, not dots, as MCP tool names). The dot notation (`wiki.bootstrap`) is used in documentation as a conceptual name.
- **space_id is always explicit:** No ambient global space. Every tool call requires a `space_id`. This supports multiple wiki domains.
- **Anytype deeplinks in all responses:** Format `anytype://object/{space_id}/{object_id}`. Every object reference in a tool response includes its deeplink so the user can jump directly from an MCP response to the Anytype app.
- **Structured return types (JSON-serializable dicts):** Not plain text strings. MCP clients can display these as formatted output.
- **Error category in all errors:** Every exception raised by a wiki tool includes an `error_category` field: `api_error`, `data_error`, or `config_error`.

### Installation and Developer Experience

The wiki module ships as part of the `anytype-rag` pip package — no separate install step:

```bash
pip install anytype-rag
```

After install, the wiki MCP tools are available in the MCP server alongside the existing tools. The CLI commands are also available:

```bash
anytype-rag wiki-bootstrap --space-id <space_id>
anytype-rag wiki-ingest --source https://arxiv.org/abs/... --space-id <space_id>
anytype-rag wiki-lint --space-id <space_id>
```

**Configuration (environment variables):**

| Variable | Default | Purpose |
|----------|---------|---------|
| `WIKI_EXTRACT_MODEL` | value of `OLLAMA_MODEL` | LLM model for entity/concept extraction |
| `WIKI_QUERY_INDEX_THRESHOLD` | 200 | Object count above which query switches to vector-augmented mode |
| `WIKI_FILEBACK_MIN_SOURCES` | 3 | Minimum sources cited to trigger Query file-back |
| `WIKI_FILEBACK_MIN_WORDS` | 100 | Minimum word count of synthesis to trigger file-back |
| `WIKI_AUTO_REINDEX` | true | Whether ingest calls reindex_anytype automatically |
| `WIKI_UPSERT_THRESHOLD_TITLE` | 0.92 | Exact-title match confidence for auto-upsert (provisional — tune during Phase 2) |
| `WIKI_UPSERT_THRESHOLD_EMBEDDING` | 0.85 | Embedding similarity confidence for auto-upsert (provisional — tune during Phase 2) |
| `WIKI_STALE_DAYS` | 90 | Days without update before an object is marked stale |

**README structure (required for community positioning):**

1. What is the Wiki Library Module (1 paragraph — the Karpathy pattern, Anytype-native)
2. Why Anytype? (the structural advantages table vs. filesystem implementations)
3. Prerequisites (required before quick-start): Anytype desktop installed and running, Qdrant running, Ollama running with bge-m3 model pulled, Python 3.11+
4. Quick-start: bootstrap → ingest → query in under 15 minutes (measured from `pip install anytype-rag` with all prerequisites already met)
5. MCP tool reference
6. Configuration reference
7. How this compares to filesystem LLM wikis (explicit positioning section)
8. Operational policies (page threshold, cross-link minimum, contradiction handling, archive workflow)

### Delivery Phases

**Phase 1: Type schema bootstrap (`wiki_bootstrap`)**

Standalone deliverable. Unblocks Jan's content collection while the pipelines are built. Produces the 6 Types, all Properties, and the tag taxonomy in any designated Anytype space. The bootstrap tool is the natural first PR — it has no dependencies on the ingest or query pipelines and immediately provides value by allowing manual content creation with the correct schema.

**Phase 2: Ingest pipeline (`wiki_ingest`)**

Depends on Phase 1 (schema must exist). Core write capability. Includes entity resolver, LLM extraction, relation writing, WikiLog, and post-ingest reindex. The PATCH body update behavior must be verified before Phase 2 begins.

**Phase 3: Query pipeline (`wiki_query`)**

Depends on Phase 1 (schema must exist) and on content existing in the space (from Phase 2 or manual entry). Core read capability. Index-navigation mode first, vector-augmented as follow-up within the same PR or immediately after.

**Phase 4: Lint suite (`wiki_lint`)**

Depends on Phase 1. Can be implemented in parallel with Phase 2 and 3. Standalone maintenance capability.

---

## Resource Impact

**Mac Mini M4 32GB (Jan's primary deployment):**

- **Memory:** The wiki module does not run persistently. Each MCP tool call is a short-lived operation. Peak memory during ingest is dominated by the LLM extraction call (Ollama) and relation neighborhood fetch (object cache). Estimated peak: 200–500 MB additional RAM during active ingest operations. Within normal operating margins for the Mac Mini.
- **CPU:** LLM extraction (Ollama) and bge-m3 embedding calls are the CPU-intensive operations. Ingest of one source: 1-3 minutes elapsed time depending on source length and extraction model. Not a background-continuous load.
- **Disk:** Qdrant index growth is proportional to wiki object count. 1000 wiki objects at 1024 dims per chunk, ~3 chunks per object average: ~12 MB additional Qdrant storage. Well within available disk.
- **Anytype API calls per operation:**
  - **Ingest** of one source: 1 Source create + N entity/concept creates/updates + 2N relation writes (bidirectional) + 1 WikiLog create = approximately 20-60 API calls for a typical article with 8-10 extracted entities.
  - **Query** (index-navigation mode): 1 search/list call to enumerate candidates + K object fetches (K = number of candidates, typically 5-15) + K * M relation-neighborhood fetches (M = average outbound relations per object, typically 2-4) = approximately 15-75 API calls for a typical query. Vector-augmented mode replaces the initial list call with a Qdrant query (not an Anytype API call) but the object fetch and relation traversal counts are similar.
  - **Lint**: 1 list-objects call per wiki type (6 types) + N object fetches for relation verification (N = total wiki objects) = approximately 6 + N API calls. For a 200-object wiki: ~206 calls. For a 500-object wiki: ~506 calls. The implementation should batch and cache aggressively to stay within reasonable run times.
  - All operations use sequential local HTTP calls to the Anytype desktop API. Rate limiting (HTTP 429) is unlikely for local API calls but should be handled gracefully with exponential backoff.
- **Token cost for community users on hosted APIs:** Each ingest call to a hosted LLM for extraction costs 2,000–8,000 tokens for a long article. For Jan on Ollama: compute time only (no monetary cost). For community users on hosted APIs (OpenAI, Anthropic): real cost. The configurable `WIKI_EXTRACT_MODEL` allows using a smaller, cheaper model for extraction (e.g., a smaller Ollama model) while using a larger model for query synthesis. Documentation must call this out explicitly.

---

## Security Considerations

**Data locality:** The wiki module reads and writes only to the user's own Anytype space via the local API (`localhost:31012`). No external data transmission occurs except for URL fetching during ingest (the source URL is fetched via httpx). All vector data stays in the local Qdrant instance.

**Auth:** The existing anytype-rag bearer token mechanism is used unchanged. The wiki module inherits the same auth model — no new credentials are introduced.

**PII handling:** If a user ingests sources containing personal information (emails, conversations, personal notes), that content is extracted into Entity/Concept descriptions and stored in Anytype. This is by design — the wiki is a personal knowledge base. The module makes no special PII classification. Users are responsible for curating what sources they ingest. This should be noted in the README.

**Source URL fetching:** During ingest, the source URL is fetched using httpx. The module should respect standard http proxy settings and not follow suspicious redirects. URL fetching is the only network egress beyond the local Anytype and Qdrant APIs.

**Anytype desktop as a dependency:** The Anytype API runs only when the Anytype desktop app is active. For Jan's Mac Mini, this is already managed. For community deployments, this is a runtime dependency that users must understand. The README must document it explicitly.

**API token scope:** The wiki module requires write access to the Anytype API. Whether the existing anytype-rag bearer token (currently used only for read operations) also covers write operations is unresolved (see Open Question #6). Phase 1 implementation must verify this as its first step: attempt a write operation (e.g., creating a test type) with the existing token. If the existing token covers writes, no configuration change is needed. If writes require a different token or re-authentication with broader scope, the quick-start and configuration guide must document the additional token setup step.

---

## Success Criteria

**Phase 1 (Bootstrap):**
- `wiki_bootstrap` creates all 6 Types, all Properties, the tag taxonomy, and a root Collection in a clean Anytype space in under 30 seconds.
- Running `wiki_bootstrap` on a space that already has wiki types produces no duplicates and reports correctly what was skipped vs. created.
- A community user following the README quick-start can bootstrap a wiki space without reading any code.

**Phase 2 (Ingest):**
- `wiki_ingest` correctly applies the page threshold policy: creates objects for entities mentioned in 2+ sources or central to one source; records skips for passing mentions.
- All Relations created by ingest are bidirectional (lint check: asymmetric Relations = 0 after any ingest run).
- A partial ingest failure (Anytype API error mid-pipeline) leaves a coherent WikiLog entry and does not silently lose the entities that were successfully created.
- `wiki_ingest` of the same source twice produces no duplicate objects (idempotent above the auto-upsert threshold).

**Phase 3 (Query):**
- `wiki_query` returns a synthesized answer with citations to specific Anytype objects and deeplinks within 30 seconds for a wiki under 200 objects.
- Query objects that meet the file-back threshold appear in Anytype after the call.
- `wiki_query` on a space where bootstrap has not been run returns a clear `config_error` with instructions.

**Phase 4 (Lint):**
- `wiki_lint` identifies orphaned objects (zero inbound relations after more than 7 days), reports them at High severity with deeplinks.
- `wiki_lint` identifies asymmetric relations and reports them at Critical severity.
- `wiki_lint` runs in under 60 seconds for a wiki with fewer than 500 objects.

**Community positioning:**
- The README "Why Anytype?" section clearly differentiates the module from filesystem implementations with the structural advantages table.
- Quick-start (bootstrap → first ingest → first query) can be completed in under 15 minutes by a new user on a clean Anytype space, measured from `pip install anytype-rag` with all prerequisites already met.

**Evaluation timing:** Phase 1 criteria evaluated at first PR review. Phase 2-4 criteria evaluated at implementation completion. Community positioning evaluated by Jan's review of the README before merge.

---

## Test Plan

Acceptance tests at the user level. Implementation team adds unit and integration tests.

**Bootstrap:**
- User runs `wiki_bootstrap` on a clean Anytype space → 6 Types appear in the space, each with correct properties → response includes deeplinks to each Type.
- User runs `wiki_bootstrap` again on the same space → no duplicate Types or Properties created → response reports each element as "already exists, skipped."
- User runs `wiki_bootstrap` with an invalid space_id → receives `[CONFIG ERROR]` response with the space_id echoed back and a hint to check the space exists.
- User runs `wiki_bootstrap` when Anytype desktop is not running → receives `[API ERROR]` response with clear instructions to start Anytype.

**Ingest:**
- User runs `wiki_ingest(source="https://arxiv.org/abs/2502.12110", space_id=<id>)` → Source object created → at least one Entity and one Concept object created → relations wired → WikiLog entry created → response includes deeplinks to all created objects.
- User runs `wiki_ingest` with the same URL twice → second run updates existing objects rather than creating duplicates → `objects_created` count = 0, `objects_updated` count ≥ 1.
- User runs `wiki_ingest` on a source with only passing mentions of entities already in the wiki → `objects_skipped` list is non-empty with `reason: below_threshold` → no new objects created for those entities.
- User checks Anytype after ingest → an Entity A that links to Entity B via `wiki_relations` → Entity B also shows Entity A in its `wiki_relations` (bidirectional confirmed).
- User runs `wiki_ingest` when Anytype API returns a 500 error during relation writing → receives partial ingest report with entities successfully created and a failure note → WikiLog entry created with `wiki_notes` describing the failure.

**Query:**
- User runs `wiki_query(question="What is bge-m3?", space_id=<id>)` on a wiki containing an Entity "bge-m3" → response includes a synthesized answer and a deeplink to the bge-m3 Entity object.
- User runs `wiki_query` on a wiki with fewer than 200 objects → `retrieval_mode` in response is `"index_navigation"`.
- User runs `wiki_query` with a question that draws from 3+ objects and produces 100+ words → `filed_back: true` in response → Query object appears in Anytype with `wiki_drew_from` relations to the cited objects.
- User runs `wiki_query` on a space where `wiki_bootstrap` has not been run → receives `[CONFIG ERROR]` explaining the bootstrap requirement.

**Lint:**
- User manually creates an Entity object with zero relations in a wiki space → waits 7+ days (or simulates by adjusting `wiki_ingested_at`) → runs `wiki_lint` → the Entity appears in findings at High severity (orphan) with a deeplink.
- An ingest run partially fails (simulated by interrupting API calls mid-pipeline), leaving 2 entities created but relations not wired → WikiLog records the partial failure → user runs `wiki_lint` immediately (no 7-day wait) → both entities appear as High severity pipeline orphans, referencing the WikiLog entry that recorded the failure.
- User ingest creates Entity A linked to Entity B, but the reciprocal B→A was never written (simulated by manual edit) → `wiki_lint` reports this as Critical severity (asymmetric relation) with deeplinks to both objects.
- User runs `wiki_lint` on a space where Anytype has been offline for 90 days (simulated by setting `last_modified_date` on objects) → objects not updated within the staleness threshold appear in findings at Medium severity.
- User runs `wiki_lint` with `severity_threshold="critical"` → response only contains Critical findings.
- User runs `wiki_lint` on a space with fewer than 500 wiki objects → response is returned in under 60 seconds.

---

## Open Questions

1. **PATCH body update behavior (BLOCKING for Phase 2).** The ingest pipeline is designed for both paths (PATCH vs. Properties-only), but the implementation team must verify actual behavior against the live Anytype API before implementing `wiki_ingest`. Specifically: does `PATCH /v1/spaces/{space_id}/objects/{object_id}` with a markdown body update the visible content of the object, or is the body silently ignored? If ignored, the Properties-only path (storing descriptions in `wiki_description` and `wiki_facts` text properties) is the implementation path. This test should be the first action taken when Phase 2 implementation begins. **See Appendix A for the concrete verification protocol.**

2. **FilterExpression in search (BLOCKING for Phase 3 Tier 1).** The `POST /v1/search` FilterExpression may be a no-op based on community source code analysis. The query pipeline's index-navigation mode uses this for type filtering. Implementation team must verify before relying on it. Fallback: list-objects with property query params and client-side filtering (confirmed working). **See Appendix A for the concrete verification protocol.**

3. **Extraction model default.** `WIKI_EXTRACT_MODEL` defaults to the same model configured for anytype-rag (Ollama). What model should the quick-start documentation recommend for community users who may be using a hosted API? This is Jan's call — the spec documents the configurable behavior but does not prescribe the default for hosted users.

4. **File-back threshold for Query objects.** Default: 3+ sources AND 100+ words. Is this the right default? Too aggressive (filing too much) makes the wiki noisy; too conservative (filing too little) defeats the compounding mechanism. Recommend Jan tests this with the initial wiki deployment and adjusts the configurable values.

5. **Community branding.** Should this be "anytype-rag wiki module" or merit a distinct product name (e.g., "Anytype LLM Wiki" or "Anytype Knowledge Library")? A distinct name is more memorable and community-searchable but adds fragmentation risk. Jan's call.

6. **Write token permissions.** The anytype-rag bearer token currently has read scope. Does bootstrapping and ingesting require generating a new write-scoped token, or does the same token cover write operations? The implementation team must verify against the Anytype auth API and document the setup in the README accordingly.

7. **Backlinks queryability via REST API.** The Anytype UI shows a system `Backlinks` property (read-only, auto-populated). Can the lint suite use this via the REST API to verify inbound relation counts without fetching all linked objects? If queryable, orphan detection becomes cheaper (one API call vs. N calls). Implementation team to verify.

---

## Deferred Items

**Multi-space / federated wiki queries.** Cross-domain synthesis across multiple Anytype spaces. The one-space-per-wiki-domain model is the explicit v1 design. Cross-domain queries require a federated search layer not warranted for v1. Filed as a follow-up ticket.

**LLM Wiki v2 enhancements (confidence scoring, supersession tracking, tiered consolidation).** Karpathy's community has developed extensions to the base pattern: confidence decay, explicit fact supersession, tiered memory consolidation. These increase implementation scope significantly. The base Hermes-parity implementation is the correct first target.

**ASMR-style multi-agent retrieval for the query pipeline.** Supermemory's ASMR technique (3 parallel ingestion agents + 3 parallel search agents + 8-12 answering variants) achieves ~97-99% on LongMemEval. This approach is relevant future art for the query pipeline. The query pipeline is designed pluggably (single-LLM synthesis today, agentic multi-LLM in a future iteration). The ASMR open-source code, once released, should be reviewed for the ingestion agent knowledge extraction architecture.

**Synthetic data generation and finetuning.** Karpathy explicitly names this as the natural next step after a wiki grows: generating question-answer pairs from wiki objects for model finetuning. Out of scope for this ticket. The Anytype typed-object model preserves provenance metadata that would support this in a future iteration.

**Visual output formats (Marp slides, matplotlib charts).** Karpathy's implementation supports rendering query outputs as slide decks and charts. Anytype's native UI is the v1 browsing surface. Rich output types are a follow-up.

**Auto-merge entity dedup below the confidence threshold.** The module surfaces potential duplicate Entity pairs (above similarity threshold but below auto-upsert threshold) for user review. Auto-merge above a configurable threshold is an ingest option — below threshold, the user must make the call. Full automated dedup below the confidence threshold is deferred.

**Real-time webhook-based embedding refresh.** Anytype has no webhooks. The explicit post-ingest `reindex_anytype` call and the 30-minute launchd schedule are sufficient for v1. Webhook support would be an Anytype platform feature, not something this module can provide.

**`wiki.status(space_id)` lightweight health check tool.** A fast status command returning object counts by type, last ingest timestamp, and any critical lint findings would be useful for daily operations. `wiki.lint` is comprehensive but potentially slow (up to 60 seconds for 500 objects). Deferred because v1 already provides `wiki.lint` with `severity_threshold="critical"` as a partial substitute, and adding a fifth MCP tool increases the surface area before the core four are validated. Should be reconsidered after Phase 4 ships if lint performance is an issue for daily use.

---

## Appendix A: API Verification Protocols

These are copy-pasteable curl commands that the implementation team must run against a live Anytype API instance as blocking prerequisites. Each test includes the expected response for both the "works" and "does not work" outcomes, so the result is unambiguous.

**Prerequisites for all tests:** Anytype desktop running, a bearer token available (referred to as `$TOKEN` below), a space ID (referred to as `$SPACE_ID`), and at least one existing object in the space (referred to as `$OBJECT_ID`). The Anytype API base URL is `http://127.0.0.1:31012`.

### A1: PATCH Body Update Verification

**Purpose:** Determine whether `PATCH /v1/spaces/{space_id}/objects/{object_id}` with a markdown `body` field actually updates the visible content of the object, or silently ignores the body.

**Step 1: Read the current object body.**

```bash
curl -s -X GET \
  "http://127.0.0.1:31012/v1/spaces/$SPACE_ID/objects/$OBJECT_ID?format=md" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Anytype-Version: 2025-11-08" \
  | jq '.body'
```

Record the current body content. If the object has no body, note that.

**Step 2: PATCH with a new body containing a unique marker.**

```bash
curl -s -X PATCH \
  "http://127.0.0.1:31012/v1/spaces/$SPACE_ID/objects/$OBJECT_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Anytype-Version: 2025-11-08" \
  -H "Content-Type: application/json" \
  -d '{
    "body": "## PATCH Test Marker\n\nThis content was written by the PATCH verification test at '"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'. If this text is visible in the object body, PATCH body updates work."
  }'
```

Record the HTTP status code and response body.

**Step 3: Read the object body again.**

```bash
curl -s -X GET \
  "http://127.0.0.1:31012/v1/spaces/$SPACE_ID/objects/$OBJECT_ID?format=md" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Anytype-Version: 2025-11-08" \
  | jq '.body'
```

**Interpreting results:**

| Step 2 status | Step 3 body contains "PATCH Test Marker"? | Conclusion |
|---|---|---|
| 200 OK | Yes | **PATCH body works.** Use the primary path: store Entity/Concept descriptions in the markdown body via PATCH. |
| 200 OK | No (body unchanged from Step 1) | **PATCH body is silently ignored.** Use the fallback path: store descriptions in `wiki_description` and `wiki_facts` text properties only. The markdown body is a display-only surface. |
| 4xx/5xx | N/A | PATCH endpoint itself is broken or auth is insufficient. Debug before proceeding. Check if this is a write-token issue (see Open Question #6). |

**Important:** Also verify the PATCH works for Property updates (this is expected to work based on community reports, but confirm):

```bash
curl -s -X PATCH \
  "http://127.0.0.1:31012/v1/spaces/$SPACE_ID/objects/$OBJECT_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Anytype-Version: 2025-11-08" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "PATCH Property Test - '"$(date +%s)"'"
  }'
```

Then GET the object and verify the name changed. If Property PATCH also fails, the issue is broader than body updates.

### A2: FilterExpression Search Verification

**Purpose:** Determine whether `POST /v1/spaces/{space_id}/search` with a `FilterExpression` actually filters results, or returns unfiltered results (a no-op).

**Step 1: Count total objects in the space (baseline).**

```bash
curl -s -X POST \
  "http://127.0.0.1:31012/v1/spaces/$SPACE_ID/search" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Anytype-Version: 2025-11-08" \
  -H "Content-Type: application/json" \
  -d '{
    "query": ""
  }' \
  | jq '.data | length'
```

Record this count as TOTAL.

**Step 2: Search with a FilterExpression that should return a strict subset.**

Use a filter that restricts to a specific type_key. Pick a type that exists in the space but does not account for all objects (e.g., if the space has Pages and Notes, filter for just one type).

```bash
curl -s -X POST \
  "http://127.0.0.1:31012/v1/spaces/$SPACE_ID/search" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Anytype-Version: 2025-11-08" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "",
    "filter": {
      "condition": "and",
      "filters": [
        {
          "key": "type_key",
          "condition": "eq",
          "value": "note"
        }
      ]
    }
  }' \
  | jq '.data | length'
```

Record this count as FILTERED.

**Step 3: Verify with a filter that should return zero results.**

```bash
curl -s -X POST \
  "http://127.0.0.1:31012/v1/spaces/$SPACE_ID/search" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Anytype-Version: 2025-11-08" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "",
    "filter": {
      "condition": "and",
      "filters": [
        {
          "key": "type_key",
          "condition": "eq",
          "value": "nonexistent_type_that_does_not_exist_xyz"
        }
      ]
    }
  }' \
  | jq '.data | length'
```

Record this count as ZERO_TEST.

**Interpreting results:**

| FILTERED < TOTAL? | ZERO_TEST == 0? | Conclusion |
|---|---|---|
| Yes | Yes | **FilterExpression works.** Use it in the query pipeline's Tier 1 index-navigation mode for efficient type filtering. |
| No (FILTERED == TOTAL) | No (ZERO_TEST == TOTAL) | **FilterExpression is a no-op** (filter is ignored, all objects returned). Use the fallback: `GET /v1/spaces/{space_id}/objects` with client-side type filtering. |
| Yes | No | **Partial implementation.** FilterExpression works for some conditions but not others. Document which conditions work and use them; fall back to client-side for the rest. |
| No | Yes | **Inconsistent behavior.** Re-run tests. If reproducible, treat as "does not work" and use the fallback path. |

**Note on filter syntax:** The exact FilterExpression schema may vary by API version. The `filter` object structure above follows the OpenAPI spec's `FilterExpression` type. If the API rejects this structure, try alternative field names (e.g., `filters` at the top level, or `operator` instead of `condition`). Document the working syntax for the implementation team.
