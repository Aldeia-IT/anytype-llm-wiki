# Positioning Verification Record

**Date of check:** 2026-05-30
**Checked by:** market-researcher agent (aldeia pipeline)
**Re-verify before:** every public release (next check due at v0.3.0 tag)

---

## Purpose

This file records the web-search evidence used to substantiate (or revise) the marketing
positioning claim in the README, and the basis for the trademark disclaimer in the footer.
It is an internal substantiation record kept in the public repo for transparency.

---

## 1. Positioning Claim — Research Queries and Findings

The draft README intro at the time of this check read:

> "The first open-source LLM wiki that uses a typed knowledge-graph store —
> Anytype's native Objects, Types, and Relations — instead of a filesystem of markdown files."

The following queries were run on 2026-05-30 to test whether any superlative ("first") is
defensible.

| Query | Finding |
|-------|---------|
| `Anytype LLM wiki semantic search RAG` | Generic results about LLM wiki vs RAG patterns; no Anytype-specific LLM wiki product found |
| `Anytype MCP server Model Context Protocol` | **Found:** `anyproto/anytype-mcp` (official, CRUD/search, no semantic/vector search) AND `wethegreenpeople/anytype-mcp` (community, Python, semantic search + RAG via ChromaDB + Ollama, April 2025) |
| `Anytype vector search AI knowledge base` | Both MCP projects surface again; no additional Anytype-native vector/semantic project found |
| `Anytype Claude MCP semantic search RAG vector embeddings GitHub` | `wethegreenpeople/anytype-mcp` confirmed as the main Anytype-specific semantic search MCP project |
| `wethegreenpeople anytype-mcp semantic search GitHub` | Confirmed: Python 100%, ChromaDB, mxbai-embed-large via Ollama, publicly announced April 19 2025 on Anytype Community forum, listed in official Anytype developer docs |
| `Anytype "not affiliated" OR "not endorsed" third party integration disclaimer` | No Anytype-specific disclaimer template found; general nominative fair-use patterns used by community |
| `"Any Association" Anytype trademark intellectual property rights third party` | Confirmed owner: Any Association (Swiss nonprofit). Copyright and IP held by Any Association. |
| `anyproto "Any Association" Switzerland nonprofit Anytype company` | Confirmed: Any Association is a Swiss nonprofit; Berlin GmbH is a subsidiary; GitHub org is `anyproto` |
| `anytype.io brand guidelines trademark press` | No published brand-guidelines or press-kit page found at anytype.io as of 2026-05-30 |

### Analysis

**Semantic search / RAG / MCP angle:** `wethegreenpeople/anytype-mcp` (April 2025) is directly
comparable prior art — it is Anytype-native, Python, MCP-served, uses local Ollama embeddings,
and delivers semantic search over Anytype documents. Any claim that `anytype-llm-wiki` is "the
first" Anytype semantic-search or RAG MCP server is **not defensible**.

**Typed knowledge-graph-store angle:** The distinction anytype-llm-wiki draws — using Anytype's
native typed Objects, Types, and Relations as a structured wiki store rather than a flat markdown
filesystem — does not appear in any competing project found. However, that pipeline
(`wiki-bootstrap`, typed ingest, entity/concept synthesis) is v0.2+ future work; it is not fully
shipped in v0.2.0. Claiming "first" on unshipped pipeline work would be misleading.

**"First open-source LLM wiki" scoped only to the typed-store design:** Potentially true but
difficult to police and requires the typed pipeline to actually ship before the claim can stand
cleanly.

### Conclusion

The superlative "first" is not defensible for any wording that encompasses the semantic-search
/ RAG / MCP surface area, because `wethegreenpeople/anytype-mcp` predates this project and
covers the same core capability. The typed-wiki-pipeline differentiation is real and worth
communicating, but must be framed as a differentiator, not a superlative, until the full
pipeline ships.

**Decision: swap the superlative. `verified = false`.**

### Recommended claim (README intro)

> "An MCP-native semantic search and LLM wiki for your Anytype knowledge base — local-first,
> typed, and built on Anytype's native Objects, Types, and Relations."

This phrasing:
- Uses "an" (indefinite article), not "the first"
- Highlights the genuine differentiators: MCP-native design, local-first stack, and the typed
  wiki pipeline (which remains the product's long-term direction)
- Makes no superlative claim that requires ongoing policing
- Will not need to be updated when competitors emerge

---

## 2. Trademark and Brand — Research and Disclaimer

### Findings

- **Trademark owner:** Any Association, a Swiss nonprofit (GitHub org: `anyproto`).
  Confirmed via Terms of Use, GitHub organization profile, and community discussions.
- **Brand-guidelines page:** No dedicated trademark-usage or brand-guidelines page was found
  at anytype.io as of 2026-05-30. The anytype.io/brand and anytype.io/trademark URLs return 404.
- **Legal site:** `legal.any.coop` exists but returned no parseable content during this check.
- **Usage in community:** Third-party projects (including `wethegreenpeople/anytype-mcp` and
  `anyproto/anytype-mcp`) use the Anytype name in project titles without apparent objection from
  Any Association, consistent with nominative fair use.
- **Anytype's own MCP server** is MIT-licensed; the broader platform is under the Any Source
  Available License 1.0 for some components.

### Approach

Because Anytype publishes no formal third-party trademark-usage policy, the disclaimer follows
established nominative fair-use practice: acknowledge the mark owner, disclaim affiliation or
endorsement, and use the name only to identify the platform this project integrates with.

### Final disclaimer text

> Anytype is a trademark of Any Association. This project is not affiliated with, sponsored by,
> or endorsed by Any Association or the Anytype project. The Anytype name is used solely to
> identify the platform this software integrates with.

---

## 3. Re-verify Checklist (before each public release)

- [ ] Re-run the search queries in Section 1 to check for new Anytype-native LLM wiki or
      typed-store projects.
- [ ] Check anytype.io/brand and legal.any.coop for any newly published trademark or
      brand-usage policy.
- [ ] Confirm Any Association is still the correct trademark owner (check anyproto GitHub org
      and anytype.io footer).
- [ ] If the typed wiki pipeline (`wiki-bootstrap`, `wiki-ingest`, entity/concept synthesis)
      has shipped, consider whether a stronger (but still non-superlative) differentiator claim
      is appropriate.
- [ ] Update this file with the new check date and findings.

---

## Sources

- https://github.com/wethegreenpeople/anytype-mcp — community Anytype semantic search MCP (April 2025)
- https://developers.anytype.io/docs/examples/community/wethegreenpeople-anytype-mcp/ — listed in official Anytype developer docs
- https://community.anytype.io/t/introducing-anytype-mcp/27597 — original announcement (April 19, 2025)
- https://github.com/anyproto/anytype-mcp — official Anytype MCP (CRUD, no semantic search)
- https://github.com/anyproto — Any Association GitHub organization
- https://anytype.io/terms_of_use/ — Anytype Terms of Use (IP ownership by Any Association)
- https://github.com/anyproto/anytype-ts/blob/main/LICENSE.md — Any Association copyright notice
