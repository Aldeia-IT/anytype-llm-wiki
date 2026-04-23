# Product Brief: Wiki Library Module — Port LLM Wiki Pattern onto Anytype

**Date:** 2026-04-14
**Analyst:** product-analyst agent
**Ticket:** #140

---

## Target Persona(s)

- **Primary — Jan (Aldeia IT operator):** A solo technical consultant running an AI-augmented agency on a Mac Mini M4. Already uses Anytype as a personal knowledge base. Uses anytype-rag for semantic search inside the agent pipeline today. Needs a knowledge system that compounds — where ingesting a new article or source makes future agent queries smarter, without manual curation overhead. Is comfortable configuring and operating Python MCP servers. Constraint: budget-conscious on LLM tokens; the Mac Mini is shared infrastructure.

- **Secondary — Anytype community developer:** A technically sophisticated user who tracks the Anytype ecosystem, builds integrations, and is actively watching the LLM wiki space after Karpathy's April 2026 tweet went viral (16M views, 7+ community implementations in one week). Wants to use Anytype for knowledge management but finds existing LLM wiki tools Obsidian-native and cumbersome to adapt. Is looking for a clean, installable module — not a personal script.

- **Tertiary — Aldeia IT reputation signal:** This is not a user but a product goal: the anytype-rag repo is public and Jan wants it to demonstrate technical seriousness and community relevance. Visitors who land on the repo should immediately understand what the module does, how to install it, and why Anytype is the right substrate for an LLM wiki.

---

## Product Direction

The anytype-rag Wiki Library Module is an Anytype-native implementation of the Karpathy LLM wiki pattern — the first of its kind. Every community implementation that appeared in the week after Karpathy's viral tweet (nashsu/llm_wiki, lucasastorian/llmwiki, Ar9av/obsidian-wiki, and four others) is built on the filesystem + Obsidian stack. This module takes the same compile-once-maintain-over-time knowledge graph model and grounds it in Anytype's typed-object model, gaining structural properties that the filesystem approach cannot achieve: typed bidirectional relations that cannot break, closed-option tag taxonomies enforced at the data layer, and native property queries that eliminate the file-scanning heuristics Hermes' lint suite requires.

The core product insight Jan identified is correct: Anytype's knowledge graph is functionally more interesting than a directory of markdown files. Relations are object references, not strings. Renaming an entity does not break any link. Tags cannot drift outside the taxonomy. The "index.md" is a live Collection, not a file someone forgot to update. These aren't implementation details — they are architectural properties that solve three of the seven documented LLM wiki failure modes at the data-model layer rather than through lint rules and agent discipline. This is the differentiating claim the module should lead with.

The wiki module should be shipped as an installable extension to anytype-rag (same pip package, new MCP tools) with a fast getting-started experience. The target is: a technically capable Anytype user can have their first wiki space bootstrapped and their first source ingested in under 15 minutes. That experience — the install, the `wiki.bootstrap()` call, watching Anytype populate with typed objects — is the community hook. The research, the lint reports, the query compounding are the depth that earns repeat use and Jan's consulting credibility.

---

## Scope

### In Scope

- **Type schema bootstrap (`wiki.bootstrap`):** Programmatic creation of the full wiki type schema (Source, Entity, Concept, Comparison, Query, WikiLog) and property/tag taxonomy in a designated Anytype space. Idempotent — safe to re-run. Ships as an MCP tool and a CLI command. This is the must-ship-first deliverable that unblocks everything else.
- **Ingest pipeline (`wiki.ingest`):** CLI + MCP tool. Accepts a URL or file path, creates a Source object, extracts entities/concepts via LLM, upserts into Anytype with bidirectional Relations, appends WikiLog entry. Applies Hermes-derived page threshold policy (2+ source mentions OR central to source = create; passing mention = skip).
- **Query pipeline (`wiki.query`):** MCP tool. Semantic search over wiki types (using existing bge-m3 + Qdrant) → fetch full objects + 1-hop relation neighborhoods → synthesize answer → file-back as Query object if synthesis meets threshold. Index-first navigation strategy for small wikis (<200 articles), vector search augmentation for medium wikis.
- **Lint suite (`wiki.lint`):** MCP tool. Reports on orphans, stale objects, contradiction drift, page-size candidates. Output grouped by severity with Anytype deeplinks. Leverages native Anytype property queries rather than file scanning.
- **Operational policies (documented):** Page threshold, cross-link minimum (≥2 outbound Relations per new object), contradiction handling, archive workflow. Ported from Hermes SKILL.md with Anytype-specific adaptations.
- **Developer experience:** README with quick-start (bootstrap → first ingest → first query in <15 minutes), configuration reference, and an explicit "How this compares to filesystem LLM wikis" positioning section.
- **One space per wiki domain:** The default model is one Anytype space per wiki domain. The spec should make this the explicit and documented design choice.

### Out of Scope

- **Federated cross-space queries:** Out of scope for this ticket. Cross-domain synthesis goes through the query pipeline against a single space. Multi-space support filed as a follow-up.
- **Obsidian integration:** Anytype is the UI. No Obsidian export or compatibility layer.
- **Replacing the existing semantic search tools:** `semantic_search` and `reindex_anytype` remain unchanged. The wiki tools add on top.
- **LLM Wiki v2 enhancements (confidence scoring, supersession tracking, tiered consolidation):** Valuable but significantly increase scope. Defer to a follow-up ticket.
- **ASMR-style multi-agent retrieval:** The Supermemory ASMR result is relevant future art, but the full multi-agent query pipeline is out of scope. The query pipeline should be designed as pluggable so this can be added later.
- **Finetuning/synthetic data generation:** Karpathy named this as a future direction; not in scope here.
- **Visual output formats (Marp slides, matplotlib charts):** Karpathy uses these in his implementation. The Anytype native UI is sufficient for v1. Rich output types are a follow-up.
- **Auto-merge entity dedup below the confidence threshold:** The module will surface potential duplicates for user review below the configurable threshold. Auto-merge above threshold only.

---

## Requirements

### Must-Have

- `wiki.bootstrap(space_id)` MCP tool and CLI: creates full type schema (6 types, all properties, tag taxonomy) in the target Anytype space. Idempotent. Completion time under 30 seconds. Must verify PATCH body update behavior before spec is written (this is the highest-risk API question from research).
- `wiki.ingest(source, space_id, domain_hint?)` MCP tool: end-to-end ingest from URL or file → Source object → entity/concept extraction → Anytype upsert with bidirectional Relations → WikiLog entry. Applies page threshold policy. Returns a structured summary of objects created/updated.
- `wiki.query(question, space_id)` MCP tool: synthesized answer from wiki with object citations. File-back policy for substantial syntheses creates a Query object with `drew_from` relations.
- `wiki.lint(space_id)` MCP tool: severity-grouped report (critical/high/medium/low) with Anytype deeplinks. Covers orphans, stale objects, contradiction drift, oversized objects.
- Entity resolution: exact title match via Anytype API search before creating any new object. Embedding similarity check (bge-m3) for near-duplicate detection. Configurable auto-upsert threshold (default: 0.92 title match, 0.85 embedding similarity); below threshold, surface as a proposed merge for user review.
- Bidirectional relation writes: when creating a relation A→B, also write B→A. Lint rule for asymmetric relations.
- pip-installable as part of anytype-rag package. No new infrastructure dependencies beyond what anytype-rag already requires (Anytype desktop, Qdrant, Ollama/bge-m3).
- README quick-start: bootstrap → first ingest → first query in under 15 minutes on a clean Anytype space.

### Should-Have

- Tiered query strategy: index-navigation mode for wikis under 200 articles (skip vector search, query Anytype Collections directly), vector-augmented mode for wikis over 200 articles. Threshold configurable.
- `wiki_` key prefix convention for all wiki-managed tags to avoid conflicts with existing space tags.
- Anytype deeplinks in all tool output (e.g., `anytype://object/{space_id}/{object_id}`) so users can jump from an MCP response directly to the relevant object in the Anytype app.
- Explicit "comparison to filesystem LLM wikis" documentation section for community positioning.
- Archive workflow: set Anytype object status to archived (native Anytype state) rather than deletion. Relations to archived objects remain valid. No link-update cascade required.

### Won't-Have (this version)

- Multi-space/federated wiki queries: architectural complexity not warranted for v1. The space-per-domain model is sufficient for Jan's use cases and community introduction.
- Confidence decay and supersession tracking (LLM Wiki v2): increases complexity significantly. The base Hermes-parity implementation is the correct first target.
- ASMR-style multi-agent retrieval in the query pipeline: future spike. Query pipeline should be designed pluggably but ship with single-LLM synthesis.
- Real-time webhook-based embedding refresh: Anytype has no webhooks. Explicit post-ingest `reindex_anytype` call + 30-minute launchd schedule is sufficient.
- Synthetic data generation from wiki objects: a future direction Karpathy named, not in scope for this ticket.

---

## Gaps and Risks

- **PATCH body update behavior (BLOCKING):** The research identified a community report that `PATCH /v1/spaces/{space_id}/objects/{object_id}` body updates are silently ignored. This is unresolved. If confirmed, the ingest pipeline cannot update Entity/Concept descriptions — a fundamental requirement. The workaround (delete+recreate) loses object IDs and breaks all inbound Relations, which is significantly more complex. **This must be verified against the live Anytype API before the spec is written.** This is a targeted technical test, not more research. The spec writer or lead should do this manually before proceeding. If PATCH is broken, the spec must be written around delete+recreate semantics and the complexity implications for relation management must be explicitly addressed.

- **FilterExpression in search may be a no-op:** The `POST /v1/search` FilterExpression was reported as unimplemented in one community source. Fallback exists (list-objects endpoint with property query params, confirmed working). Lower risk but needs explicit verification. The spec should document both paths and the fallback.

- **Open-source packaging and install experience is understated in the ticket:** Jan explicitly asked about "product packaging, install, management functions." The ticket's deliverables are purely functional (types, pipelines, lint). The brief identifies these as first-class product requirements, not afterthoughts. The spec writer should treat the install experience (pip install, configuration, quick-start) as a named deliverable, not an implied side-effect of the implementation.

- **Community attraction requires more than the code:** Jan wants to "gain some attraction to what we're building at Aldeia IT." Code alone does not attract a community. The module needs a clear README that leads with the positioning story (Anytype-native LLM wiki, structurally superior to filesystem approaches), a quick-start, and a "Why Anytype?" section that translates the technical advantages into understandable benefits. This is not a deliverable for the spec writer but is a gap the lead should flag for Jan's attention before or after the PR.

- **Anytype desktop runtime dependency:** The Anytype REST API is only available when the Anytype desktop app is running. This is an existing constraint for anytype-rag, but it should be explicitly documented in the wiki module's README for community users who may not understand it. On the Mac Mini, this is already managed; for other users it is a deployment consideration.

- **Token cost for ingest:** Each ingest call hits the LLM to extract entities and concepts from the source. For a long article, this is 2,000-8,000 tokens minimum. For Jan's Mac Mini (Ollama), cost is compute time rather than money. For community users using hosted APIs, this is a real cost concern. The spec should allow configuration of the extraction model separately from the embedding model, so cost-conscious users can use a smaller model for extraction.

- **Entity duplication is not fully solved by Anytype:** The research correctly identifies that Anytype prevents broken links but does not prevent creating two distinct Entity objects for the same real-world entity. The embedding-similarity check mitigates this but does not eliminate it. The spec should be honest about this limitation and the lint suite should include a "potential duplicates" report (Entity pairs above a similarity threshold but below the auto-upsert threshold).

- **The `phase-summary-research-rerun.md` notes worktree write access blocked by sandbox:** This is an operational issue, not a product gap, but it means the lead should verify the impl-worker has appropriate file write permissions to the anytype-rag worktree when implementation begins.

---

## UX Assessment

No significant UI design work is needed for this module. All user interaction happens through:
1. MCP tool calls (Claude, cursor, or other MCP client)
2. The Anytype desktop app (viewing/browsing objects created by the module)
3. CLI commands for bootstrap and ingest

The module does not own any UI surface. The Anytype app is the "frontend" — the module's job is to populate it with well-structured objects.

However, there are **MCP tool interface design decisions** the spec writer should treat carefully:
- Tool parameter names and return schemas are the user interface. They must be clear, consistent, and minimal.
- Return values from `wiki.ingest` and `wiki.lint` should include Anytype deeplinks to make MCP responses immediately actionable.
- Error messages from all tools should distinguish between "API error" (Anytype unreachable, auth failure) and "data error" (entity resolution conflict, relation type mismatch).

No UX designer dispatch needed. These are spec-level decisions.

---

## Recommended Research

- **Agent:** technical-researcher
  **Question:** Does `PATCH /v1/spaces/{space_id}/objects/{object_id}` actually update the markdown body of an object, or are body updates silently ignored? Test against a live Anytype API instance with a concrete example. If broken, document the exact behavior and confirm whether delete+recreate preserves inbound Relations (i.e., do other objects' `objects`-format properties pointing to the deleted object ID remain valid after recreation with a new ID?).
  **Why:** This is the single highest-risk technical question. If PATCH body updates are broken, the entire ingest update path must be redesigned. The spec cannot be written correctly without knowing the answer.

---

## Open Questions

1. **PATCH body update behavior** — see Gaps and Risks. Must resolve before spec.
2. **Extraction model selection:** What LLM should the ingest pipeline use for entity/concept extraction? Ollama/local model for cost control vs. hosted frontier model for quality? The spec should make this configurable, but the default choice should be Jan's call.
3. **File-back threshold for Query objects:** When should a query synthesis be filed back as a Query object? Options: always (noisy), above a word count (arbitrary), manually triggered, or when the synthesis draws from 3+ objects. Hermes does not specify this; Karpathy implies always. The spec writer should propose a sensible default and make it configurable.
4. **Community branding:** Should this be presented as "anytype-rag wiki module" or does it merit a distinct name? A distinct name (e.g., "Anytype LLM Wiki") would be more memorable and community-searchable, but adds fragmentation risk. Jan's call.
5. **Phase ordering:** The ticket recommends shipping the type schema (Deliverable 1) as a standalone first PR. The brief endorses this — it unblocks content collection while the pipelines are built. The spec should structure deliverables accordingly, with the bootstrap tool as a clearly separable first implementation milestone.

---

## Inputs Consulted

- `.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/research-synthesis.md` — primary synthesis, 8 recommendations, risk table. Most authoritative single source.
- `.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/market-research.md` — Karpathy pattern, Hermes implementation details, 7 failure modes, competitive landscape, what to carry forward / adapt / avoid.
- `.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/market-research-update.md` — corrected analysis with actual tweet content. Karpathy scale claim (~100 articles, no RAG needed), ASMR characterization, file-back as explicit compounding mechanism, ecosystem velocity (7 implementations in one week, all filesystem-based).
- `.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/technical-research.md` — anytype-rag architecture, full Anytype API audit, bidirectional relation constraints, feasibility assessment.
- GitHub issue #140 — original ticket, open questions, Jan's feedback comment of 2026-04-14.
- Jan's feedback (2026-04-14T19:05:00Z) — open-source positioning as primary goal, Anytype knowledge graph differentiator, product packaging/install/management functions as named requirements.
