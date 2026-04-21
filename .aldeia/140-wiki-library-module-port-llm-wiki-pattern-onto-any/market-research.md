# Market & Prior Art Research: Wiki Library Module

**Date:** 2026-04-13
**Researcher:** market-researcher
**Ticket:** #140

---

## M1: Karpathy LLM Wiki Pattern

### Core Design Principles

Karpathy's LLM Wiki pattern (published as a GitHub Gist, ~5,000 stars within days of the April 2026 tweet thread) describes a persistent, compounding knowledge base maintained by an LLM. The fundamental insight: **LLMs should compile knowledge once, not rediscover it per query.**

The division of labor is explicit:
- **Human:** curates sources, asks questions, exercises judgment
- **LLM:** handles all bookkeeping — summarization, cross-referencing, consistency maintenance, index updates, log entries

The pattern draws explicit comparison to Vannevar Bush's 1945 Memex vision but solves the maintenance problem Bush couldn't: the LLM is the diligent worker who never tires of cross-linking.

### Three-Layer Architecture

**Layer 1 — Raw Sources (immutable)**
The human-curated document corpus. LLM reads but never modifies. Articles, papers, transcripts, images.

**Layer 2 — The Wiki (LLM-owned)**
Markdown files generated and maintained by the LLM, organized by content type:
- `entities/` — pages for people, organizations, products, models
- `concepts/` — topic and technique pages
- `comparisons/` — side-by-side analyses
- `queries/` — filed query results worth preserving

**Layer 3 — Schema**
A configuration document (SCHEMA.md or CLAUDE.md) specifying wiki structure, conventions, tag taxonomy, and operational workflows. Co-evolved between user and LLM over time.

### Data Model

Every wiki page is a Markdown file with YAML frontmatter:
```yaml
---
title: Page Title
created: YYYY-MM-DD
updated: YYYY-MM-DD
type: entity | concept | comparison | query | summary
tags: [from taxonomy]
sources: [raw/articles/source-name.md]
---
```

Navigation infrastructure:
- **index.md** — catalog of all wiki pages, one-line summaries per page, organized by category
- **log.md** — append-only chronological record of all operations (ingest, query, lint, archive)

### Operational Policies

**Ingest:** User drops new source → LLM reads, extracts takeaways → writes/updates wiki pages → updates index → appends log entry. A single source may touch 10-15 wiki pages.

**Query:** LLM searches index → reads relevant pages → synthesizes answer with citations → valuable answers filed back as new Query pages.

**Lint:** Periodic health checks for contradictions, stale claims, orphan pages (no inbound links), concepts lacking dedicated pages, data gaps.

### How It Differs from RAG

| Dimension | RAG | LLM Wiki |
|-----------|-----|----------|
| Synthesis | Per-query (re-derived each time) | Compiled once, maintained |
| Knowledge accumulation | None — stateless | Compounds over time |
| Cross-references | None — chunk-level retrieval | Pre-built into structure |
| Contradictions | Not tracked | Flagged at ingest |
| Scale | Requires retrieval infrastructure | Index file works to ~200 pages |
| Human effort | Upload sources, ask questions | Same, plus source curation |

The wiki is not a replacement for RAG at large scale — Karpathy explicitly notes that at 100+ sources / hundreds of pages, optional search tools (BM25/vector via `qmd`) augment but don't replace the compiled structure.

### What the Tweet Thread Added

The April 2026 tweet thread (status/2039805659525644595; page returned 402 — Twitter paywall) expanded on practical deployment. Based on contemporaneous blog coverage and the community implementations it spawned, the thread emphasized:
- The pattern works immediately with tools like Claude Code and Cursor via AGENTS.md/CLAUDE.md bootstrap files
- Obsidian as the viewing interface
- MCP servers as the standardized LLM tool interface for the pipeline
- The gist is intentionally abstract — directory structure and schema conventions depend on domain

---

## M2: Hermes Agent llm-wiki Implementation

### Overview

NousResearch's Hermes agent implemented the LLM Wiki pattern as a structured skill in PR #5635. This is the most complete reference implementation of Karpathy's pattern with production-tested design decisions.

### Filesystem Structure

```
wiki/
├── SCHEMA.md              # Domain definition, conventions, tag taxonomy
├── index.md               # Catalog of all pages with one-line summaries
├── log.md                 # Append-only operations log
├── raw/
│   ├── articles/          # Web clippings
│   ├── papers/            # PDFs and arxiv papers
│   ├── transcripts/       # Meeting notes, interviews
│   └── assets/            # Images and diagrams
├── entities/              # People, organizations, products, models
├── concepts/              # Topics and techniques
├── comparisons/           # Side-by-side analyses
├── queries/               # Filed query results
└── _archive/              # Superseded pages (preserved, not deleted)
```

### YAML Frontmatter (all fields required)

```yaml
---
title: Page Title
created: YYYY-MM-DD
updated: YYYY-MM-DD
type: entity | concept | comparison | query | summary
tags: [from taxonomy]
sources: [raw/articles/source-name.md]
---
```

When a page has contradicting information from different sources:
```yaml
contradictions: [conflicting-page-name]
```

### Page Threshold Policy

- **Create:** entity/concept appears in 2+ sources OR is central to one source
- **Add to existing:** source mentions already-covered content
- **Skip:** passing mentions, minor details, out-of-scope items
- **Split:** pages exceeding ~200 lines → sub-topics with cross-links
- **Archive:** fully superseded content → move to `_archive/`, remove from index

### Cross-Linking Policy

- Minimum 2 outbound `[[wikilinks]]` per page
- Bidirectional linking when semantically appropriate
- Existing pages must link back to new pages
- Orphaned pages (zero inbound links) are lint violations

### Entity Resolution

Before creating any page: search existing pages via `search_files` against both index and filename. Prevents duplicate pages for the same entity under slightly different names. No automated fuzzy-match dedup — relies on LLM judgment with index as ground truth.

### Update Policy on Contradictions

1. Check dates — newer sources generally supersede
2. If genuinely contradictory: document both positions with dates and sources
3. Mark `contradictions:` in frontmatter
4. Flag for user review in lint reports
5. Never silently overwrite — preserve audit trail

### Archive Workflow

1. Create `_archive/` if needed
2. Move page preserving path structure
3. Remove from `index.md`
4. Update linking pages (replace wikilink with plain text + "(archived)")
5. Log the action

### Lint Checks

Severity-grouped report:
1. **Critical:** Broken wikilinks (target doesn't exist)
2. **High:** Orphan pages (no inbound links), index completeness
3. **Medium:** Frontmatter validation, tags outside taxonomy, stale content (updated >90 days older than related sources)
4. **Low:** Oversized pages (>200 lines), contradiction flags not user-reviewed
5. **Meta:** Log rotation (>500 entries → rename to `log-YYYY.md`), index sub-sectioning (>50 entries per section)

### Session Startup Requirement (Critical)

Before any operation on an existing wiki, the agent MUST:
1. Read `SCHEMA.md`
2. Read `index.md`
3. Scan recent `log.md` entries (last 20-30 lines)

This is the primary defense against duplicates and missed cross-references.

### Documented Limitations

- **Single global wiki path:** `wiki.path` is globally singular — no project-aware resolution. A follow-up issue (#5655) was filed to add per-project resolution via `.hermes.md` frontmatter.
- **Entity resolution is LLM-trust-dependent:** The system relies on the LLM searching and recognizing existing pages. Fuzzy/near-duplicate detection is not automated.
- **No confidence scoring:** All facts are equally weighted regardless of source count or recency.
- **Manual contradiction resolution:** Contradictions are flagged but humans must resolve them.
- **Obsidian headless complexity:** Server deployments without display need `obsidian-headless` + Obsidian Sync — adds operational overhead.

### Changes from Karpathy's Original

The Hermes implementation significantly expanded Karpathy's abstract pattern:
- Added mandatory session orientation (SCHEMA → index → log before any operation)
- Formalized page lifecycle (thresholds, split, archive)
- Enforced tag taxonomy in SCHEMA.md
- Added explicit contradiction handling
- Added scaling guidance (index sub-sections at 50, topic maps at 200+, log rotation at 500+)
- Structured lint as a graded severity report

---

## M3: MemPalace

### What It Is

MemPalace is an open-source local AI memory system focused on preserving **complete conversation history** without summarization. The stated philosophy: "store everything, then make it findable" — rather than having AI decide what matters upfront.

### Data Model — The Palace Metaphor

Hierarchical organization borrowed from the classical memory palace mnemonic:
- **Wings** — Projects or people (top-level units)
- **Rooms** — Topics within a wing (auth, billing, deployment)
- **Halls** — Memory types (facts, events, discoveries, preferences, advice)
- **Closets** — Summary pointers to original content
- **Drawers** — Verbatim original files
- **Tunnels** — Cross-wing connections when the same room appears in multiple wings

### Storage Backend

- **ChromaDB** — vector database for semantic search
- **SQLite** — knowledge graph storing entity-relationship triples with temporal validity windows
- Entirely local — no cloud dependencies

### Query Mechanism

Structured metadata filtering dramatically outperforms flat semantic search:
- Unfiltered: 60.9% recall
- Wing filtering only: 73.1% recall
- Wing + room filtering: 94.8% recall (+34% vs unfiltered)

MCP server for Claude, ChatGPT, Cursor integration. CLI: `mempalace init`, `mine`, `search`.

### Comparison to LLM Wiki Pattern

| Dimension | LLM Wiki | MemPalace |
|-----------|----------|-----------|
| Philosophy | Compile knowledge, synthesize explicitly | Store everything verbatim |
| Content | Agent-synthesized markdown | Raw conversation transcripts |
| Structure | Agent-maintained, human-browsable | Auto-organized by metaphor hierarchy |
| Synthesis | Done at ingest time | Done at query time |
| Scale | ~100s of pages | All conversations |
| Human effort | Source curation + validation | Nearly zero (auto-organizes) |
| Risk | Knowledge loss through compression | Context noise from verbatim storage |

**Key differentiator:** MemPalace preserves implicit decision reasoning (the reasoning trail in a debugging session) that LLM wikis necessarily lose through summarization. The wiki pattern makes knowledge human-readable; MemPalace makes history machine-searchable.

**Reported accuracy:** 96.6% on LongMemEval — notably higher than Zep (63.8%) and Mem0 (49%), likely because verbatim storage avoids extraction errors.

### Assessment for This Ticket

MemPalace solves a different problem. It is conversation-history retrieval, not knowledge graph construction. It does not produce structured, interlinked, human-readable knowledge artifacts. For the anytype-wiki use case, MemPalace's verbatim approach would flood Anytype with raw transcripts rather than curated knowledge objects.

---

## M4: Agent Memory/Skills Insights

### From the ibl.ai Blog Post

The post (titled "Memory and Skills: What Turns an Agent Loop into a Real AI Agent") describes a four-file memory architecture for institutional agents:

- **SOUL.md** — identity, personality, operational boundaries
- **MEMORY.md** — accumulated facts learned through interactions
- **HISTORY.md** — key events and decisions log
- **USER.md** — explicit user preferences and instructions

A "Context Builder" assembles these files plus conversation history at each session start, providing cross-session continuity. This mirrors the Hermes pattern's session startup orientation (SCHEMA → index → log).

Key distinction articulated: **Memory = persistence of knowledge about identity/context across sessions. Skills = extensibility mechanism for new capabilities without core code changes.**

Architectural recommendation: two-tier skill loading — always-loaded skills for essential workflows, on-demand skills for optional capabilities. Plain-language skill configuration (instructions, not code) teaches agents new workflows.

### From DhravyaShah's Tweet (status/2035517012647272689)

The tweet page returned 402 (Twitter paywall). Based on community references and the research context, Shah's implementation appears to be an early practical port of the LLM Wiki pattern, likely demonstrating rapid iteration on Karpathy's pattern with Claude Code or similar tools. The key insight attributed to his thread in the community: the pattern works immediately without infrastructure investment — AGENTS.md and a wiki directory is sufficient to start.

### From LLM Wiki v2 (rohitg00 gist)

This community extension addresses what breaks in production:

**Confidence scoring:** Every fact carries a numerical confidence value (source count × recency × inverse contradiction count). Facts are not equally weighted — confidence decays with time, strengthens with reinforcement.

**Supersession tracking:** New information explicitly replaces old claims with versioned, timestamped linkage rather than orphaning stale facts.

**Memory consolidation tiers:**
1. Working memory (recent observations)
2. Episodic memory (session summaries)
3. Semantic memory (cross-session facts)
4. Procedural memory (workflows/patterns)

Content gets promoted upward as evidence accumulates — analogous to how human memory consolidates.

**Hybrid retrieval:** BM25 + vector search + graph traversal, fused via reciprocal rank fusion. Single index files degrade at ~200 pages; at 200+ pages the system shifts to hybrid retrieval.

**Event-driven automation:** Hooks fire on source ingestion, session boundaries, query thresholds, contradiction detection — eliminating manual bookkeeping.

### From A-MEM (NeurIPS 2025)

A-MEM (arxiv 2502.12110) takes a Zettelkasten-inspired approach where new memories automatically:
1. Generate structured notes (keywords, tags, contextual descriptions, embeddings)
2. Identify relevant historical memories via embedding similarity
3. Establish typed links to similar memories
4. Trigger updates to existing memory representations

This is the most academically rigorous formalization of the agent knowledge network pattern. Key results:
- 2x performance gains in multi-hop reasoning vs baselines
- 85-93% token reduction vs flat memory approaches
- Consistent superiority on LoCoMo and DialSim datasets

The "memory evolution" mechanism (new memories update existing ones) is the most novel contribution — the wiki does not just grow, it revises itself as understanding deepens.

### Competitive Landscape: The Broader Memory Market

| System | Approach | Storage | Entity Resolution | Temporal | Best For |
|--------|----------|---------|-----------------|----------|----------|
| **Mem0** | Hybrid vector+graph+KV | Managed cloud | Self-editing updates existing records | Timestamps only | Drop-in personalization |
| **Zep/Graphiti** | Temporal knowledge graph | PostgreSQL + embeddings | Bi-temporal (fact-valid + system-created) | Full temporal validity windows | Facts that change over time |
| **Letta/MemGPT** | OS-inspired tiered memory | External vector store | Manual tier promotion | Session-based | Long-running agents |
| **Cognee** | Poly-store (vector+graph+SQL) | Local Neo4j/FalkorDB/KuzuDB | Graph triplet extraction | Partial | Air-gapped, privacy-critical |
| **LLM Wiki (Karpathy)** | Compiled markdown | Filesystem | LLM-managed index | Updated dates | Human-browsable knowledge |
| **MemPalace** | Verbatim conversation store | ChromaDB+SQLite | Metaphor hierarchy | Temporal validity windows | Complete session recall |
| **A-MEM** | Zettelkasten note network | Vector DB | Embedding similarity + LLM judgment | Created dates | Multi-hop reasoning tasks |

**Important: Zep scores 63.8% on LongMemEval vs Mem0's 49.0%** — a 15-point gap driven by temporal architecture. Graph-based systems consistently outperform flat vector stores for facts that change over time.

**All general-purpose systems lack:**
- Business glossary / domain schema enforcement
- Typed bidirectional relations (they use string entity references)
- Closed-option taxonomies (they use free-form tags)
- Multi-device sync without cloud dependency

These gaps are precisely where Anytype's native data model wins.

---

## M5: Common Failure Modes and Mitigations

### Failure Mode 1: Entity Duplication / Near-Duplicate Proliferation

**Description:** The agent creates "GPT-4" and "GPT-4 (OpenAI)" and "OpenAI GPT-4" as separate pages. Over time the wiki has multiple partial pages for the same entity, none complete.

**Root cause:** LLM name recognition is fuzzy. Without a canonical registry, each ingest session may produce a different variant of the same entity name.

**Observed in:** All filesystem-based LLM wiki implementations. The Hermes SKILL.md explicitly warns "search for existing pages before creating new ones" as a critical pitfall.

**Mitigations:**
- Entity registry (JSON/YAML) mapping canonical names to aliases, checked before every create (LLM Wiki v2)
- Mandatory pre-session orientation: read index before any operation (Hermes)
- Embedding similarity check on proposed new pages (automated near-dup detection)
- Anytype advantage: title uniqueness can be enforced per Type; Relations use object references not strings — creating a duplicate object just creates a duplicate, it doesn't silently fragment the graph

### Failure Mode 2: Stale Content / Outdated Facts Never Corrected

**Description:** A page about "GPT-4 capabilities" written in 2024 sits unchanged as GPT-5, o3, and successors are ingested. New pages reference current models; old pages retain stale claims that contradict them.

**Root cause:** Ingest pipelines are better at creating than updating. Updating requires reading the existing page, which adds tokens. Update triggers are not automatic.

**Observed in:** Universally documented. Hermes lint checks for `updated > 90 days older than related sources`. LLM Wiki v2 adds confidence decay.

**Mitigations:**
- Staleness lint rule with configurable threshold (90 days in Hermes)
- Confidence decay: facts lose weight as time passes without reinforcement (LLM Wiki v2)
- Supersession tracking: new facts explicitly link to facts they replace (LLM Wiki v2)
- Anytype advantage: `updated_at` is a native system property; lint queries are native property predicates, not file timestamp heuristics

### Failure Mode 3: Broken Cross-References

**Description:** Page A links to `[[entity-foo]]`. The entity page is later renamed to `entity-foo-bar` or archived. The link silently becomes an orphan. At scale (100+ pages), broken links proliferate.

**Root cause:** Wikilink syntax uses string matching, not object references. Rename operations don't cascade to incoming links.

**Observed in:** Hermes treats broken wikilinks as the highest-severity lint violation. The obsidian-wiki framework's cross-linker explicitly addresses this. Hermes archive workflow requires manually updating all pages that link to the archived page.

**Mitigations:**
- Lint rule: validate all `[[wikilinks]]` targets exist (Hermes)
- Archive workflow: replace broken wikilinks before archiving (Hermes)
- Obsidian-wiki: automated cross-linker sweeps for unlinked mentions
- **Anytype eliminates this class of bug entirely:** Relations use object IDs, not string titles. Renaming an object does not break any relation pointing to it. There is no "broken link" — the relation target either exists or it doesn't.

### Failure Mode 4: Schema Drift / Inconsistent Tagging

**Description:** Tags proliferate without taxonomy enforcement. `#llm`, `#large-language-model`, `#language-model`, `#transformer` all appear. Property frontmatter fields are inconsistently populated. New pages omit required fields. Over time, structural queries return incomplete results.

**Root cause:** YAML frontmatter is freeform text — nothing enforces the schema. The LLM may invent tags not in the taxonomy, especially across sessions.

**Observed in:** Universally documented. Hermes critical rule: "Every tag must be declared in SCHEMA.md before use." Hermes lint audits all tags against taxonomy.

**Mitigations:**
- Pre-declared tag taxonomy in SCHEMA.md, lint-enforced (Hermes)
- Frontmatter validation in lint pass (all required fields present)
- **Anytype eliminates this class of bug entirely:** Tags are closed-option properties enforced at the data layer. An agent cannot assign a tag not in the taxonomy. Types enforce required properties at schema level.

### Failure Mode 5: Information Quality Degradation Over Time

**Description:** At 500+ pages, agent writes become less careful. Pages synthesize from other wiki pages (not original sources), introducing synthesis errors and compression artifacts. The wiki becomes "telephone tag" for original sources. Human readability degrades as content becomes optimized for agent consumption patterns (dense, decontextualized, structured for search rather than understanding).

**Root cause:** Compounding synthesis — pages cite pages which cite pages. Agent context windows can't hold the full wiki for consistency checks.

**Observed in:** LLM Wiki v2 explicitly identifies this as "knowledge decay." Cognee and Zep research papers note that summarization approaches lose causal chains and reasoning context.

**Mitigations:**
- Source citation required on every fact (Hermes: `sources:` frontmatter field)
- Quality scoring: evaluate structure, source citation, consistency; flag or regenerate below threshold (LLM Wiki v2)
- Always-immutable raw source layer — agents can always re-derive from originals
- Page size limit (~200 lines) prevents bloat (Hermes)
- Anytype advantage: `Source` objects with provenance tracking are first-class objects, not just strings in frontmatter; every Entity/Concept can carry typed `sources` relations pointing to auditable Source objects

### Failure Mode 6: "Wikilink-as-Interface" Coupling

**Description:** Every implementation couples the knowledge graph's navigation primitive to Obsidian's `[[wikilink]]` syntax. The cross-reference mechanism, entity resolution, lint rules, and agent prompts all assume this format. Swapping the storage layer requires rewriting the entire operational model.

**Root cause:** The filesystem + Obsidian toolchain is deeply assumed in Karpathy's pattern.

**Observed in:** Hermes SKILL.md is Obsidian-native. The obsidian-wiki framework is named for this dependency. Migrations are painful.

**Mitigation for our case:** By porting to Anytype's native Relations, we eliminate this coupling. The relation mechanism is the storage layer — not an encoding layer on top of it. This is architecturally cleaner.

### Failure Mode 7: Operational Brittleness at Session Boundaries

**Description:** Every LLM wiki implementation requires session orientation (read SCHEMA → index → log) before any operation. If an agent skips this (e.g., context window pressure, interrupted session), it creates duplicates, misses cross-references, and applies wrong tags. At scale, this happens regularly.

**Root cause:** The orientation state is stored in files that must be actively loaded — it is not ambient. Context windows have limits.

**Observed in:** Hermes documents this as "Critical Session Startup" with explicit warning. Obsidian-wiki's `.manifest.json` delta tracking addresses this for source tracking but not for entity resolution.

**Mitigations:**
- Mandatory session startup procedure (Hermes)
- Delta tracking via manifest (obsidian-wiki)
- Automated hooks that fire on session boundaries (LLM Wiki v2)
- Anytype partial mitigation: Anytype's Collections and Sets provide always-current views of objects by Type, removing the need to read index.md — the "index" is a live query, not a maintained file

---

## Comparative Summary

| Feature | Karpathy (Original) | Hermes (Filesystem) | MemPalace | Zep/Graphiti | Anytype (Proposed) |
|---------|--------------------|--------------------|-----------|--------------|-------------------|
| **Storage** | Markdown files | Markdown files | ChromaDB + SQLite | PostgreSQL + embeddings | Anytype native objects |
| **Cross-refs** | `[[wikilinks]]` (stringly typed) | `[[wikilinks]]` | Tunnel metaphor | Graph edges | Typed Relations (object IDs) |
| **Schema enforcement** | SCHEMA.md (LLM-trust) | SCHEMA.md + lint | Metaphor hierarchy | Node/edge types | Types + closed-option tags |
| **Broken links possible?** | Yes | Yes | No | No | No |
| **Tag taxonomy** | Free-form | Lint-enforced | Not applicable | Not applicable | Data-layer enforced |
| **Staleness detection** | Manual lint | 90-day lint rule | Temporal validity windows | Bi-temporal model | Native `updated_at` queries |
| **Entity dedup** | Manual (index lookup) | Manual (index lookup) | Auto (chromadb similarity) | Automated | Manual + search (Anytype API) |
| **Temporal awareness** | Updated dates | Updated dates | Temporal validity | Full bi-temporal | `updated_at` + `ingested_at` |
| **Human readability** | High | High | Low (raw transcripts) | Medium (graph) | High (native UI) |
| **Multi-device sync** | Obsidian Sync (paid) | Obsidian Sync (paid) | Local only | Cloud/self-hosted | Native (E2E encrypted) |
| **Programmatic schema** | N/A | N/A | N/A | Yes | Yes (API + mcp-plus) |
| **Query by property** | Dataview plugin | Dataview plugin | Metadata filters | Graph traversal | API (`?created_date[gte]=X`) |
| **Community** | 5,000+ gist stars | One reference impl | Small | Large (Zep: 13K stars) | Growing |

---

## Key Takeaways for Anytype Port

### Principles to Carry Forward

**1. Three-layer immutability principle.** Keep raw sources immutable (`Source` objects never mutated after ingestion). Wiki knowledge objects (`Entity`, `Concept`, etc.) are the mutable, agent-maintained layer. This is directly portable.

**2. Mandatory orientation before any session operation.** In the Anytype context, this means: before ingest, the agent must query current Entity/Concept objects (via `wiki.list_entities()`) and check existing Relations. Anytype's live queries are superior to reading index.md — they're always current.

**3. Page threshold policy — carry verbatim.** 2+ source mentions OR central to one source = create. Passing mention = skip. This maps cleanly to Anytype: create an `Entity` object vs. add a string mention in a source object's excerpt field.

**4. Append-only log.** The `WikiLog` type is already in the ticket's design. The operational insight from Hermes: log rotation (at 500+ entries) must be planned. For Anytype, this means archiving WikiLog objects by year, not deleting them.

**5. Lint as a first-class operation.** Lint is not an afterthought — it's how the system maintains health. The Anytype implementation has a structural advantage: several lint checks that require file scanning in Hermes become native property queries (orphans = Entities with zero inbound Relations, stale = `updated_at < max(source.ingested_at) - 90d`).

**6. Cross-link minimum.** Every new Entity/Concept must have ≥2 outbound Relations before being committed. This is directly portable. It prevents information silos and is enforceable by the ingest pipeline before the operation completes.

### What to Adapt

**7. Entity resolution.** Hermes relies on LLM judgment + index lookup. Anytype adds a layer: exact title match via API search, then embedding similarity via existing anytype-rag. This is strictly better — use both. The confidence threshold for auto-upsert vs. propose should be configurable (the ticket's open question has a good proposed answer: auto above threshold, propose below).

**8. Contradiction handling.** The `contradictions` field in Hermes is a frontmatter string list — fragile. In Anytype, `contradictions` becomes a typed Relation → Entity/Concept, which is structurally superior. The update policy (preserve both, flag for review) carries forward as-is.

**9. Tag taxonomy.** Hermes requires lint to enforce taxonomy; Anytype enforces it at the data layer. This means the SCHEMA.md concept maps directly to: create the closed-option Tag property with predefined options. The tag options IS the taxonomy. No lint rule needed for tag violations (the API will reject invalid tags) — though it is worth checking import paths.

**10. Archive workflow.** Hermes' archive manually updates every linking page. Anytype's archive approach: set object status to "archived" (a native Anytype state), which removes it from active Sets/Collections without breaking Relations. Relations to archived objects remain valid and visible. This is architecturally superior — no link-update cascade required.

### What to Avoid

**11. Do not build an index.md equivalent.** Hermes' index.md is a manually maintained file that requires reading before every operation and updating after every ingest. In Anytype, Collections with grouped-by-Type views ARE the index — always current, no maintenance cost. Generating a parallel static index would be regression.

**12. Do not use string-based cross-references.** The entire wikilink machinery exists because filesystem-based wikis have no alternative. Anytype Relations are object references. String-based entity linking is a step backward. Every cross-reference in the ingest pipeline should resolve to an actual Anytype object ID, not a title string.

**13. Avoid verbatim conversation storage (MemPalace approach).** For this use case, we want compiled, synthesized, human-readable knowledge — not conversation transcripts. MemPalace solves a different problem.

**14. Do not underestimate API limitations.** The anytype-mcp-plus investigation revealed critical gaps:
- Body (rich text) updates via PATCH are silently ignored in current API
- FilterExpression in search has a TODO (no-op)
- The API has been confirmed to support `?created_date[gte]=X` property filtering (via the list-objects endpoint), which is sufficient for staleness queries
- Relation neighborhood queries are not natively supported — the lint suite will need to fetch objects and traverse Relations manually, not use a single graph query

**15. Scope the entity dedup problem correctly.** None of the filesystem implementations solved entity dedup well — they all rely on LLM judgment. The Anytype advantage is smaller than it appears: Anytype prevents broken links but does not prevent creating two distinct Entity objects for the same real-world entity. Embedding similarity (via existing anytype-rag) is the mitigation — not the data model.

### Open Question: One Space vs. Multiple Spaces

The ticket proposes one Anytype space per wiki domain. This aligns with:
- MemPalace's "Wings" as top-level organizational units
- Hermes' single `wiki.path` per configuration (the per-project extension was filed as a follow-up issue)
- How Jan reportedly uses Anytype today

**Pressure test:** Zep/Graphiti and Mem0 both use namespacing within a single store rather than separate instances. The single-store approach simplifies cross-domain queries (e.g., "how does Axé DAO strategy relate to Aldeia business?"). However, for Anytype, the space-per-domain approach has a native-UI benefit: each space has its own navigational context and member permissions. Given that the use cases are genuinely domain-isolated (AI Research vs. Axé DAO vs. Aldeia business), the space-per-wiki proposal is sound. Cross-domain synthesis can go through the query pipeline rather than requiring a shared knowledge graph.

---

## Sources

- [Karpathy LLM Wiki Gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) — original pattern description
- [Hermes Agent llm-wiki SKILL.md](https://github.com/NousResearch/hermes-agent/blob/main/skills/research/llm-wiki/SKILL.md) — reference filesystem implementation
- [Hermes Agent PR #5635](https://github.com/NousResearch/hermes-agent/pull/5635) — implementation discussion and design decisions
- [MemPalace GitHub](https://github.com/MemPalace/mempalace) — verbatim conversation memory system
- [ibl.ai: Memory and Skills](https://ibl.ai/blog/memory-and-skills-what-turns-an-agent-loop-into-a-real-ai-agent) — institutional agent memory architecture
- [LLM Wiki v2 Gist (rohitg00)](https://gist.github.com/rohitg00/2067ab416f7bbe447c1977edaaa681e2) — community extension with production failure modes
- [obsidian-wiki Framework (Ar9av)](https://github.com/Ar9av/obsidian-wiki) — delta-driven LLM wiki implementation
- [A-MEM Paper (arxiv 2502.12110)](https://arxiv.org/html/2502.12110v11) — NeurIPS 2025, Zettelkasten-inspired agentic memory
- [Graphiti GitHub](https://github.com/getzep/graphiti) — temporal knowledge graph for agent memory
- [Zep: Stop Using RAG for Agent Memory](https://blog.getzep.com/stop-using-rag-for-agent-memory/) — RAG failure modes for memory use case
- [Best AI Memory Frameworks 2026 (Atlan)](https://atlan.com/know/best-ai-agent-memory-frameworks-2026/) — Mem0 vs Zep vs Letta vs Cognee comparison
- [Cognee Memory Tools Evaluation](https://www.cognee.ai/blog/deep-dives/ai-memory-tools-evaluation) — benchmark results and methodology
- [Survey of AI Agent Memory Frameworks (Graphlit)](https://www.graphlit.com/blog/survey-of-ai-agent-memory-frameworks) — landscape overview
- [anytype-mcp-plus v1.1.0 Community Post](https://community.anytype.io/t/anytype-mcp-plus-v1-1-0-enhanced-mcp-server-with-34-tools-bug-fixes-and-api-research/30466) — Anytype API capabilities and limitations
- [Anytype API Reference](https://developers.anytype.io/docs/reference) — official API documentation
- [Anytype Create Property endpoint](https://developers.anytype.io/docs/reference/2025-05-20/create-property/) — property creation API
- [Anytype List Types endpoint](https://developers.anytype.io/docs/reference/2025-05-20/list-types/) — type management API
- [Anytype Searching and Filtering Objects](https://developers.anytype.io/docs/guides/get-started/searching/) — query capabilities including date filters
- [LLM Wiki: Why Your Best Knowledge Base May Be an Agent-Maintained Wiki](https://akillness.github.io/posts/llm-wiki-persistent-knowledge-base/) — failure mode analysis
- [Top 10 AI Memory Products 2026 (Medium)](https://medium.com/@bumurzaqov2/top-10-ai-memory-products-2026-09d7900b5ab1) — broader market landscape
