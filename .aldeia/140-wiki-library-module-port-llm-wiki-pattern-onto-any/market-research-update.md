# Market Research Update: Wiki Library Module — Re-Run for Missed Twitter Sources

**Date:** 2026-04-14
**Researcher:** market-researcher agent (re-run)
**Ticket:** #140
**Previous research:** 2026-04-13 (market-research.md, 526 lines)
**Re-run reason:** Twitter sources returned 402 paywall in first run. Jan provided full tweet text in issue comments on 2026-04-14.

---

## 1. Corrections to Previous Research

### M4 Correction: DhravyaShah/Supermemory Tweet Was Incorrectly Characterized

**What the previous research said:**

> "Based on community references and the research context, Shah's implementation appears to be an early practical port of the LLM Wiki pattern, likely demonstrating rapid iteration on Karpathy's pattern with Claude Code or similar tools. The key insight attributed to his thread in the community: the pattern works immediately without infrastructure investment — AGENTS.md and a wiki directory is sufficient to start."

**This was entirely wrong.** The DhravyaShah tweet is not about the LLM Wiki pattern at all. It is Dhravya Shah (founder of Supermemory) announcing a research result: the ASMR (Agentic Search and Memory Retrieval) technique achieving ~99% on LongMemEval_s. The tweet predates Karpathy's by approximately 11 days. It is about a completely different design space: agent-orchestrated retrieval as a replacement for vector search, not wiki compilation.

**What the previous research got right:** The competitive landscape table for Zep (63.8%) and Mem0 (49%) on LongMemEval was correct — but these scores are the backdrop against which ASMR's ~99% claim must be evaluated (see Section 3).

### M1 Partial Correction: Karpathy Coverage Was Incomplete

The previous research reconstructed Karpathy's tweet from blog posts and community discussion. It captured the three-layer architecture and basic operational policies accurately. However, it missed or understated several important details documented in Section 2 below. The core model was correct; the operational specifics were thin.

---

## 2. New Findings from Karpathy's Tweet

The full tweet (status/2039805659525644595, published April 3, 2026) adds the following details not captured in the previous research:

### Scale Claim: RAG Not Needed at This Scale

Karpathy explicitly states his wiki is "~100 articles and ~400K words" — longer than most PhD dissertations — and that he "thought I had to reach for fancy RAG, but the LLM has been pretty good about auto-maintaining index files and brief summaries of all the documents and it reads all the important related data fairly easily at this ~small scale."

**Implication:** The tweet explicitly frames the index-based navigation as sufficient at the ~100-article scale. This is a claim, not a proof, but it has strong implications for the wiki module's query pipeline design: for a personal-scale wiki (under ~200 articles), an index-read approach may be preferable to embedding retrieval because it avoids retrieval noise. RAG is described as "fancy" and framed as unnecessary overhead at this scale.

**Previous research missed:** The previous research mentioned RAG vs Wiki comparison generically but did not document this explicit scale threshold claim from the primary source.

### Specific Tooling Named

The tweet names specific tools the previous research did not capture:

- **Obsidian Web Clipper** — browser extension for converting web articles to .md files for the `raw/` directory. Not just "Obsidian" generically.
- **Hotkey for local image download** — Karpathy uses a keyboard shortcut to download all related images locally so the LLM can reference them with vision capabilities.
- **Marp format** — markdown-based slide deck format with an Obsidian plugin. Query outputs can be rendered as slideshows, viewed in Obsidian.
- **matplotlib images** — query outputs can be Python-generated charts, also viewable in Obsidian.

**Implication for Anytype port:** The output format diversity (text, slides, charts) is an explicit design goal in the original, not just a sidebar feature. Anytype's native support for rich object types positions it well here; the wiki module should support filing back different output artifact types as distinct object types or at least preserve source type metadata.

### "Filing Outputs Back" as an Explicit Compounding Mechanism

Karpathy: "I end up 'filing' the outputs back into the wiki to enhance it for further queries. So my own explorations and queries always 'add up' in the knowledge base."

This is stated explicitly as a core value-generating mechanism — queries are not ephemeral. Filing results back is what makes the wiki compound. The previous research mentioned "Query" objects being filed but did not flag this as explicitly stated in the tweet as a primary design value.

**Implication:** The `Query` type in the ticket's deliverables is not just a log entry — it is the mechanism by which asking questions improves future answers. The wiki module's file-back policy should be a first-class design concern, not an optional behavior.

### "Vibe Coded Search Engine" — The LLM as a Tool Builder

Karpathy: "I vibe coded a small and naive search engine over the wiki, which I both use directly (in a web ui), but more often I want to hand it off to an LLM via CLI as a tool for larger queries."

Two distinct uses: (1) direct human use via web UI, (2) as an LLM-accessible CLI tool. This is the origin point for community implementations that built MCP-based search tools (lucasastorian/llmwiki provides full MCP tools for search/read/write; ScrapingArt/Karpathy-LLM-Wiki-Stack adds a `qmd` semantic search engine with BM25 + vector + LLM reranking).

**Implication for anytype-rag:** The existing anytype-rag semantic search (bge-m3 + Qdrant) is exactly the "vibe coded search engine" Karpathy describes — a CLI-accessible tool that can be handed off to an LLM. The wiki module naturally uses it as this tool. This is architecturally clean.

### Future Direction: Synthetic Data + Finetuning

Karpathy: "As the repo grows, the natural desire is to also think about synthetic data generation + finetuning to have your LLM 'know' the data in its weights instead of just context windows."

This is a future direction, not a current feature — but it names a clear product evolution path. A mature wiki becomes a finetuning dataset. This is novel and was not captured in the previous research.

**Implication:** The Anytype wiki module should preserve provenance and structure in a way that could eventually support synthetic data generation (e.g., question-answer pairs derived from Entity/Concept objects). Not a deliverable for this ticket, but worth noting in the spec as a non-goal with a forward pointer.

### Product Vision: "Incredible New Product"

Karpathy's TLDR ends: "I think there is room here for an incredible new product instead of a hacky collection of scripts."

Community response confirmed this framing. The tweet reached 16 million views. Entrepreneur Vamshi Reddy replied: "Every business has a raw/ directory. Nobody's ever compiled it. That's the product." Karpathy agreed. This is a market-positioning signal: the pattern is validated, the tooling is immature, and there is explicit founder-level endorsement of productizing it.

**Implication:** The anytype-rag wiki module is entering a market that Karpathy himself described as pre-product. Seven community implementations appeared within a week of the tweet (nashsu/llm_wiki, claude-obsidian, coleam00/claude-memory-compiler, sdyckjq-lab/llm-wiki-skill, llm-wiki-compiler, Ar9av/obsidian-wiki, Astro-Han/karpathy-llm-wiki). The ecosystem is moving fast. The Anytype-native angle remains differentiated because all community implementations use filesystem + Obsidian.

---

## 3. ASMR Analysis: Supermemory's Agentic Retrieval Technique

### What ASMR Is

ASMR (Agentic Search and Memory Retrieval) is an experimental multi-agent orchestrated pipeline published by Supermemory (DhravyaShah) in March 2026. It is a direct challenge to the dominance of vector search for agent memory. The core claim: replacing vector math with active LLM reasoning agents produces dramatically better results on temporal, multi-session memory tasks.

**This is not a wiki compiler.** ASMR addresses retrieval from conversation history, not document-to-knowledge-graph compilation. It is in a different problem space from Karpathy's wiki pattern, but it is directly relevant to the wiki module's query pipeline design.

### Architecture

**Phase 1 — Parallel Ingestion (Observer Agents)**

Instead of chunking and embedding conversation sessions, ASMR deploys 3 parallel reader agents (Gemini 2.0 Flash) that read raw sessions concurrently (Agent 1 takes sessions 1, 3, 5; Agent 2 takes 2, 4, 6; etc.). Each agent extracts structured findings across six knowledge vectors:
1. Personal Information
2. Preferences
3. Events
4. Temporal Data
5. Updates
6. Assistant Info

Findings are stored natively (structured text, not embeddings) and mapped back to source sessions for provenance.

**Phase 2 — Active Agentic Retrieval (Search Agents)**

At query time, instead of a vector database lookup, 3 parallel search agents are deployed with specialized roles:
- Agent 1: Direct facts and explicit statements
- Agent 2: Related context, social cues, implications
- Agent 3: Temporal timelines and relationship maps

The orchestrator compiles findings from all three, pulling verbatim session excerpts for detail verification.

**Phase 3 — Agent-Orchestrated Answering Ensembles**

Two approaches were tested:

*Run 1: 8-Variant Ensemble (98.60% accuracy)*
Retrieved context is routed through 8 specialized prompt variants running in parallel (e.g., Precise Counter, Time Specialist, Context Deep Dive). If any of the 8 reasoning paths arrives at the ground truth, the question is marked correct. This is a best-of-N methodology.

*Run 2: 12-Variant Decision Forest (97.20% accuracy)*
12 specialized agents (GPT-4o-mini) independently answer, then an Aggregator LLM synthesizes via majority voting and conflict resolution. This produces a single authoritative answer.

### LongMemEval Results in Context

The ~99% claim must be understood against the benchmark landscape:

| System | LongMemEval Score | Methodology | Notes |
|--------|------------------|-------------|-------|
| ASMR Run 1 (Supermemory) | ~98.60% | 8-variant best-of-N | Experimental, not production |
| ASMR Run 2 (Supermemory) | ~97.20% | 12-variant majority vote | Experimental, not production |
| OMEGA | 95.4% | Single-answer, GPT-4.1 | Independent open-source |
| Mastra (Observational Memory) | ~93-95% | Gemini 3 Pro | QA accuracy |
| MemPalace | 96.6% | Retrieval recall (different metric) | Not QA accuracy |
| Supermemory (production) | ~81-85% | Standard | Production engine |
| Zep/Graphiti | 63.8-71.2% | GPT-4o | Depends on version |
| Mem0 | 49.0% | GPT-4o | Flat vector approach |

**Critical methodology caveat:** The 8-variant ensemble does not produce one answer per question — it produces 8 answers and marks the question correct if any one of them is right. This is best-of-8, not real-world performance. Critics (notably aihola.com) flagged this as a "generous scoring methodology." The 12-variant majority-vote run at 97.2% is more representative of real-world use.

**The ASMR approach also does not use vector databases or embeddings at all** — no Qdrant, no bge-m3. Storage is in-memory structured text. This makes the system portable (even embeddable in robots, per the tweet) but raises questions about scalability to very large knowledge bases.

### Key Engineering Insights from ASMR

Three findings from the Supermemory paper/blog are directly relevant to the wiki module:

**1. Agentic Retrieval Beats Vector Search for Temporal Data**

"Ditching vector embeddings for active search agents was the single biggest unlock. Agents actively searching for context eliminated the semantic similarity trap that causes traditional RAG to fail on temporal changes and updates."

This is a direct critique of the anytype-rag current approach (bge-m3 + Qdrant). Vector similarity cannot reliably distinguish an old fact from its newer correction — semantic similarity is high between "X has 4GB RAM" and "X now has 8GB RAM," so the vector store may return both or the wrong one. ASMR's agent-based search does temporal reasoning explicitly.

**2. Parallel Processing Is Critical**

Splitting ingestion and retrieval across multiple specialized agents "dramatically improved both the speed and granularity of fact extraction." Parallelism serves both throughput and quality: each agent can have a specialized focus without context interference.

**3. Specialization Beats Generalization**

Routing context through dedicated specialist agents "vastly outperforms any single master prompt." The Counter prompt, the Detail Extractor, the Timeline Reconstructor — each is better than one prompt trying to do all three.

### Open-Source Status: Not Confirmed Released

The tweet promised "beginning of April" open-source release. As of April 14, 2026:
- The supermemoryai GitHub organization has 23 repos; no repo matching "ASMR" or "experimental agent memory" is listed.
- The production supermemory repo (21.8K stars) is open-source frontend/SDK; core engine is a proprietary backend at api.supermemory.ai.
- The research page at supermemory.ai/research/ references open-sourced ingestion pipeline and evaluation scripts but does not explicitly confirm the ASMR experimental code was released.
- The aihola.com article notes "The April open-source release will enable genuine scrutiny beyond benchmark metrics" — implying release is expected but unconfirmed at time of writing.

**Conclusion:** The ASMR open-source code has not been confirmed released as of April 14, 2026. The promise was "beginning of April" — it may have been released after the search snapshot. Check https://github.com/supermemoryai for any new repo named "asmr" or "experimental-memory."

### Community Reception

Reception was mixed excitement and skepticism:
- The ~99% claim was widely covered (VentureBeat, various AI news outlets)
- Critics noted compute budget incomparability: ASMR fires ~14+ frontier-model API calls per query (3 ingestion + 3 search + 8 answering), vs. single-call vector systems
- The "no vector DB" framing was called out: ASMR swaps embedding cost for LLM API cost. Different cost curve, not free.
- The 8-variant best-of-N scoring was specifically criticized as not reflecting real user experience.

---

## 4. Updated Competitive Landscape

### Corrections to Previous Table

The previous research's competitive table had one row labeled "From DhravyaShah's Tweet" that was a fictional characterization (LLM Wiki port). This is removed entirely. ASMR is added as a distinct row.

MemPalace's 96.6% score was listed in the previous research as a straightforward benchmark win over Zep and Mem0. Updated context: the 96.6% measures retrieval recall (R@5), not QA accuracy — a different metric than what Zep and Mem0 report. Direct comparison is misleading. This nuance matters for the wiki module's design: MemPalace optimizes for verbatim retrieval, not synthesized answer quality.

### Updated Competitive Table

| System | Approach | LongMemEval | Storage | Best For |
|--------|----------|-------------|---------|----------|
| **ASMR (Supermemory experimental)** | Multi-agent orchestrated retrieval, no vector DB | ~98.6% (best-of-8) / ~97.2% (majority vote) | In-memory structured text | Temporal, multi-session conversation memory |
| **OMEGA** | Compiled wiki + index navigation | 95.4% | Markdown + LanceDB | Single-domain research knowledge base |
| **MemPalace** | Verbatim conversation store | 96.6% (retrieval recall, different metric) | ChromaDB + SQLite | Complete session recall, no summarization loss |
| **Mastra (Observational Memory)** | Observational memory extraction | ~93-95% | Graph-based | Production conversation agents |
| **Supermemory (production)** | Hybrid vector+graph memory | ~81-85% | Proprietary backend | Drop-in conversation personalization |
| **Zep/Graphiti** | Temporal knowledge graph | 63.8-71.2% | PostgreSQL + embeddings | Facts that change over time |
| **Mem0** | Hybrid vector+graph+KV | 49.0% | Managed cloud | Drop-in personalization API |
| **LLM Wiki (Karpathy)** | Compiled markdown, index navigation | Not benchmarked | Filesystem | Human-browsable personal knowledge base |
| **Anytype wiki module (proposed)** | Compiled typed objects, typed relations | Not yet benchmarked | Anytype native | Human-browsable + agent-queryable, typed schema enforcement |

**Key additions:**
- ASMR now appears with correct characterization (not LLM Wiki)
- OMEGA added — this is the closest benchmark peer to the Anytype wiki approach (compiled wiki + index-based navigation, no embeddings for navigation)
- Mastra Observational Memory added — a newer strong performer
- Methodology notes on MemPalace score

### The Agentic vs Vector Retrieval Design Tension

The ASMR result makes explicit a design question that was implicit in the previous research: **for the wiki module's query pipeline, should retrieval be purely vector-based (anytype-rag status quo), or should LLM-based search agents be used alongside or instead of vector search?**

Key data points:
- At wiki scale (~100-200 articles / ~400K words), Karpathy found index navigation sufficient without any vector search
- ASMR shows that for temporal/multi-session data, agentic LLM-based retrieval outperforms vector search significantly
- Vector search (bge-m3 + Qdrant) excels at semantic similarity matching across large corpora but struggles with temporal reasoning and fact staleness
- Agentic retrieval requires significantly more LLM calls per query (cost, latency trade-off)

**For the wiki module specifically:** The wiki is a compiled, structured knowledge base (not raw conversation history). Entities have explicit typed Relations, timestamps, and source provenance. This structured nature means the staleness/temporal problem is partially solved at the data model level (Anytype's `updated_at`, `ingested_at`, typed Relations). Whether full ASMR-style multi-agent retrieval is warranted, or whether a hybrid (vector search for candidate selection + single LLM for synthesis) is sufficient, is an open design question that the spec should address.

---

## 5. Design Implications for Wiki Module Query Pipeline

### Implication 1: Index-First Navigation for Small Wikis

Karpathy's explicit scale claim (~100 articles, ~400K words, no RAG needed) suggests a tiered query strategy:
- **Tier 1 (small wiki, <200 articles):** Index-read approach — query the Anytype Collections/Sets by Type, read relevant object descriptions and Relations, synthesize. No vector search needed.
- **Tier 2 (medium wiki, 200-500 articles):** Hybrid — vector search (bge-m3 + Qdrant) to identify candidate objects, then read full objects + relation neighborhoods.
- **Tier 3 (large wiki, 500+ articles):** Full ASMR-style agentic retrieval may be warranted, but this is beyond initial scope.

The query pipeline spec should explicitly acknowledge these tiers and define the transition thresholds.

### Implication 2: Agentic Retrieval Is Worth a Future Spike

ASMR's core insight — that active LLM-based search agents outperform vector similarity for temporal data — is directly applicable to the wiki module. A wiki of AI research will have stale claims, updates to existing entities, and temporal sequences. Bge-m3 vector search will struggle to distinguish "as of 2024" from "as of 2026" claims without explicit temporal filtering.

The recommended approach for the initial spec: use vector search as the primary retrieval mechanism (already built), but design the query pipeline to be pluggable — so an agentic retrieval layer can be added in a later iteration. The ASMR architecture's three-phase structure (ingestion agents → search agents → answering ensemble) is a roadmap for iteration.

### Implication 3: File-Back Policy Is a Primary Design Concern

Karpathy explicitly names filing query outputs back into the wiki as the mechanism by which "explorations and queries always add up." The `Query` type in the ticket's deliverables must be treated as a first-class compounding mechanism, not a log entry. The spec should define:
- What triggers a file-back (size threshold for synthesis? Manual vs. automatic?)
- How `Query` objects relate back to `Entity`/`Concept` objects via `drew_from` Relations
- How a filed query improves future queries (does it add new tags? Create new Entity objects? Strengthen Relations?)

### Implication 4: Supermemory ASMR Is Not a Direct Competitor

ASMR addresses conversation-history retrieval. The anytype-rag wiki module addresses knowledge graph construction and querying. These are different problems. ASMR is prior art for retrieval technique design, not a competing product for the wiki module's use case.

However, **the ASMR open-source code (when released) should be studied for its ingestion agent architecture** — specifically the six-vector knowledge extraction framework (Personal Info, Preferences, Events, Temporal Data, Updates, Assistant Info) as an alternative to the simple entity/concept/comparison taxonomy. The wiki module's ingest pipeline extracts similar categories; ASMR's extraction categories are more operationally specific and could inform the ingest LLM prompt design.

### Implication 5: The "No Vector DB" Result Is Not a Recommendation to Remove Qdrant

ASMR works without vector embeddings by replacing them with expensive LLM API calls. At personal wiki scale (100-200 articles), Karpathy's index approach also avoids vector search. Neither of these implies that Qdrant should be removed from anytype-rag. The existing embedding infrastructure (bge-m3 + Qdrant) remains valuable for:
- Semantic dedup during ingest (detecting near-duplicate Entity objects)
- Candidate selection at medium wiki scale
- Cross-wiki search (searching across multiple Anytype spaces)

The recommendation is to keep Qdrant, add the index-first navigation strategy as the default for query, and treat vector search as a fallback/augmentation for medium-to-large wikis.

---

## Sources

### Primary Sources (Tweet Full Text)
- Karpathy tweet (full text provided by Jan): https://x.com/karpathy/status/2039805659525644595
- DhravyaShah/Supermemory tweet (full text provided by Jan): https://x.com/DhravyaShah/status/2035517012647272689

### Supermemory / ASMR
- [Supermemory ASMR Blog Post](https://blog.supermemory.ai/we-broke-the-frontier-in-agent-memory-introducing-99-sota-memory-system/) — primary technical description
- [Supermemory Research Page](https://supermemory.ai/research/) — benchmarks and methodology
- [Supermemory Hits 99% on LongMemEval With Agent Swarm (aihola.com)](https://aihola.com/article/supermemory-99-longmemeval-agentic-memory) — independent coverage with critical analysis
- [supermemoryai GitHub Organization](https://github.com/supermemoryai) — repos (ASMR code not confirmed released as of 2026-04-14)

### Karpathy LLM Wiki Ecosystem
- [Karpathy LLM Wiki Gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) — primary pattern
- [Wave of Open-Source Tools (SimpleNews.ai)](https://www.simplenews.ai/news/karpathys-llm-wiki-pattern-sparks-wave-of-open-source-knowledge-base-tools-3hel) — ecosystem overview
- [VentureBeat Coverage](https://venturebeat.com/data/karpathy-shares-llm-knowledge-base-architecture-that-bypasses-rag-with-an) — mainstream coverage with scale details
- [nashsu/llm_wiki](https://github.com/nashsu/llm_wiki) — community implementation (680 stars)
- [lucasastorian/llmwiki](https://github.com/lucasastorian/llmwiki) — MCP-based implementation
- [ScrapingArt/Karpathy-LLM-Wiki-Stack](https://github.com/ScrapingArt/Karpathy-LLM-Wiki-Stack) — comprehensive reference stack with qmd search
- [skyllwt/OmegaWiki](https://github.com/skyllwt/OmegaWiki) — full research lifecycle implementation (23 Claude Code skills)
- [tjiahen/awesome-llm-wiki](https://github.com/tjiahen/awesome-llm-wiki) — curated list of implementations
- [Product vision discussion (reliabilitywhisperer.substack.com)](https://reliabilitywhisperer.substack.com/p/the-andrej-karpathy-llm-wiki-idea) — "hacky collection of scripts" / "incredible new product" framing
- [Karpathy's LLM Wiki in Production (aaronfulkerson.com)](https://aaronfulkerson.com/2026/04/12/karpathys-pattern-for-an-llm-wiki-in-production/) — practical deployment notes

### Competitive Landscape / Benchmarks
- [LongMemEval Leaderboard (OMEGA)](https://omegamax.co/benchmarks) — current leaderboard with methodology notes
- [Mastra Observational Memory](https://mastra.ai/research/observational-memory) — 93-95% on LongMemEval
- [Agentic Memory Analysis (lhl/agentic-memory)](https://github.com/lhl/agentic-memory) — independent research collection
- [Hindsight Benchmark Manifesto](https://hindsight.vectorize.io/blog/2026/03/23/agent-memory-benchmark) — methodology critique
- [Agentic vs Vector Retrieval Tradeoffs (MarkTechPost)](https://www.marktechpost.com/2025/11/10/comparing-memory-systems-for-llm-agents-vector-graph-and-event-logs/) — design analysis
