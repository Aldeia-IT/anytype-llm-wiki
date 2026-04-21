---
name: wiki-library-module-port-llm-wiki-pattern-onto-any
status: SPEC
issue: 140
repo: anytype-llm-wiki
target_repo: anytype-llm-wiki
review_rounds: 0
date: 2026-04-22
author: spec-writer agent
---

# Wiki Library Module: Port LLM Wiki Pattern onto Anytype

## Contributor's Map

A new contributor to this module should read in the following order:

1. **README.md** (repo root) — what the module is, prerequisites, quick-start. v0.2.0 extends this.
2. **This spec** — authoritative design reference. Start at [Proposed Solution](#proposed-solution) for the architecture, then [Delivery Phases](#delivery-phases) for shippable scope boundaries, then [Implementation Plan](#implementation-plan) for file layout and signatures.
3. **`scripts/verify-anytype-writes.sh`** — runs three live-API checks (PATCH body, FilterExpression, write-token scope). Every contributor starting work on v0.3.0+ must run this first.
4. **`src/anytype_llm_wiki/wiki/`** — proposed module layout (does not yet exist in v0.1.0).
5. **`tests/wiki/`** — per-module test files mirroring the source layout.

The module is **additive**: v0.1.0's `semantic_search` and `reindex_anytype` tools and their files (`src/anytype_llm_wiki/{server,anytype_client,indexer,chunker,embedder,config}.py`) are not modified in substance during v0.2.x — v0.2.x adds files under `src/anytype_llm_wiki/wiki/` and extends `server.py` to register the new MCP tools.

## Problem Statement

Agents and knowledge workers rediscover the same information repeatedly. Every query to an LLM re-derives facts that were already derived from the same sources. There is no compiled, compounding, interlinked knowledge that carries forward from one session to the next. The result is wasted tokens, inconsistent synthesis, and an ever-growing raw source library that never becomes more queryable over time.

The Karpathy LLM Wiki pattern solves this: compile knowledge once into a structured wiki maintained by the LLM rather than re-deriving it per query. Cross-references, contradictions, and synthesis are materialized at ingest time. Queries then become structured lookups over a growing, interlinked knowledge base rather than expensive from-scratch retrievals.

All seven existing open-source implementations of this pattern (nashsu/llm_wiki, lucasastorian/llmwiki, Ar9av/obsidian-wiki, ScrapingArt/Karpathy-LLM-Wiki-Stack, and three others appearing in the week after Karpathy's April 2026 tweet reached 16 million views) are built on the filesystem + Obsidian stack. Every one of them shares the same structural failure modes: broken cross-references when entity names change, freeform tag drift that erodes taxonomy over sessions, a static index.md that lags behind the actual content, and lint rules that must compensate for what the data layer cannot enforce.

anytype-llm-wiki already indexes Anytype objects into Qdrant for semantic search (v0.1.0, shipped). Anytype's native data model eliminates three of these failure modes at the data layer: typed Relations that use object IDs (not strings) cannot break when an entity is renamed; closed-option tag properties enforced by the API prevent taxonomy drift entirely; and live Collections always reflect the current state of the knowledge base without requiring a maintained index file.

The opportunity is to be, to our knowledge, the first Anytype-native LLM wiki implementation — combining Karpathy's pattern, Hermes' battle-tested operational policies, and Anytype's structural advantages into a publicly installable, community-facing module. (Note: This "first" claim must be verified before the v0.2.0 README updates ship by searching the Anytype community forum, the anytype-mcp repo issues, and GitHub for any prior Anytype-based LLM wiki attempt. If a prior implementation is found, adjust the positioning accordingly.)

**Specific user scenarios that drive this:**

- Jan has ingested 40+ AI research papers into Anytype over 6 months. Asking an agent "how does the attention mechanism in Mamba compare to classic transformers?" currently triggers a cold retrieval from Qdrant. There is no compiled synthesis of this already-read material to draw from.
- An agent supporting Jan's consulting work needs to answer "what is our current position on agentic memory architectures?" but has no persistent knowledge base to consult — only a semantic search over raw objects.
- A community developer landing on the anytype-llm-wiki GitHub repo today finds two MCP tools and no path toward structured knowledge management. They want a clean module to try the Karpathy pattern without migrating away from Anytype.

---

## Product Context

**Business goal:** Extend anytype-llm-wiki from a utility tool (semantic search, v0.1.0) into a knowledge platform with compounding value — where each ingested source makes future queries smarter. Simultaneously, use this as a public signal of Aldeia IT's technical seriousness and community relevance in the growing agent knowledge space.

**Target users:**

- **Primary — Jan (Aldeia IT operator):** Solo technical consultant, Mac Mini M4, already runs anytype-llm-wiki v0.1.0. Uses Anytype as primary personal knowledge base. Needs a knowledge system that compounds over time without manual curation overhead. Budget-conscious on hosted LLM tokens — Ollama on local hardware is the default. Comfortable configuring and operating Python MCP servers. Currently lacks a structured way to compile research into a queryable knowledge graph.

- **Secondary — Anytype community developer:** Technically sophisticated user tracking the Anytype ecosystem and the LLM wiki space. Frustrated that every existing implementation assumes Obsidian. Wants a clean, installable module — not a personal script to adapt. Will evaluate the module by reading the README, trying the quick-start, and checking the positioning against known alternatives.

- **Tertiary — Aldeia IT reputation signal (not a user, a product goal):** The anytype-llm-wiki repo is public. Visitors should immediately understand the module's value, how to install it, and why Anytype is the right substrate for an LLM wiki.

**User stories:**

- As Jan, I want to ingest a research paper URL and have the module extract entities and concepts, create or update Anytype objects, and wire their relations, so that future queries draw on compiled synthesis rather than raw retrieval.
- As Jan, I want to ask a structured question against my wiki and receive a synthesized answer with citations to specific Anytype objects, so that I can trace the reasoning and jump directly to source material.
- As Jan, I want to run a lint check on my wiki space and see a severity-grouped report with Anytype deeplinks, so that I can identify and fix structural problems (orphans, stale objects, unresolved contradictions) without manually scanning objects.
- As an Anytype community developer, I want to run one command to bootstrap the wiki type schema into my Anytype space and a second command to ingest my first source, so that I can evaluate the module within 15 minutes of `pip install` (with prerequisites already running) on my own data.
- As an Anytype community developer, I want clear documentation explaining how this module compares to Obsidian-based implementations, so that I can make an informed choice about adopting it.
- As Jan, I want to bootstrap a new wiki domain (e.g., "Axé DAO research") into a fresh Anytype space using the same type schema, so that each domain has its own isolated knowledge graph without cross-contamination.

**Success metrics:** see the [Success Criteria](#success-criteria) section for per-version quantified targets.

**Roadmap alignment:** This extends anytype-llm-wiki's existing foundation (Qdrant, bge-m3, FastMCP) without replacing or breaking the two current tools (`semantic_search`, `reindex_anytype`). It is additive. The wiki module ships as new MCP tools within the same pip package, released as semantic-versioned minor bumps (v0.2.0, v0.3.0, v0.4.0, v0.5.0). It is the first step toward anytype-llm-wiki becoming a full knowledge platform rather than a search utility.

---

## User Experience

**Workflows:**

The module has four distinct user-facing workflows, each corresponding to a shippable release:

**Workflow 1: Bootstrap a new wiki space (v0.2.0)**

1. User has an Anytype space designated for a wiki domain (e.g., "AI Research").
2. User runs `wiki.bootstrap(space_id="<id>")` via MCP client or `anytype-llm-wiki wiki-bootstrap --space-id <id>` via CLI. Optionally passes `domain_tags` to customize the tag taxonomy for their domain.
3. The tool creates: 6 object Types (Source, Entity, Concept, Comparison, Query, WikiLog), all Properties for each Type, the tag taxonomy as closed-option multi_select properties, and a root Collection.
4. Tool responds with a structured summary listing every object created, every property created, and a confirmation that the schema is ready. Anytype deeplinks to each new Type are included in the response.
5. User opens Anytype and sees the new Types in their space, populated with the correct properties. The wiki is ready to receive content.
6. Bootstrap is idempotent: running it again on a space that already has wiki types skips existing elements (checks by key before creating), creates any missing elements, and reports what was skipped vs. created.

**Workflow 2: Ingest a source (v0.3.0)**

1. User runs `wiki.ingest(source="https://arxiv.org/abs/2502.12110", space_id="<id>")` or passes a local file path.
2. The tool fetches the source content, creates a Source object in Anytype, runs LLM extraction to identify entities, concepts, and relationships mentioned.
3. For each identified entity/concept, the tool checks Anytype for an existing object (normalized-title exact match, then embedding similarity — see [Entity Resolution Semantics](#entity-resolution-semantics)). If found above the auto-upsert threshold, the existing object is updated with new facts and the new Source added to its `sources` relation. If no match, a new object is created if it meets the page threshold policy (2+ source mentions or central to this source).
4. Relations between objects are wired bidirectionally. Each new Entity that relates to existing Entities gets its `relations` property updated; the target Entities get the reciprocal update.
5. A WikiLog entry is created recording the ingest operation (source, objects created, objects updated, timestamp).
6. Tool responds with a structured summary: source object ID + deeplink, list of objects created (with deeplinks), list of objects updated (with deeplinks), list of entities skipped (with reason), count of relations created.
7. User calls `reindex_anytype(space_id="<id>")` after ingest to update the Qdrant index for near-real-time query availability. (This step may be automated by the ingest tool as a post-ingest call if configured.)

**Workflow 3: Query the wiki (v0.4.0)**

1. User runs `wiki.query(question="How does Mamba's attention mechanism compare to classic transformers?", space_id="<id>")` via MCP client.
2. For wikis under the configured size threshold (default: 200 objects), the tool uses index-navigation mode: queries Anytype Collections by type to identify candidate objects, reads full object content and 1-hop relation neighborhoods.
3. For wikis above the threshold, vector search (bge-m3 + Qdrant) identifies candidate objects first, then full object fetch + 1-hop relation neighborhoods.
4. The tool synthesizes an answer from the fetched content, citing specific objects by title and Anytype deeplink.
5. If the synthesis meets the file-back threshold (default: draws from 3+ objects and produces 100+ words), a Query object is created in Anytype with `drew_from` relations to the cited objects, recording the question, answer, and timestamp.
6. Tool responds with the synthesized answer, a "Sources consulted" section listing object titles and deeplinks, and a note if a Query object was filed back.

**Workflow 4: Lint the wiki (v0.5.0)**

1. User runs `wiki.lint(space_id="<id>")` via MCP client or CLI.
2. The tool queries Anytype for structural health: orphaned objects (no inbound relations), stale objects (updated_at more than 90 days older than newest related source's ingested_at), objects with unresolved contradiction flags, objects exceeding the size threshold (candidates to split), and types with zero objects (empty Types indicating incomplete schema).
3. Report is returned as a severity-grouped list: critical, high, medium, low, informational.
4. Each item includes: object title, issue description, severity, and Anytype deeplink for immediate navigation.
5. Potential duplicate pairs (objects above embedding similarity threshold but below auto-upsert threshold) are surfaced as a separate section.

**UX implications:** The user's mental model shifts from "I search my Anytype objects" to "I query a compiled knowledge base that understands relationships between topics." The Anytype app becomes the visual browsing surface — the user navigates wiki objects in Anytype the same way they would navigate a wiki, while the MCP tools handle all creation and maintenance. The user should rarely need to manually edit wiki objects.

**Accessibility:** N/A — the module's user-facing surface is MCP tool calls (text-based, no visual interface beyond the Anytype app which has its own accessibility support) and CLI commands.

**Error states and error message design:**

All four tools must distinguish between three error categories with distinct messaging:

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

The anytype-llm-wiki module occupies a unique position: it is the only implementation that:
1. Uses a structured typed-object graph rather than markdown files
2. Eliminates broken cross-references and tag drift at the data-model layer rather than through lint rules
3. Provides native multi-device sync (Anytype's E2E encrypted sync) without Obsidian Sync subscription
4. Ships as a pip-installable module with a documented quick-start, not a script to copy

The positioning statement for the README: "To our knowledge, the first Anytype-native LLM wiki — combining Karpathy's pattern, Hermes' battle-tested operational policies, and Anytype's typed knowledge graph into an installable module. Three common LLM wiki failure modes eliminated at the data layer. No Obsidian required."

**Claim verification (required before v0.2.0 README update ships):** Search the Anytype community forum, the anytype-mcp repo issues/PRs, and GitHub for any prior Anytype-based LLM wiki attempt. If none is found, the "first" claim stands. If one is found, revise the positioning to differentiate on specific features rather than priority.

### Comparison with filesystem LLM wikis (carry into README)

| Dimension | Filesystem + Obsidian (nashsu, lucasastorian, OmegaWiki, …) | anytype-llm-wiki |
|---|---|---|
| Cross-reference integrity | String-based wikilinks; break when an entity is renamed | Typed Relations use object IDs; rename-safe |
| Tag taxonomy | Freeform tags drift across sessions | Closed-option multi_select enforced by the Anytype API |
| Index / navigation surface | Static `index.md` maintained by the LLM; lags content | Live Collections filtered by type_key; always current |
| Multi-device sync | Requires Obsidian Sync subscription or manual git | E2E-encrypted sync in the Anytype client, no cloud account |
| Browsing surface | Obsidian (or editor of choice) | Native Anytype desktop/mobile |
| Vector retrieval | Optional plugin (varies per implementation) | Integrated (Qdrant + bge-m3 from v0.1.0) |
| Install | Copy scripts, edit paths | `pip install anytype-llm-wiki` |
| License / cost | Varies; Obsidian Sync is paid | MIT; all local components free |

---

## Research Summary

### Primary findings informing this spec

**The Karpathy pattern is validated and the tooling gap is explicit.** The tweet at 16M views and 7 community implementations in one week confirm strong developer demand. Karpathy himself named the gap: "room for an incredible new product." The Anytype-native angle is differentiated because every community response uses filesystem + Obsidian.

**Hermes' design decisions are the operational blueprint.** Page threshold policy (2+ mentions or central to one source), cross-link minimum (≥2 outbound relations per object), severity-graded lint (critical/high/medium/low), contradiction handling (document both positions, flag for review, never silently overwrite), append-only WikiLog. These are portable verbatim — only the storage mechanism changes.

**Anytype eliminates 3 of 7 documented LLM wiki failure modes at the data layer.** Broken cross-references (Relations use object IDs), schema drift/tag violations (closed-option enforcement), wikilink-as-interface coupling (no string-based linking). Two more are mitigated: stale content (native `updated_at` property queries) and session orientation brittleness (live Collections replace static index.md). Entity duplication and information quality degradation still require application-layer solutions.

**Anytype API supports all required operations.** Full CRUD for Types, Properties, Tags, Objects. Programmatic type schema bootstrap is fully feasible. The existing anytype-llm-wiki pipeline integrates with zero code changes for new wiki types via `type_key` filtering already built into Qdrant payloads (verified in `src/anytype_llm_wiki/server.py` lines 38–42).

**The PATCH body update risk is the highest-risk technical question.** Community report from anytype-mcp-plus v1.1.0: "Body (rich text) updates via PATCH are silently ignored in current API." This contradicts the official API docs. If confirmed, the ingest pipeline cannot use PATCH to update Entity/Concept descriptions. This must be verified against the live API before v0.3.0 implementation begins (see `scripts/verify-anytype-writes.sh`).

**Index-navigation is sufficient at personal wiki scale.** Karpathy's own scale claim: ~100 articles / ~400K words works without RAG. OMEGA achieves 95.4% on LongMemEval using compiled wiki + index navigation. The query pipeline should default to index-navigation for small wikis and add vector search as augmentation at medium scale.

**File-back of query outputs is the primary compounding mechanism.** Karpathy: "my own explorations and queries always add up in the knowledge base." This is not an optional log entry — it is the mechanism by which questions improve future answers. The Query type and its `drew_from` relations are a first-class design concern.

---

## Proposed Solution

### Architecture Overview

The wiki module adds four MCP tools and one CLI entry point to the existing anytype-llm-wiki package. All wiki tools share a new `wiki/wiki_client.py` module that provides write capabilities to the Anytype API (types, properties, tags, objects, PATCH updates) with module-scoped `httpx.Client` reuse. The existing `anytype_client.py` (read-only) is unchanged in v0.2.x; a follow-up ticket in v0.3.x+ may refactor shared client infrastructure. The existing `semantic_search` and `reindex_anytype` tools are unchanged.

### Type Schema (Deliverable: wiki.bootstrap — v0.2.0)

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

*Note:* The Comparison type is not auto-created by the ingest pipeline. Ingest extracts entities and concepts only. Comparisons are created in two ways: (1) manually by the user when they want to compare entities, or (2) by `wiki.query` when a query produces a comparison-style synthesis that meets the file-back threshold. The type is included in v0.2.0 because the bootstrap schema should be complete for manual use from day one, and because the query pipeline's file-back mechanism may produce comparison objects. If usage data from v0.3.0–v0.4.0 shows Comparisons remain consistently empty, the type can be reconsidered.

**Query** — a filed synthesis from a wiki.query call (the compounding mechanism)
- `wiki_question` (text): the question asked
- `wiki_answer` (text): the synthesized answer
- `wiki_drew_from` (objects): Entity/Concept/Comparison objects cited in the answer
- `wiki_asked_at` (date): timestamp

**WikiLog** — append-only operational record (see [Observability](#observability))
- `wiki_action` (select): ingest | query | lint | bootstrap | archive
- `wiki_subject` (text): the source URL, object title, or operation description
- `wiki_objects_created` (number): count of objects created in this operation
- `wiki_objects_updated` (number): count of objects updated
- `wiki_timestamp` (date): operation timestamp
- `wiki_notes` (text): any errors, skips, or noteworthy events

**Tag taxonomy (closed-option, enforced by Anytype API):**

Domain tags (wiki_domain_tags, shared across all types) are configurable at bootstrap time via an optional `domain_tags` parameter. The defaults are:
`wiki_ai-research`, `wiki_infrastructure`, `wiki_business`, `wiki_engineering`, `wiki_governance`, `wiki_science`, `wiki_other`

Community users building wikis for other domains pass their own list:
```python
wiki.bootstrap(space_id="<id>", domain_tags=["wiki_cooking-techniques", "wiki_ingredients", "wiki_cuisines", "wiki_other"])
```

Tags created at bootstrap can be extended later by adding new tags via the Anytype API or by re-running bootstrap with an expanded list (bootstrap is idempotent — existing tags are skipped, new ones are created). The `wiki_` key prefix convention prevents collisions with any existing tags in the user's space.

### Ingest Pipeline (wiki.ingest — v0.3.0)

**Ingest data flow:**

```mermaid
flowchart TD
    A[User invokes wiki.ingest<br/>source, space_id] --> B[Acquire per-space lock]
    B -->|lock busy| B_ERR[[DATA ERROR<br/>ingest_in_progress]]
    B -->|acquired| C[Fetch source<br/>httpx with SSRF guards]
    C -->|unsupported type| C_ERR[[DATA ERROR<br/>pdf/js/paywall]]
    C --> D[Convert HTML to markdown]
    D --> E[Create Source object in Anytype]
    E --> F[LLM extraction<br/>WIKI_EXTRACT_MODEL]
    F -->|malformed JSON| F_RETRY[Retry once with<br/>repair prompt]
    F_RETRY -->|still bad| F_ERR[[DATA ERROR<br/>extraction_failed]]
    F --> G{For each entity/concept}
    G --> H[Resolve entity<br/>normalized-title exact match]
    H -->|no match| I[Embedding similarity vs.<br/>existing wiki objects of same type]
    I -->|>= upsert threshold| J[Update existing object]
    I -->|0.70-upsert threshold| K[Skip with duplicate_proposed]
    I -->|< 0.70| L{Page threshold<br/>2+ sources or central?}
    L -->|yes| M[Create new object]
    L -->|no| N[Skip below_threshold]
    J --> O[Write bidirectional relations<br/>target side reciprocal]
    M --> O
    O --> P[Enforce cross-link min<br/>>= 2 outbound relations]
    P --> Q[Create WikiLog entry]
    Q --> R{WIKI_AUTO_REINDEX?}
    R -->|yes| S[Call reindex_anytype]
    R -->|no| T[Return IngestResult]
    S --> T
    T --> U[Release lock]
```

**MCP tool signature:**
```python
def wiki_ingest(
    source: str,                  # URL or absolute file path
    space_id: str,                # Anytype space ID
    domain_hint: str | None = None,  # optional tag to pre-apply (e.g. "wiki_ai-research")
) -> dict:  # IngestResult shape, below
    ...
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
  "warnings": ["string"],
  "status": "ok|partial|error"
}
```

**Ingest pipeline steps:**

1. Acquire the per-space lock file (see [Concurrent Ingest Policy](#concurrent-ingest-policy)). If another ingest is active, return `[DATA ERROR] ingest_in_progress: another ingest is running for space {space_id} (lock held since {timestamp}). Retry when it completes or remove the stale lock at {lock_path}.`
2. Fetch source content (URL via httpx with SSRF redirect guard, file via local read). Create Source object in Anytype.
   **Supported source types:** plain text, Markdown, HTML. For URLs, httpx fetches the page and HTML is converted to markdown (using `markdownify` — added as a v0.3.0 dependency) before extraction. **Unsupported source types:** PDFs, paywalled articles, and JavaScript-rendered pages (SPAs) are not handled in v0.3.0. If a URL serves a PDF `Content-Type`, or the fetched HTML contains no meaningful text content (empty `<body>` / SPA root), the tool returns a `[DATA ERROR]` explaining the limitation and suggesting a local markdown/text file instead. PDF parsing (`pymupdf`) and headless browser fetching are deferred.
3. Run LLM extraction prompt against source content. Extract: entities (with descriptions), concepts (with definitions), relationships between extracted entities/concepts. The extraction model is configurable separately from the embedding model (env var `WIKI_EXTRACT_MODEL`, default: same Ollama instance + model configured for anytype-llm-wiki). See [Extraction Prompt Structure](#extraction-prompt-structure) for the exact prompt, expected JSON schema, and retry/repair behavior.
4. For each extracted entity/concept:
   a. Normalized-title exact match (see [Entity Resolution Semantics](#entity-resolution-semantics)) via the Anytype search API.
   b. If no exact match: embedding similarity check via bge-m3 against existing wiki objects of the same type.
   c. If match above auto-upsert threshold (configurable, default: 0.92 title / 0.85 embedding): update existing object. **Thresholds are provisional defaults** adopted from the research synthesis examples, not empirically validated against bge-m3 similarity on actual entity pairs; tune during v0.3.0 testing (see [Open Questions](#open-questions)).
   d. If match below auto-upsert threshold but above the duplicate-surfacing floor (0.70): add to `objects_skipped` as `duplicate_proposed`. User must manually review.
   e. If no match: apply page threshold policy. Create object if entity appears in 2+ sources OR is central to this source. Skip otherwise.
5. Apply cross-link minimum: each new or updated object must have ≥2 outbound wiki_relations before the pipeline completes. If fewer than 2 can be identified from the source, flag in WikiLog `wiki_notes`.
6. Write bidirectional relations: for every A→B relation, also write B→A. If either write fails, roll back both writes and record the failure in the WikiLog.
7. Create WikiLog entry (always, including partial failures).
8. Call `reindex_anytype(space_id=space_id)` post-ingest (configurable, default: enabled via `WIKI_AUTO_REINDEX`).
9. Release the lock.

**PATCH update — single canonical path with pre-v0.3.0 verification:**

The v0.2.0 pre-release runs `scripts/verify-anytype-writes.sh`, which exercises PATCH body updates, PATCH property updates, and FilterExpression against the live Anytype API. The verification result selects **one** canonical path, recorded in `.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/patch-decision.md` and referenced by the implementation:

- **Primary path — PATCH body works:** When updating an existing Entity or Concept, use `PATCH /v1/spaces/{space_id}/objects/{object_id}` with the updated description/facts in the body. Properties (`wiki_description`, `wiki_facts`) mirror the body for programmatic access.
- **Fallback path — PATCH body silently ignored:** Store descriptions and facts exclusively in dedicated text Properties (`wiki_description`, `wiki_facts`). The markdown body is treated as a display-only surface populated on create and never updated. This path avoids delete+recreate because that would break all inbound Relations.

**Decision rule:** v0.3.0 does not ship with both code paths. The verification script runs during v0.3.0 pre-release. The path is selected once, committed, and the unused path is not present in shipped code. If API behavior changes in a later Anytype release, a new ticket and new verification run re-select the path.

### Query Pipeline (wiki.query — v0.4.0)

**Query data flow:**

```mermaid
flowchart TD
    A[User invokes wiki.query<br/>question, space_id] --> B[Verify schema exists<br/>list wiki types]
    B -->|missing| B_ERR[[CONFIG ERROR<br/>run wiki.bootstrap]]
    B --> C[Count wiki objects<br/>Entity + Concept + Comparison + Query]
    C --> D{count >= WIKI_INDEX_THRESHOLD?}
    D -->|no| E[Tier 1 — index-navigation<br/>list objects by type_key]
    D -->|yes| F[Tier 2 — vector-augmented<br/>semantic_search wiki types]
    E --> G[Candidate object IDs]
    F --> G
    G --> H[Fetch full objects +<br/>1-hop relation neighborhoods<br/>with per-run cache]
    H --> I[LLM synthesis with citations]
    I --> J{file_back gate<br/>sources>=min AND words>=min?}
    J -->|yes| K[Create Query object +<br/>drew_from relations]
    J -->|no| L[Return QueryResult]
    K --> L
```

**MCP tool signature:**
```python
def wiki_query(
    question: str,                # natural language question
    space_id: str,                # Anytype space ID
    file_back: bool | None = None,  # override file-back policy
) -> dict:  # QueryResult
    ...
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
  "retrieval_mode": "index_navigation|vector_augmented",
  "object_count_at_decision": 147
}
```

**Tiered retrieval strategy:**

- **Tier 1 — index-navigation mode** (default for wikis under `WIKI_INDEX_THRESHOLD` wiki objects, default 200): Query Anytype by type_key to enumerate candidates. Read object descriptions and 1-hop relation neighborhoods directly from Anytype. No Qdrant query needed.
- **Tier 2 — vector-augmented mode** (default for wikis ≥ `WIKI_INDEX_THRESHOLD` wiki objects): Run `semantic_search(question, types=["wiki_entity", "wiki_concept", "wiki_comparison", "wiki_query"])` to identify candidates. Fetch full objects + 1-hop relation neighborhoods from Anytype. Synthesize.

**Boundary test (addresses council ADVISORY #3):** Object counts 199, 200, 201 are exercised explicitly — the threshold is `count >= WIKI_INDEX_THRESHOLD` (mode flips at 200 inclusive). The threshold is configurable and can be re-tuned by the operator; tests cover both defaults and a custom threshold value.

**Relation neighborhood traversal:** Limited to 1 hop to avoid N+1 call explosion. For each candidate object, fetch the objects linked in its `wiki_relations`, `wiki_related`, and `wiki_drew_from` properties. Cache fetched objects within the pipeline run to avoid duplicate API calls.

**File-back policy:** A Query object is created when synthesis draws from `WIKI_FILE_BACK_MIN_SOURCES` (default 3) objects AND produces `WIKI_FILE_BACK_MIN_WORDS` (default 100) words. Users can override per call with `file_back=True` or `file_back=False`.

**Query compounding:** Filed Query objects are indexed by `reindex_anytype` on the next cycle and become available as sources for future queries via `semantic_search`. This is the mechanism by which asking questions improves future answers.

**FilterExpression — single canonical path with pre-v0.4.0 verification:** The `POST /v1/search` FilterExpression is verified by the same `scripts/verify-anytype-writes.sh` used at v0.3.0. If FilterExpression works, Tier 1 uses it directly. If it is a no-op, Tier 1 uses list-objects with property query params and client-side filtering. The decision is single-path in shipped code.

### Lint Suite (wiki.lint — v0.5.0)

**Lint data flow:**

```mermaid
flowchart TD
    A[User invokes wiki.lint<br/>space_id, severity_threshold] --> B[List all wiki objects<br/>grouped by type_key]
    B --> C[Count objects per type<br/>report empty types as informational]
    C --> D[For each object,<br/>fetch relation properties<br/>batched to reduce API calls]
    D --> E[Check asymmetric relations<br/>A->B exists AND B->A missing?]
    E --> F[Check orphans<br/>no inbound relations,<br/>7-day grace for manual]
    F --> G[Check pipeline orphans<br/>WikiLog partial-failure cross-ref]
    G --> H[Check unresolved contradictions<br/>non-empty wiki_contradictions AND<br/>null wiki_last_reviewed]
    H --> I[Check stale objects<br/>updated_at < ingest -90d]
    I --> J[Check oversized descriptions<br/>> 2000 chars]
    J --> K[Qdrant similarity sweep<br/>for potential duplicates]
    K --> L[Apply severity_threshold filter]
    L --> M[Return LintReport]
```

**MCP tool signature:**
```python
def wiki_lint(
    space_id: str,
    severity_threshold: str = "all",  # "critical"|"high"|"medium"|"low"|"all"
) -> dict:  # LintReport
    ...
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
  "summary": {"critical": 0, "high": 0, "medium": 0, "low": 0, "informational": 0},
  "elapsed_ms": 0
}
```

**Lint checks, severity, and detection method:**

| Check | Severity | Detection Method |
|-------|----------|-----------------|
| Broken/asymmetric relation (A→B exists, B→A missing) | Critical | Fetch all wiki objects, verify each `wiki_relations` entry has a reciprocal |
| Pipeline orphan (zero relations, created by a failed ingest) | High | Cross-reference WikiLog entries with `wiki_notes` containing failure text against objects created in the same ingest run. Objects created by a pipeline run that logged a partial failure and that have zero `wiki_relations` are flagged immediately (no grace period). |
| Orphan entity/concept (zero inbound relations, manually created or from successful ingest) | High | List objects where `wiki_relations` is empty AND `wiki_ingested_at < now - 7 days`. The 7-day grace period allows time for manually created objects to be wired. |
| Unresolved contradiction | High | Filter objects with non-empty `wiki_contradictions` AND null `wiki_last_reviewed` |
| Stale object | Medium | Compare `last_modified_date` to `wiki_ingested_at` of linked sources |
| Oversized description (> ~2000 chars) | Low | String length check client-side after fetch |
| Empty type | Informational | Object count by type_key |
| Potential duplicates (similarity 0.70–upsert threshold) | Informational | Qdrant similarity query against existing wiki object embeddings |

**Performance characteristics (addresses council ADVISORY #6):** The asymmetric-relation check is O(N) in wiki object count (one object fetch per object, each yielding constant-size relation property). For a 500-object wiki this is ~500 API calls. With p50 100ms Anytype latency, wall time is ~50s — within the 60s target but tight. Mitigations:

- **Batching:** fetch objects in batches of 100 via `GET /v1/spaces/{space_id}/objects?limit=100&offset=...` (already used in `anytype_client.list_objects`). Relation properties come in the object response.
- **Caching:** per-run object cache (dict keyed by object_id) reused across checks (orphan + asymmetric + stale all reference the same fetched objects).
- **Future optimization (deferred to v0.6.x, tracked via OQ#7):** if the Anytype REST API exposes the system `Backlinks` property, inbound-relation counts become O(1) per object — orphan detection becomes a single property read. This is a follow-up ticket, not a v0.5.0 deliverable.
- **Budget:** lint must return in ≤ 60s for wikis up to 500 objects. Above 500 objects, lint emits a warning in `warnings` and may exceed budget; this is acceptable for v0.5.0.

### MCP Tool Interface Design

All four tools share these conventions:

- **Tool naming:** `wiki_bootstrap`, `wiki_ingest`, `wiki_query`, `wiki_lint` (underscores, not dots, as MCP tool names). The dot notation (`wiki.bootstrap`) is used in documentation as a conceptual name.
- **space_id is always explicit:** No ambient global space. Every tool call requires a `space_id`. This supports multiple wiki domains.
- **Anytype deeplinks in all responses:** Format `anytype://object/{space_id}/{object_id}`.
- **Structured return types (JSON-serializable dicts).**
- **Error category in all errors:** `api_error`, `data_error`, `config_error`.
- **WikiLog receipt in all responses:** Every tool returns enough information (WikiLog ID + deeplink + structured status) to reconstruct what happened (see [Observability](#observability)).

### Installation and Developer Experience

The wiki module ships as part of the `anytype-llm-wiki` pip package — no separate install step:

```bash
pip install anytype-llm-wiki
# or (preferred)
uv tool install anytype-llm-wiki
```

After install, the wiki MCP tools are available in the MCP server alongside the existing tools. The CLI commands are also available:

```bash
anytype-llm-wiki wiki-bootstrap --space-id <space_id>
anytype-llm-wiki wiki-ingest --source https://arxiv.org/abs/... --space-id <space_id>
anytype-llm-wiki wiki-query --question "..." --space-id <space_id>
anytype-llm-wiki wiki-lint --space-id <space_id>
```

### README additions (insert into README for v0.2.0+)

Council ADVISORY #1 and #2 require a privacy notice and a content-rights notice in the README. The exact text, verbatim-ready:

**Insert into README — new section "Privacy and data flow" (after "How it works"):**

> ### Privacy and data flow
>
> anytype-llm-wiki runs locally on your machine. By default, nothing leaves your computer except for the specific network calls described below.
>
> - **Anytype, Qdrant, and Ollama** are accessed over `localhost` only.
> - **Source URL fetching (v0.3.0+)**: when you call `wiki.ingest` with a URL, an HTTP request is sent to that URL from your machine. The server hosting the URL sees your IP and standard User-Agent. No other party is involved.
> - **Hosted-LLM extraction (optional, v0.3.0+)**: if you configure `WIKI_EXTRACT_MODEL` to point at a hosted LLM API (e.g., OpenAI, Anthropic), the **source content you ingest is transmitted to that provider** as part of the extraction prompt. The default configuration uses your local Ollama instance and sends nothing to third parties. The startup log prints the active extraction endpoint so you can confirm which model is in use.
> - **Content rights and PII**: you are responsible for ensuring you have the right to ingest and store the content you provide. This module does not perform PII classification. If you ingest content containing personal data (of yourself or others), that data is stored in your local Anytype space and, if a hosted LLM is configured, transmitted to that provider. Treat the wiki as you would any personal note-taking system with the additional awareness that extraction may involve third-party processing.
>
> This module is a tool, not a data controller under GDPR/LGPD. Operational responsibility for data protection rests with the operator (you).

**Insert into README — new subsection "Source content and copyright" (inside "Privacy and data flow"):**

> #### Source content and copyright
>
> `wiki.ingest` fetches and stores extracted content from the URLs and files you provide. You are responsible for respecting the copyright and terms-of-use of the sources you ingest. Public scholarly articles, your own notes, and openly licensed material are appropriate inputs. Paywalled content, proprietary documents you do not have rights to redistribute, and third-party material you only have read access to should be treated carefully — even local storage and LLM processing may raise licensing questions depending on your jurisdiction and the source's terms.

**Configuration (environment variables) — updated table (see [Configuration](#configuration) section below).**

---

## Delivery Phases

Each phase is a tagged, shippable release. Re-tested, documented, and released in order — v0.3.0 cannot ship until v0.2.0 is tagged; v0.4.0 cannot ship until v0.3.0; v0.5.0 may start in parallel with v0.3.0/v0.4.0 but cannot tag until v0.2.0 is tagged.

### v0.2.0 — `wiki.bootstrap` + schema

**Scope (in):**
- `wiki/types_schema.py` — canonical schema definitions (the "SCHEMA.md" equivalent in Python).
- `wiki/wiki_client.py` — Anytype write client with module-scoped `httpx.Client` (types, properties, tags, search, create_object).
- `wiki/bootstrap.py` — idempotent creation of 6 Types, all Properties, default tag taxonomy, root Collection.
- `wiki/config.py` — v0.2.0-specific env vars (`WIKI_EXTRACT_MODEL` placeholder only, `WIKI_LOCK_DIR`).
- `wiki/locks.py` — file-lock primitive (used by v0.3.0, shipped early so the API is stable).
- `wiki/normalize.py` — `normalize_title` function (used by v0.3.0 ingest, shipped early for test coverage).
- `wiki/cli.py` — `wiki-bootstrap` subcommand only.
- `scripts/verify-anytype-writes.sh` — committed verification script (see [Verification Script](#verification-script)).
- `server.py` — register `wiki_bootstrap` tool.
- README — privacy/data-flow notice, content-rights notice, prerequisites update.
- `tests/wiki/test_bootstrap.py`, `test_wiki_client.py`, `test_normalize.py`, `test_locks.py`, `test_types_schema.py`.

**Scope (out):**
- Ingest, query, lint (deferred to v0.3.0+).
- No LLM extraction in v0.2.0.
- No Qdrant reads/writes beyond what v0.1.0 already does.

**Requirements (MoSCoW):**
- **Must**: bootstrap creates 6 types + properties + tags + root Collection idempotently; supports custom `domain_tags`; write-token scope verified; README privacy/rights notices land; verification script ships.
- **Should**: `wiki_bootstrap` returns < 30s on a clean space; CLI command `anytype-llm-wiki wiki-bootstrap` works.
- **Won't**: auto-configuration of WIKI_EXTRACT_MODEL (needs Ollama detection heuristics deferred); schema migration tooling (not yet needed).

**Acceptance criteria:**
1. `wiki_bootstrap(space_id=<clean_space>)` creates the 6 Types with correct properties, the tag taxonomy, and a root Collection.
2. Running `wiki_bootstrap` on the same space twice produces no duplicates; the second call reports each element as "already exists, skipped".
3. `wiki_bootstrap(space_id=<missing>)` returns `[CONFIG ERROR]` with the space_id echoed.
4. When Anytype desktop is not running, the tool returns `[API ERROR]` with instructions to start Anytype.
5. Custom `domain_tags` parameter replaces the default taxonomy; re-running with an extended list adds new tags without removing existing ones.
6. Completed call returns < 30s on a clean space (p95 over 5 runs on Jan's Mac Mini M4).
7. `scripts/verify-anytype-writes.sh` runs end-to-end and prints an unambiguous decision for PATCH body, property PATCH, and FilterExpression.
8. README shows the exact privacy notice from this spec (verbatim).
9. Tests in `tests/wiki/test_bootstrap.py` pass with `respx`-mocked Anytype responses plus one optional live-API test gated on `ANYTYPE_API_KEY`.

**Deliverables:**
- Files: those listed under "Scope (in)".
- Docs: README updated; CHANGELOG.md v0.2.0 entry.
- Tests: full unit-level coverage of the new files.

**Dependencies:**
- External: verification script must run successfully against live Anytype (determines v0.3.0 path; no v0.3.0 tagging without this).
- Prior version: v0.1.0 (shipped).

**Risks & mitigations:**
- *Risk: write-token scope insufficient.* Mitigation: verification script runs BEFORE implementation begins. If the existing read token cannot write types, the README documents a new auth flow for v0.2.0.
- *Risk: Anytype API changes between verification and v0.3.0 tagging.* Mitigation: record `Anytype-Version` at verification time and pin it in `config.ANYTYPE_API_VERSION`. Rerun verification on any version bump.

**Pre-release checklist (v0.2.0):**
- [ ] `scripts/verify-anytype-writes.sh` run and result recorded at `.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/patch-decision.md`.
- [ ] `uv run pytest tests/` all green.
- [ ] `pip-audit` clean.
- [ ] README updated with privacy notice and prerequisites.
- [ ] `anytype-llm-wiki wiki-bootstrap --space-id <real>` demo'd against Jan's Anytype.
- [ ] CHANGELOG.md entry.
- [ ] Git tag `v0.2.0`.

---

### v0.3.0 — `wiki.ingest`

**Scope (in):**
- `wiki/fetch.py` — URL fetching with SSRF protections (see [Security Considerations](#security-considerations)) and markdownify-based HTML→markdown.
- `wiki/extraction.py` — LLM extraction pipeline (Ollama or hosted), JSON-schema validation, one retry with repair prompt on malformed output.
- `wiki/prompts/extraction.md` — committed extraction prompt (human-readable).
- `wiki/ingest.py` — ingest orchestration.
- `wiki/cli.py` — extends with `wiki-ingest` subcommand.
- `server.py` — register `wiki_ingest` tool.
- `pyproject.toml` — add `markdownify>=0.11.0` dependency (pinned to minor).
- `tests/wiki/test_ingest.py`, `test_fetch.py`, `test_extraction.py`.

**Scope (out):**
- Query and lint (v0.4.0+, v0.5.0).
- PDF / JavaScript-rendered sources.
- Automatic comparison creation.
- Concurrent ingest (single-writer per space — enforced by the lock; concurrent ingests of different spaces are fine).

**Requirements (MoSCoW):**
- **Must**: URL + file ingestion; bidirectional Relations; page threshold + cross-link minimum; WikiLog entry always written; per-space file lock; SSRF guards; extraction retry on malformed JSON; single canonical PATCH path determined by v0.2.0 verification.
- **Should**: post-ingest reindex call when `WIKI_AUTO_REINDEX=true`; domain_hint short-circuits tag classification; startup log prints the active extraction endpoint.
- **Won't**: auto-merge of duplicates below the upsert threshold; PDF parsing; multi-space concurrency within a single ingest call.

**Acceptance criteria:**
1. `wiki_ingest(source=<arxiv_url>, space_id=<id>)` creates ≥ 1 Entity and ≥ 1 Concept with bidirectional relations, and a Source object.
2. Ingesting the same URL twice updates existing objects (0 created, ≥ 1 updated) — idempotence above upsert threshold.
3. An ingest partial failure produces a WikiLog entry, a coherent `objects_created/objects_updated/warnings` response, and `status: "partial"`.
4. A URL that 302-redirects to `127.0.0.1:31012` is rejected with `[DATA ERROR] ssrf_blocked`.
5. A concurrent ingest call against the same space is rejected with `[DATA ERROR] ingest_in_progress`; a concurrent call against a different space succeeds.
6. Normalized-title resolution matches "Bge-M3", "bge-m3", "  BGE-M3  ", and "BGE‑M3" (non-breaking hyphen) to the same entity.
7. Malformed extraction JSON triggers one repair attempt before failing.
8. All new tests green; full test suite green; `pip-audit` clean.

**Deliverables:**
- Files: those listed under "Scope (in)".
- Docs: README extends "How it works" with the ingest diagram; CHANGELOG entry; `.env.example` updated.
- Tests: covering URL fetch (with respx), SSRF rejection, file fetch, extraction happy+malformed paths, entity resolution, bidirectional relation rollback, partial-failure path.

**Dependencies:**
- v0.2.0 (schema + wiki_client + locks + normalize shipped).
- External: PATCH behavior decided by v0.2.0's verification script.

**Risks & mitigations:**
- *Risk: extraction quality varies wildly by source type.* Mitigation: prompt is versioned and committed under `wiki/prompts/extraction.md`; users can fork.
- *Risk: lock files go stale after crash.* Mitigation: locks record PID and start time; `wiki.ingest` on stale lock (PID gone) auto-clears with a warning in the WikiLog.
- *Risk: cost/privacy surprise with hosted extraction.* Mitigation: startup log prints active endpoint; README spells out the data flow.

**Pre-release checklist (v0.3.0):**
- [ ] Verification script rerun if any Anytype version bump since v0.2.0.
- [ ] `pytest tests/` all green.
- [ ] `pip-audit` clean.
- [ ] Ingest of 3 representative sources (short article, long paper, local markdown) run by hand.
- [ ] WikiLog verified in Anytype app.
- [ ] Git tag `v0.3.0`.

---

### v0.4.0 — `wiki.query`

**Scope (in):**
- `wiki/query.py` — tiered retrieval + 1-hop neighborhood fetch + synthesis + file-back.
- `wiki/cli.py` — extends with `wiki-query` subcommand.
- `server.py` — register `wiki_query` tool.
- `tests/wiki/test_query.py`.

**Scope (out):**
- Multi-space federation.
- ASMR-style multi-agent retrieval.
- Custom synthesis models per tool call (single model config for v0.4.0).

**Requirements (MoSCoW):**
- **Must**: index-navigation mode for < threshold; vector-augmented mode at/above threshold; file-back respects thresholds and per-call override; synthesis includes Anytype deeplinks; config error if schema missing.
- **Should**: `retrieval_mode` and `object_count_at_decision` included in response; per-run object cache; FilterExpression path decided by v0.2.0 verification.
- **Won't**: streaming responses; inline tool-use during synthesis.

**Acceptance criteria:**
1. Query on a wiki < 200 objects returns `retrieval_mode: "index_navigation"`.
2. Query on a wiki ≥ 200 objects returns `retrieval_mode: "vector_augmented"`.
3. Boundary test: a seeded wiki with 199, 200, and 201 objects respectively flips modes at exactly 200.
4. Query that meets file-back threshold creates a Query object with `wiki_drew_from` relations.
5. `file_back=False` suppresses file-back even if threshold met.
6. Query on a space with no wiki types returns `[CONFIG ERROR]` naming `wiki.bootstrap`.
7. Query on a wiki ≤ 200 objects returns in < 5s (p95).
8. All new tests green; full suite green.

**Deliverables:**
- Files under "Scope (in)".
- Docs: README's "Roadmap" updated; query-flow diagram added; CHANGELOG entry.
- Tests: covers tier boundary, file-back gate, config-error path, and 1-hop neighborhood cache hits.

**Dependencies:**
- v0.2.0 (schema).
- v0.3.0 (ingest — so the test fixtures can build a wiki). Query can technically run against a manually populated wiki but is only useful once ingest exists.

**Risks & mitigations:**
- *Risk: FilterExpression unexpectedly changes behavior.* Mitigation: rerun the verification script in pre-release; Tier 1 fallback documented.
- *Risk: synthesis latency > 5s on large neighborhoods.* Mitigation: cap neighborhood fetch at 20 objects; document the cap.

**Pre-release checklist (v0.4.0):**
- [ ] Verification script rerun; FilterExpression behavior confirmed.
- [ ] `pytest tests/` all green.
- [ ] Boundary test (199/200/201) exercised.
- [ ] Demo query against Jan's existing wiki.
- [ ] Git tag `v0.4.0`.

---

### v0.5.0 — `wiki.lint`

**Scope (in):**
- `wiki/lint.py` — 7 lint checks + potential-duplicates sweep.
- `wiki/cli.py` — extends with `wiki-lint` subcommand.
- `server.py` — register `wiki_lint` tool.
- `tests/wiki/test_lint.py`.

**Scope (out):**
- Auto-fix mode.
- Backlinks-API optimisation (deferred; tracked as OQ#7).

**Requirements (MoSCoW):**
- **Must**: 7 checks + severity grouping + duplicate sweep + severity_threshold filter + deeplinks.
- **Should**: batching to stay under 60s for 500 objects; per-run object cache.
- **Won't**: auto-resolve / auto-archive (v0.6+).

**Acceptance criteria:**
1. Orphan detection respects the 7-day grace period.
2. Pipeline orphan detection cross-references WikiLog partial-failure notes and flags immediately (no grace).
3. Asymmetric relation detection reports both object IDs with deeplinks.
4. Stale detection flags objects where `last_modified_date` < `wiki_ingested_at - WIKI_STALE_DAYS`.
5. `severity_threshold="critical"` returns only Critical findings.
6. 500-object wiki: lint returns in < 60s on Jan's Mac Mini M4 (p95 over 3 runs).
7. Empty types reported at Informational severity with count=0.

**Deliverables:**
- Files under "Scope (in)".
- Docs: README extended with lint example output; CHANGELOG entry.
- Tests: seed a wiki with known defects and assert every check fires.

**Dependencies:**
- v0.2.0 schema.
- May ship before v0.3.0/v0.4.0 if implementation parallelism allows, but v0.5.0 is tagged last by convention.

**Risks & mitigations:**
- *Risk: O(N) API calls miss the 60s budget at 500+ objects.* Mitigation: batching + caching now; Backlinks optimisation in v0.6+ if needed.
- *Risk: false-positive orphans.* Mitigation: 7-day grace period is the default and configurable.

**Pre-release checklist (v0.5.0):**
- [ ] Seeded fixture tests cover every check.
- [ ] Performance test at 500 objects.
- [ ] Git tag `v0.5.0`.

---

## Implementation Plan

### Module Layout

Proposed structure under `src/anytype_llm_wiki/` (verified against current repo; `wiki/` subdirectory and files do not exist in v0.1.0 and are added by v0.2.0+):

```
src/anytype_llm_wiki/
├── __init__.py                       # existing (v0.1.0)
├── anytype_client.py                 # existing read-only client; unchanged in v0.2.x
├── chunker.py                        # existing; unchanged
├── config.py                         # existing; v0.2.0 adds wiki env vars here (single source of truth)
├── embedder.py                       # existing; unchanged
├── indexer.py                        # existing; unchanged
├── server.py                         # existing; v0.2.0+ registers new wiki tools here
└── wiki/                             # new in v0.2.0
    ├── __init__.py                   # public exports: wiki_bootstrap, wiki_ingest, wiki_query, wiki_lint
    ├── wiki_client.py                # write client with module-scoped httpx.Client
    ├── types_schema.py               # canonical type + property definitions (the "SCHEMA" source of truth)
    ├── bootstrap.py                  # wiki.bootstrap implementation
    ├── ingest.py                     # wiki.ingest implementation (v0.3.0)
    ├── query.py                      # wiki.query implementation (v0.4.0)
    ├── lint.py                       # wiki.lint implementation (v0.5.0)
    ├── extraction.py                 # LLM extraction pipeline (v0.3.0)
    ├── fetch.py                      # URL fetching with SSRF guard + HTML→md (v0.3.0)
    ├── normalize.py                  # normalize_title and related helpers
    ├── locks.py                      # per-space filesystem lock
    ├── cli.py                        # argparse-based CLI entry point for wiki-* subcommands
    └── prompts/
        └── extraction.md             # versioned extraction prompt (v0.3.0)
```

One-line responsibility per file (already listed in the layout; grouped above for discoverability).

### Public API / MCP tool signatures

All four MCP tools are registered in `src/anytype_llm_wiki/server.py` using `@mcp.tool()`. The exact signatures (Python 3.11+):

```python
# v0.2.0
@mcp.tool()
def wiki_bootstrap(
    space_id: str,
    domain_tags: list[str] | None = None,
) -> dict:
    """Create the wiki schema (types, properties, tags, root Collection) in the given space.

    Idempotent: re-running on an already-bootstrapped space creates no duplicates
    and reports skipped elements.
    """

# v0.3.0
@mcp.tool()
def wiki_ingest(
    source: str,
    space_id: str,
    domain_hint: str | None = None,
) -> dict:
    """Ingest a source (URL or absolute file path) into the wiki."""

# v0.4.0
@mcp.tool()
def wiki_query(
    question: str,
    space_id: str,
    file_back: bool | None = None,
) -> dict:
    """Query the wiki and return a synthesized answer with citations."""

# v0.5.0
@mcp.tool()
def wiki_lint(
    space_id: str,
    severity_threshold: str = "all",
) -> dict:
    """Run lint checks across the wiki and return a severity-grouped report."""
```

Internal function signatures (illustrative, may change during implementation):

```python
# wiki/normalize.py
def normalize_title(raw: str) -> str: ...

# wiki/wiki_client.py
class WikiClient:
    def __init__(self) -> None: ...          # holds a module-scoped httpx.Client
    def create_type(self, space_id: str, type_def: dict) -> dict: ...
    def create_property(self, space_id: str, type_key: str, prop_def: dict) -> dict: ...
    def create_tag(self, space_id: str, property_key: str, tag: str) -> dict: ...
    def search(self, space_id: str, query: str, filter: dict | None = None) -> list[dict]: ...
    def create_object(self, space_id: str, type_key: str, name: str, properties: dict, body: str | None = None) -> dict: ...
    def update_object(self, space_id: str, object_id: str, patch: dict) -> dict: ...
    def close(self) -> None: ...

# wiki/locks.py
from contextlib import contextmanager
@contextmanager
def space_ingest_lock(space_id: str) -> Iterator[None]: ...

# wiki/fetch.py
def fetch_source(source: str) -> tuple[str, dict]:  # returns (markdown, metadata)
    ...

# wiki/extraction.py
def extract(markdown: str, domain_hint: str | None) -> dict:  # validated JSON
    ...
```

### Data-flow diagrams

See inline Mermaid diagrams in [Ingest Pipeline](#ingest-pipeline-wikiingest--v030), [Query Pipeline](#query-pipeline-wikiquery--v040), and [Lint Suite](#lint-suite-wikilint--v050). Three diagrams total.

### Entity Resolution Semantics

**`normalize_title` contract** (addresses council ADVISORY #8):

```python
# wiki/normalize.py
import re
import unicodedata

_WS_RE = re.compile(r"\s+")

def normalize_title(raw: str) -> str:
    """Normalize an entity/concept title for exact-match comparison.

    Steps (in order):
      1. Unicode NFC normalization (compose precomposed forms).
      2. Unicode casefold (aggressive case-insensitive comparison,
         handles German sharp-s, Turkish dotted-i, etc.).
      3. Collapse all whitespace runs to a single ASCII space.
      4. Strip leading/trailing whitespace.

    Note: we deliberately do NOT strip punctuation or hyphens —
    "GPT-4" and "GPT 4" are distinct entities.
    """
    nfc = unicodedata.normalize("NFC", raw)
    casefolded = nfc.casefold()
    collapsed = _WS_RE.sub(" ", casefolded)
    return collapsed.strip()
```

**Resolution pseudocode:**

```python
# wiki/ingest.py (ingest-time entity resolution)
def resolve_entity(client: WikiClient, space_id: str, type_key: str,
                   candidate_title: str, candidate_embedding: list[float]) -> ResolveResult:
    normalized = normalize_title(candidate_title)

    # Step 1 — normalized-title exact match
    matches = [
        o for o in client.search(space_id, query=candidate_title, filter={"type_key": type_key})
        if normalize_title(o["name"]) == normalized
    ]
    if matches:
        return ResolveResult(action="update", target=matches[0])

    # Step 2 — embedding similarity sweep via Qdrant
    top = qdrant_nearest(candidate_embedding, type_key=type_key, limit=5)

    if top and top[0].score >= UPSERT_THRESHOLD_EMBEDDING:   # default 0.85
        return ResolveResult(action="update", target=top[0].object)

    if top and top[0].score >= DUPLICATE_SURFACE_FLOOR:      # default 0.70
        return ResolveResult(
            action="skip_duplicate_proposed",
            target=top[0].object,
            score=top[0].score,
        )

    # Step 3 — no match; create if page threshold met
    return ResolveResult(action="create_if_threshold")
```

### Extraction Prompt Structure

Stored in `src/anytype_llm_wiki/wiki/prompts/extraction.md`. Loaded at module import. Rendered with a lightweight `str.format` (no Jinja needed). The prompt is a single committed file so it can be reviewed, diffed, and forked by contributors.

**Prompt shape (abridged):**

```
You are an entity-and-concept extractor for the Anytype LLM Wiki.

INPUT
<source content, truncated to N tokens>

OUTPUT
Return ONLY a single JSON object matching this schema (no prose, no backticks):

{
  "entities":   [{"name": str, "description": str, "is_central": bool, "domain_tags": [str]}],
  "concepts":   [{"name": str, "definition": str, "is_central": bool, "open_questions": [str], "domain_tags": [str]}],
  "relations":  [{"from": str, "to": str, "label": str}],
  "summary":    str
}

RULES
- Names must be canonical (e.g. "bge-m3", not "the bge-m3 model").
- `is_central=true` for entities the source is primarily about.
- Do not invent relations: both endpoints must appear in `entities` or `concepts`.
- If the source is empty or non-textual, return all empty arrays and `summary: "empty_source"`.
```

**Error handling:**
- Response is parsed with `json.loads`. On `JSONDecodeError`, the ingest pipeline retries once with a repair prompt: *"The previous response could not be parsed as JSON. Return only valid JSON matching the schema."*
- If the retry also fails, the ingest returns `[DATA ERROR] extraction_failed: {parse_error}`. The Source object is still created (the WikiLog records the failure) so the user can retry extraction manually.

### Verification Script

`scripts/verify-anytype-writes.sh` — committed to the repo in v0.2.0. Runs the three live-API probes from the product spec's Appendix A:

1. **PATCH body update:** writes a timestamped marker, re-reads, compares.
2. **PATCH property update:** writes a timestamped name, re-reads, compares.
3. **FilterExpression:** runs unfiltered search, type-filtered search, and impossible-type-filtered search; compares counts.

Output: a single decision block written to stdout AND appended to `.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/patch-decision.md`:

```
ANYTYPE_VERIFICATION_DECISION
  anytype_version:         2025-11-08
  timestamp:               2026-04-24T10:03Z
  patch_body_updates:      works | silently_ignored | error
  patch_property_updates:  works | silently_ignored | error
  filter_expression:       works | no_op | partial
  implementation_path:     primary_patch | fallback_properties_only
END
```

The v0.3.0 implementation reads `patch-decision.md` during code review; reviewers fail the PR if the shipped path does not match the recorded decision. The script is shell-only (curl + jq) and requires `ANYTYPE_API_KEY`, `ANYTYPE_SPACE_ID`, `ANYTYPE_OBJECT_ID` in the environment.

### Tests Layout

Mirror the source layout under `tests/wiki/` and keep `tests/test_*.py` pattern for root-level v0.1.0 files. Add `tests/wiki/__init__.py`.

```
tests/
├── __init__.py
├── test_anytype_client.py            # existing
├── test_chunker.py                   # existing
├── test_embedder.py                  # existing
├── test_indexer.py                   # existing
├── test_server.py                    # existing; extended to assert wiki tools registered
└── wiki/
    ├── __init__.py
    ├── test_bootstrap.py             # v0.2.0
    ├── test_wiki_client.py           # v0.2.0
    ├── test_normalize.py             # v0.2.0
    ├── test_locks.py                 # v0.2.0
    ├── test_types_schema.py          # v0.2.0
    ├── test_fetch.py                 # v0.3.0
    ├── test_extraction.py            # v0.3.0
    ├── test_ingest.py                # v0.3.0
    ├── test_query.py                 # v0.4.0
    └── test_lint.py                  # v0.5.0
```

**Mock strategy (addresses council ADVISORY #5):**

- **Unit tier (default CI run):** `respx` mocks `httpx` calls (Anytype + Ollama). Qdrant is mocked via a small in-memory stub class. No network, no live services. `uv run pytest tests/` is this tier.
- **Integration tier (opt-in, `--integration` flag):** live Anytype desktop + live Qdrant + live Ollama on the developer's machine. Skipped in CI; run manually in pre-release checklists. Uses a dedicated throwaway Anytype space named `anytype-llm-wiki-test`.
- **Cassette tier (optional, v0.4.0+):** `pytest-recording` / VCR cassettes capture live Anytype responses once, replay forever. Used only for tests where live behavior is load-bearing (FilterExpression, PATCH body). Cassettes checked into `tests/wiki/cassettes/` alongside the test.
- **Time manipulation:** stale-object and orphan grace-period tests use `freezegun` (add to dev dependencies in v0.5.0) or explicit `wiki_ingested_at` manipulation on seeded objects.
- **Failure simulation:** `respx` returns configured HTTP statuses; extraction-failure tests patch `extraction.extract` to return malformed JSON.

---

## Operational Considerations

### Observability

Every MCP tool returns a WikiLog-shaped receipt (even on failure). Logs are emitted to stderr as single-line JSON so end-users can `grep` and `jq`. Standard log keys:

| Key | Type | Description |
|---|---|---|
| `ts` | ISO 8601 | Event timestamp |
| `tool` | string | `wiki_bootstrap` / `wiki_ingest` / `wiki_query` / `wiki_lint` |
| `space_id` | string | Target space |
| `action` | string | `start` / `progress` / `complete` / `error` |
| `status` | string | `ok` / `partial` / `error` (terminal events) |
| `wiki_log_id` | string | Anytype WikiLog object ID (if created) |
| `duration_ms` | int | Elapsed time (terminal events) |
| `error_category` | string | `api_error` / `data_error` / `config_error` (error events) |
| `error_detail` | string | Human-readable error (error events) |
| `extraction_endpoint` | string | Hosted-model URL if used (ingest startup only; see Security) |

Example ingest startup log:

```json
{"ts":"2026-04-22T10:03:00Z","tool":"wiki_ingest","space_id":"bafy...","action":"start","extraction_endpoint":"http://127.0.0.1:11434"}
```

The WikiLog object in Anytype is the durable record. The JSON log is the runtime observability stream for operators. Both are always written at terminal events (success or failure), except when Anytype is unreachable — in that case only the JSON log exists.

### Configuration

All new v0.2.0+ environment variables, plus existing v0.1.0 variables for reference:

| Variable | Default | Ships in | Purpose |
|----------|---------|----------|---------|
| `ANYTYPE_API_URL` | `http://127.0.0.1:31012` | v0.1.0 | Anytype REST endpoint |
| `ANYTYPE_API_KEY` | (required) | v0.1.0 | Bearer token |
| `ANYTYPE_API_VERSION` | `2025-11-08` | v0.1.0 | API version header |
| `QDRANT_URL` | `http://127.0.0.1:6333` | v0.1.0 | Qdrant endpoint |
| `QDRANT_API_KEY` | (empty) | v0.1.0 | Qdrant auth |
| `QDRANT_COLLECTION` | `anytype_semantic` | v0.1.0 | Qdrant collection name |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | v0.1.0 | Ollama endpoint |
| `EMBED_MODEL` | `bge-m3` | v0.1.0 | Embedding model |
| `EMBED_DIMS` | `1024` | v0.1.0 | Vector dimensions |
| `INDEX_STATE_DIR` | `~/.local/share/anytype-llm-wiki` | v0.1.0 | Index state location |
| `WIKI_LOCK_DIR` | `~/.local/share/anytype-llm-wiki/locks` | v0.2.0 | Per-space ingest lock files |
| `WIKI_EXTRACT_MODEL` | value of `EMBED_MODEL`'s Ollama host, `qwen2.5:7b` model | v0.3.0 | LLM for entity/concept extraction (provisional default — see OQ#3) |
| `WIKI_EXTRACT_ENDPOINT` | `OLLAMA_URL` | v0.3.0 | Base URL for extraction LLM (set to a hosted API to route off-machine) |
| `WIKI_UPSERT_THRESHOLD_TITLE` | `0.92` | v0.3.0 | Title-similarity auto-upsert cutoff (provisional) |
| `WIKI_UPSERT_THRESHOLD_EMBEDDING` | `0.85` | v0.3.0 | Embedding-similarity auto-upsert cutoff (provisional) |
| `WIKI_DUPLICATE_SURFACE_FLOOR` | `0.70` | v0.3.0 | Below upsert, above this → `duplicate_proposed` |
| `WIKI_AUTO_REINDEX` | `true` | v0.3.0 | Ingest triggers `reindex_anytype` on completion |
| `WIKI_INDEX_THRESHOLD` | `200` | v0.4.0 | Wiki size at/above which query switches to vector-augmented mode |
| `WIKI_FILE_BACK_MIN_SOURCES` | `3` | v0.4.0 | Minimum sources cited to file-back a Query |
| `WIKI_FILE_BACK_MIN_WORDS` | `100` | v0.4.0 | Minimum synthesis length to file-back |
| `WIKI_STALE_DAYS` | `90` | v0.5.0 | Staleness threshold |
| `WIKI_ORPHAN_GRACE_DAYS` | `7` | v0.5.0 | Grace for manually-created orphans |

### Concurrent Ingest Policy

**Addresses council ADVISORY #4.** v0.3.0 implements a filesystem-lock strategy:

- Lock path: `${WIKI_LOCK_DIR}/ingest-{space_id}.lock` (default root: `~/.local/share/anytype-llm-wiki/locks/`).
- Acquisition: `open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)`; on `FileExistsError`, read the lock to determine holder.
- Lock payload: JSON `{"pid": int, "started_at": ISO-8601, "source": str}`.
- Stale lock detection: if the recorded PID is not alive (via `os.kill(pid, 0)` raising `ProcessLookupError`), the lock is considered stale and silently replaced.
- Release: on ingest completion (success or error), the holder unlinks the file. A `contextmanager` (`wiki/locks.py::space_ingest_lock`) guarantees release on exception.
- Cross-space concurrency: unaffected — two spaces can ingest in parallel.
- Documented limitation: this is a single-host lock. Two machines concurrently ingesting the same space via a shared Anytype vault are not serialized. v0.3.0 documents this in the README. A distributed lock would need Anytype coordination primitives that do not exist today.

### Failure modes per tool

| Tool | Anytype 500 | Ollama unreachable | Qdrant unreachable | Extraction JSON malformed | Concurrent ingest |
|---|---|---|---|---|---|
| `wiki_bootstrap` | `[API ERROR]` + retry advice; partial bootstrap reported | N/A (no LLM) | N/A | N/A | N/A |
| `wiki_ingest` | `[API ERROR]`; WikiLog entry written if possible; `status: "partial"` with list of completed objects | `[API ERROR]`; no Source created; lock released | Tier-2 fallback cannot proceed; `[API ERROR]` logged; Source still created with `embedded=false` note | One repair retry; on failure `[DATA ERROR] extraction_failed` + Source object + WikiLog entry | `[DATA ERROR] ingest_in_progress` with lock holder info |
| `wiki_query` | `[API ERROR]`; no Query object created | Only blocks synthesis; `[API ERROR]` | Only blocks Tier 2; falls back to Tier 1 if threshold allows, else `[API ERROR]` | N/A (no extraction) | N/A |
| `wiki_lint` | `[API ERROR]`; partial findings returned if partial batch succeeded | N/A | Potential-duplicate sweep skipped; other checks complete; `warnings` notes Qdrant outage | N/A | N/A |

---

## Security Considerations

### Data locality

All operations target `localhost:31012` (Anytype), `localhost:6333` (Qdrant), and `localhost:11434` (Ollama) by default. No external data transmission except:

- URL fetching during `wiki.ingest` (egress to the source URL's host).
- Hosted-LLM extraction if `WIKI_EXTRACT_ENDPOINT` points off-machine (egress to that provider). The startup log and the README both flag this.

### SSRF protections (addresses council ADVISORY #9)

`wiki/fetch.py` applies the following policy to all URL fetches and their redirects:

```python
# wiki/fetch.py
import ipaddress
import socket
import httpx

_BLOCKED_NETS = [
    ipaddress.ip_network("127.0.0.0/8"),    # loopback
    ipaddress.ip_network("10.0.0.0/8"),     # RFC 1918
    ipaddress.ip_network("172.16.0.0/12"),  # RFC 1918
    ipaddress.ip_network("192.168.0.0/16"), # RFC 1918
    ipaddress.ip_network("169.254.0.0/16"), # link-local
    ipaddress.ip_network("::1/128"),        # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),       # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),      # IPv6 link-local
]

def _resolve_host(host: str) -> ipaddress._BaseAddress:
    return ipaddress.ip_address(socket.gethostbyname(host))

def _assert_public(url: httpx.URL) -> None:
    addr = _resolve_host(url.host)
    if any(addr in net for net in _BLOCKED_NETS) or addr.is_private or addr.is_loopback or addr.is_link_local:
        raise SsrfBlocked(f"refusing to fetch private/loopback address: {url.host} -> {addr}")
```

Enforcement:

- Initial URL: `_assert_public` before issuing the request.
- Redirects: httpx's `follow_redirects=False` is set; the fetch layer implements its own redirect loop, calling `_assert_public` on every `Location` header before continuing. Max 5 redirects.
- DNS rebinding mitigation: resolve once, connect by IP — httpx supports this via the transport layer. Accepted v0.3.0 limitation: we resolve once and trust the resolution; a full rebinding defense is out of scope.
- Raised as `[DATA ERROR] ssrf_blocked` with the offending host and resolved IP.

### Token handling

- Bearer token read from `ANYTYPE_API_KEY` env var only. Never written to disk, never logged (the structured logger masks `Authorization` header values).
- README explicitly warns users not to commit `.env` files.
- `pip-audit` runs in CI on each PR; flagged advisories block merge.

### Dependency pinning

- `pyproject.toml` pins dependencies to minor versions (e.g. `httpx>=0.27.0,<0.28.0`). v0.2.0 updates the existing pins to this policy; v0.3.0 adds `markdownify>=0.11.0,<0.12.0`.
- Pins are reviewed before each minor release; out-of-date pins that block security fixes are bumped in a patch release.
- `uv.lock` is committed.
- CI job: `pip-audit` on every PR; non-zero exit fails the build.

### LLM extraction data exfiltration

If `WIKI_EXTRACT_ENDPOINT` is not a localhost URL, every ingest transmits source content to the configured endpoint. This is documented in:

1. README's "Privacy and data flow" section (exact text in [Proposed Solution](#proposed-solution)).
2. The tool's startup log (`extraction_endpoint` field).
3. The CLI first-run banner: `anytype-llm-wiki wiki-ingest` prints a one-time warning if the endpoint is not `127.0.0.1`/`localhost`, and writes `~/.local/share/anytype-llm-wiki/extraction-endpoint-acknowledged` on user confirmation (suppressed on subsequent runs).

### Auth scope

v0.2.0's verification script includes a write-permission probe: creating a test Type, writing a test object, and cleaning them up. If the existing bearer token has insufficient scope, the script prints a precise remediation (regenerate token with write scope via Anytype Settings → API).

### Anytype desktop dependency

The Anytype API runs only when the desktop app is active. README documents this as a runtime prerequisite. No change from v0.1.0.

---

## Success Criteria

**v0.2.0 (`wiki.bootstrap`)**
- `wiki_bootstrap` creates all 6 Types, all Properties, the tag taxonomy, and a root Collection in a clean Anytype space in under 30 seconds.
- Running `wiki_bootstrap` on a space that already has wiki types produces no duplicates and reports correctly what was skipped vs. created.
- **Quick-start promise**: a contributor following README-only instructions can run `wiki.bootstrap(space_id=...)` in under 5 minutes from a fresh clone (measured from `git clone` with prerequisites already met).
- Verification script runs and records the PATCH/FilterExpression decision.

**v0.3.0 (`wiki.ingest`)**
- `wiki_ingest` correctly applies the page threshold policy.
- All Relations created by ingest are bidirectional (lint check: asymmetric Relations = 0 after any ingest run).
- A partial failure leaves a coherent WikiLog entry and does not silently lose the entities that were successfully created.
- `wiki_ingest` of the same source twice produces no duplicate objects.
- **Karpathy parity**: a Wikipedia article URL produces a committed set of Entity/Concept/Source objects with ≥ 2 relations each on completion.

**v0.4.0 (`wiki.query`)**
- `wiki_query` returns a synthesized answer with citations and deeplinks in **under 5 seconds for a wiki of ≤ 200 objects** (p95).
- Query objects meeting the file-back threshold appear in Anytype after the call.
- `wiki_query` on a space without schema returns a clear `[CONFIG ERROR]`.
- Boundary test: mode flips correctly at 199/200/201 objects.

**v0.5.0 (`wiki.lint`)**
- `wiki_lint` identifies orphans (zero inbound relations after > 7 days) at High severity with deeplinks.
- `wiki_lint` identifies asymmetric relations at Critical severity.
- **Performance target**: 500-object wiki lint returns in **under 60 seconds**.

**Community positioning**
- README "Why Anytype?" / "Comparison with filesystem LLM wikis" section matches the table in this spec.
- Quick-start (bootstrap → first ingest → first query) can be completed in under 15 minutes by a new user on a clean Anytype space, measured from `pip install anytype-llm-wiki` with all prerequisites already met.

**Evaluation timing:** Each version's criteria are evaluated at its pre-release checklist. Community positioning is re-evaluated at every minor release (v0.2.0, v0.3.0, v0.4.0, v0.5.0).

---

## Test Plan

Acceptance tests at the user level. Per [Tests Layout](#tests-layout), each version ships its own `tests/wiki/test_*.py` file. The suite must be green before tagging.

**Bootstrap (v0.2.0):**
- User runs `wiki_bootstrap` on a clean Anytype space → 6 Types appear with correct properties → response includes deeplinks.
- User runs `wiki_bootstrap` again on the same space → no duplicate Types/Properties created → response reports each element as "already exists, skipped".
- Invalid space_id → `[CONFIG ERROR]` with the space_id echoed.
- Anytype desktop not running → `[API ERROR]` with start instructions.
- Custom `domain_tags` replaces default taxonomy.

**Ingest (v0.3.0):**
- Arxiv URL ingest → Source + ≥ 1 Entity + ≥ 1 Concept + ≥ 2 relations each + WikiLog entry + deeplinks in response.
- Same URL twice → `objects_created == 0`, `objects_updated >= 1`.
- Source with only passing mentions → `objects_skipped` contains `reason: below_threshold`; no new objects for those entities.
- Post-ingest check in Anytype: A→B exists iff B→A exists (bidirectional).
- Anytype 500 during relation writing → partial ingest report + WikiLog entry with failure note + `status: "partial"`.
- **SSRF test (council ADVISORY #9):** URL that 302-redirects to `http://127.0.0.1:31012/something` is rejected with `[DATA ERROR] ssrf_blocked`; resolved IP is included in the error.
- **Entity resolution normalization test (council ADVISORY #8):** seeded entity "bge-m3" matches "Bge-M3", "bge‑m3" (non-breaking hyphen), and "  bge-m3  " via `normalize_title`.
- **Concurrent ingest test (council ADVISORY #4):** two overlapping `wiki_ingest` calls against the same space → second returns `[DATA ERROR] ingest_in_progress`; same-space sequential calls succeed; different-space concurrent calls both succeed.
- Malformed extraction JSON → repair retry → if still bad, `[DATA ERROR] extraction_failed` + Source object still created.

**Query (v0.4.0):**
- Question against seeded wiki → synthesized answer + deeplinks.
- Wiki of < `WIKI_INDEX_THRESHOLD` → `retrieval_mode: "index_navigation"`.
- Wiki of ≥ `WIKI_INDEX_THRESHOLD` → `retrieval_mode: "vector_augmented"`.
- **Boundary test (council ADVISORY #3):** seed wikis at 199, 200, 201 objects; assert mode at 199 is `index_navigation`, at 200 and 201 is `vector_augmented`.
- 3+ objects cited AND 100+ words → `filed_back: true`; Query object appears in Anytype.
- `file_back=False` → `filed_back: false` even if threshold met.
- No schema → `[CONFIG ERROR]` naming `wiki.bootstrap`.
- Latency: 100-object seeded wiki, query returns in < 5s (p95 over 20 runs) — counts as a perf test, skipped in CI and run manually.

**Lint (v0.5.0):**
- Manually create Entity with zero relations → simulate 7 days by setting `wiki_ingested_at` back → `wiki_lint` reports High severity orphan.
- Partially failed ingest leaves two entities without relations; WikiLog has partial-failure note → pipeline-orphan check flags them immediately (no grace).
- Manual edit breaks reciprocal → Critical severity asymmetric.
- Simulated stale object → Medium severity.
- `severity_threshold="critical"` returns only critical findings.
- 500-object wiki → returns in < 60s.

**Per-version coverage rule:** Every version tags only when its own tests are green AND all preceding versions' tests still green (regression guard).

---

## Open Questions

Each question carries a **Must resolve by** version. A version cannot tag if its owning questions are unresolved.

1. **PATCH body update behavior** — **Must resolve by v0.3.0 (verification script at v0.2.0 pre-release).** The ingest pipeline ships a single canonical path per the verification decision recorded in `patch-decision.md`. No dual paths in shipped code.

2. **FilterExpression in search** — **Must resolve by v0.4.0 (verification script at v0.2.0 pre-release).** Tier 1 selects its implementation based on the same `patch-decision.md`.

3. **Extraction model default** — **Must resolve by v0.3.0 pre-release.** Proposed: `qwen2.5:7b` on Ollama (local, open, 7B is plausible on 32GB Mac Mini). Jan's call. README names the recommendation; the code's provisional default is `qwen2.5:7b` with clear fallback to `EMBED_MODEL` host if that model is not pulled.

4. **File-back threshold** — **Must resolve by v0.4.0 pre-release.** Default: 3+ sources AND 100+ words. Re-evaluated at v0.4.0+1 based on Query-object noise/utility ratio in Jan's wiki.

5. **Community branding** — **Must resolve by v0.2.0 README update.** Current repo name is `anytype-llm-wiki`. Proposal: keep the repo name; the wiki module is "Anytype LLM Wiki" in documentation — no second brand. Jan's call.

6. **Write token permissions** — **Must resolve by v0.2.0 (verification script).** Verification script exercises a create-type call; if auth fails, README documents the regeneration step.

7. **Backlinks queryability via REST API** — **Must resolve by v0.6.x (post-v0.5.0 optimization).** Not blocking for v0.5.0 shipping; if Backlinks is queryable, orphan detection becomes O(1) per object and lint can scale beyond 500 objects.

---

## Deferred Items

**Multi-space / federated wiki queries.** Cross-domain synthesis across multiple Anytype spaces. The one-space-per-wiki-domain model is the explicit v0.2.x–v0.5.x design. Cross-domain queries require a federated search layer not warranted for v0.x. Filed as a follow-up ticket.

**LLM Wiki v2 enhancements (confidence scoring, supersession tracking, tiered consolidation).** Karpathy's community has developed extensions to the base pattern: confidence decay, explicit fact supersession, tiered memory consolidation. These increase implementation scope significantly. The base Hermes-parity implementation is the correct first target.

**ASMR-style multi-agent retrieval for the query pipeline.** Supermemory's ASMR technique achieves ~97-99% on LongMemEval. The query pipeline is designed pluggably (single-LLM synthesis today, agentic multi-LLM in a future iteration). The ASMR open-source code, once released, should be reviewed for the ingestion-agent knowledge-extraction architecture.

**Synthetic data generation and finetuning.** Karpathy explicitly names this as the natural next step after a wiki grows: generating question-answer pairs from wiki objects for model finetuning. Out of scope for this ticket. The Anytype typed-object model preserves provenance metadata that would support this in a future iteration.

**Visual output formats (Marp slides, matplotlib charts).** Anytype's native UI is the v0.x browsing surface. Rich output types are a follow-up.

**Auto-merge entity dedup below the confidence threshold.** The module surfaces potential duplicate Entity pairs for user review. Full automated dedup below the confidence threshold is deferred.

**Real-time webhook-based embedding refresh.** Anytype has no webhooks. The explicit post-ingest `reindex_anytype` call and the 30-minute launchd schedule are sufficient for v0.x. Webhook support would be an Anytype platform feature.

**`wiki.status(space_id)` lightweight health check tool.** A fast status command would be useful for daily operations. Deferred because v0.5.0 already provides `wiki.lint` with `severity_threshold="critical"` as a partial substitute. Reconsider after v0.5.0 ships.

**Refactor `anytype_client.py` and `wiki_client.py` to share a base session.** v0.2.0 introduces `wiki_client.py` with a module-scoped `httpx.Client` while `anytype_client.py` retains its per-call client pattern. This is intentional separation of concerns (read-only client unchanged). A v0.3.x+ follow-up ticket may unify them.

---

## Appendix A: API Verification Protocols

These protocols are implemented by `scripts/verify-anytype-writes.sh` (committed in v0.2.0). The decision output lands in `.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/patch-decision.md` and is referenced by the v0.3.0/v0.4.0 implementations.

**Prerequisites for all tests:** Anytype desktop running, a bearer token available (`$ANYTYPE_API_KEY`), a space ID (`$ANYTYPE_SPACE_ID`), and at least one existing object in the space (`$ANYTYPE_OBJECT_ID`). The Anytype API base URL is `http://127.0.0.1:31012`.

### A1: PATCH Body Update Verification

**Purpose:** Determine whether `PATCH /v1/spaces/{space_id}/objects/{object_id}` with a markdown `body` field actually updates the visible content of the object.

**Step 1: Read the current object body.**

```bash
curl -s -X GET \
  "http://127.0.0.1:31012/v1/spaces/$ANYTYPE_SPACE_ID/objects/$ANYTYPE_OBJECT_ID?format=md" \
  -H "Authorization: Bearer $ANYTYPE_API_KEY" \
  -H "Anytype-Version: 2025-11-08" \
  | jq '.body'
```

Record the current body.

**Step 2: PATCH with a new body containing a unique marker.**

```bash
curl -s -X PATCH \
  "http://127.0.0.1:31012/v1/spaces/$ANYTYPE_SPACE_ID/objects/$ANYTYPE_OBJECT_ID" \
  -H "Authorization: Bearer $ANYTYPE_API_KEY" \
  -H "Anytype-Version: 2025-11-08" \
  -H "Content-Type: application/json" \
  -d '{
    "body": "## PATCH Test Marker\n\nThis content was written by the PATCH verification test at '"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'. If this text is visible in the object body, PATCH body updates work."
  }'
```

**Step 3: Read the object body again.**

```bash
curl -s -X GET \
  "http://127.0.0.1:31012/v1/spaces/$ANYTYPE_SPACE_ID/objects/$ANYTYPE_OBJECT_ID?format=md" \
  -H "Authorization: Bearer $ANYTYPE_API_KEY" \
  -H "Anytype-Version: 2025-11-08" \
  | jq '.body'
```

**Interpreting results:**

| Step 2 status | Step 3 body contains "PATCH Test Marker"? | Conclusion |
|---|---|---|
| 200 OK | Yes | **PATCH body works.** Primary path: store descriptions in markdown body via PATCH. |
| 200 OK | No | **PATCH body is silently ignored.** Fallback path: descriptions in `wiki_description` / `wiki_facts` properties only. |
| 4xx/5xx | N/A | PATCH endpoint or auth issue. Debug before proceeding. |

Also verify Property PATCH independently:

```bash
curl -s -X PATCH \
  "http://127.0.0.1:31012/v1/spaces/$ANYTYPE_SPACE_ID/objects/$ANYTYPE_OBJECT_ID" \
  -H "Authorization: Bearer $ANYTYPE_API_KEY" \
  -H "Anytype-Version: 2025-11-08" \
  -H "Content-Type: application/json" \
  -d '{"name": "PATCH Property Test - '"$(date +%s)"'"}'
```

Then GET and confirm `name` changed.

### A2: FilterExpression Search Verification

**Step 1: Baseline count.**

```bash
curl -s -X POST \
  "http://127.0.0.1:31012/v1/spaces/$ANYTYPE_SPACE_ID/search" \
  -H "Authorization: Bearer $ANYTYPE_API_KEY" \
  -H "Anytype-Version: 2025-11-08" \
  -H "Content-Type: application/json" \
  -d '{"query": ""}' | jq '.data | length'
```

Record as TOTAL.

**Step 2: Filter to a specific type.**

```bash
curl -s -X POST \
  "http://127.0.0.1:31012/v1/spaces/$ANYTYPE_SPACE_ID/search" \
  -H "Authorization: Bearer $ANYTYPE_API_KEY" \
  -H "Anytype-Version: 2025-11-08" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "",
    "filter": {
      "condition": "and",
      "filters": [
        {"key": "type_key", "condition": "eq", "value": "note"}
      ]
    }
  }' | jq '.data | length'
```

Record as FILTERED.

**Step 3: Impossible filter.**

```bash
curl -s -X POST \
  "http://127.0.0.1:31012/v1/spaces/$ANYTYPE_SPACE_ID/search" \
  -H "Authorization: Bearer $ANYTYPE_API_KEY" \
  -H "Anytype-Version: 2025-11-08" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "",
    "filter": {
      "condition": "and",
      "filters": [
        {"key": "type_key", "condition": "eq", "value": "nonexistent_type_xyz"}
      ]
    }
  }' | jq '.data | length'
```

Record as ZERO_TEST.

**Interpreting results:**

| FILTERED < TOTAL? | ZERO_TEST == 0? | Conclusion |
|---|---|---|
| Yes | Yes | **FilterExpression works.** Tier 1 uses it for type filtering. |
| No | No | **FilterExpression is a no-op.** Tier 1 falls back to list-objects + client-side filter. |
| Yes | No | **Partial implementation.** Document which conditions work; fall back per-condition. |
| No | Yes | **Inconsistent.** Re-run; if reproducible, treat as "does not work". |
