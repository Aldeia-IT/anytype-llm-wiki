# Research Plan: Wiki Library Module — Port LLM Wiki Pattern onto Anytype

**Date:** 2026-04-13
**Lead:** research-lead
**Ticket:** #140

## Situation

Jan wants to extend `anytype-rag` (currently a semantic search MCP server for Anytype) into a full Wiki / Knowledge Library module. The model is Karpathy's "LLM Wiki" pattern — a persistent, compounding knowledge base maintained by an agent — ported onto Anytype's native typed-object model (Types, Relations, closed-option tags) instead of a filesystem (Obsidian/markdown).

The ticket already has a detailed design proposal with type schemas, pipeline definitions, and open questions. Research needs to validate feasibility, understand the Anytype API surface, study prior art implementations, and identify architectural risks before spec writing begins.

Jan has also pointed to additional resources for research:
- ibl.ai blog on agent memory/skills
- Karpathy's recent tweets on the topic
- DhravyaShah's implementation approach
- MemPalace project (GitHub)

## Research Domains
- [x] Technical: Anytype API capabilities (type creation, relation management, property queries), anytype-rag codebase architecture, MCP tool extension patterns
- [x] Market/Prior Art: Karpathy LLM Wiki, Hermes agent llm-wiki skill, MemPalace, agent memory architectures, existing implementations
- [ ] Academic: Not needed — the prior art domain covers the relevant literature
- [ ] Legal: Not needed — this is internal tooling, no PII/compliance concerns

## Research Questions

### Technical (T)
1. What is the current anytype-rag codebase architecture? What MCP tools does it expose, how does it interact with Anytype's API, and what is its embedding/indexing pipeline?
2. Does Anytype's API support programmatic Type and Relation creation? Or must types be created manually in the UI and then referenced by ID? What are the API endpoints for CRUD on objects, types, relations, and tags?
3. How does Anytype handle bidirectional relations? Can they be created/queried programmatically? What is the data model for Relations (type constraints, cardinality)?
4. What are the constraints on Anytype's closed-option tag properties? Can tag taxonomies be created/managed via API?
5. How would the ingest pipeline integrate with the existing semantic search (Qdrant + bge-m3)? What hooks exist for re-embedding on object update?

### Market / Prior Art (M)
1. What is the Karpathy LLM Wiki pattern in detail? What are its core design principles, data model, and operational policies (from the original gist and recent tweets)?
2. How did the Hermes agent implement the llm-wiki skill? What worked, what were the limitations, what decisions did they make about page thresholds, cross-linking, entity resolution?
3. What is MemPalace and how does it approach persistent agent knowledge? How does it compare to the LLM Wiki pattern?
4. What are the key insights from ibl.ai's analysis of agent memory/skills? What patterns emerge from DhravyaShah's implementation?
5. What are the common failure modes of agent-maintained knowledge bases? (Entity duplication, stale content, broken cross-references, schema drift)

## Agent Dispatch Plan
| Agent | Questions | Parallel? | Notes |
|-------|-----------|-----------|-------|
| technical-researcher | T1-T5 | Yes | Investigate anytype-rag repo (Aldeia-IT/anytype-rag on GitHub), Anytype API docs, MCP extension patterns |
| market-researcher | M1-M5 | Yes | Web-heavy: fetch Karpathy gist, Hermes PR/SKILL.md, MemPalace repo, ibl.ai blog, tweets |

## Expected Outputs
- `.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/technical-research.md`
- `.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/market-research.md`
