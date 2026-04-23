# Product Review: Wiki Library Module (Round 1)

**Reviewed:** 2026-04-14
**Spec Version:** 0c3d872 (HEAD of spec/wiki-library-module-port-llm-wiki-pattern-onto-any)
**Review method:** Multi-angle team review (market-fit, UX/needs, business-viability, tech-feasibility)

## Executive Summary

This is a well-constructed product spec that tells a coherent story from problem statement through solution design. The problem is grounded in specific user scenarios, the market context is thorough and honest, the competitive positioning is defensible, and the technical design accounts for known API risks with dual-path strategies. The spec faithfully follows the product brief's direction and scope boundaries.

The spec has no fundamental product gaps that would lead to building the wrong thing. It does have several areas where requirements are under-specified or assumptions are untested, and two items that must be resolved before implementation begins (the PATCH body behavior and the FilterExpression behavior are correctly identified as blocking open questions, but the spec does not define what "verification" means concretely enough for the implementation team to act on).

**Verdict:** APPROVED WITH CONDITIONS

---

## Findings

### BLOCKING

- **No findings at BLOCKING severity.**

  The spec's two genuinely blocking risks (PATCH body update behavior, FilterExpression search) are already correctly identified as blocking open questions in the spec itself, with dual-path designs for both. The spec does not pretend these are resolved. This is the right approach — the spec can proceed to tech handoff with the understanding that Phase 2 and Phase 3 each have a gate. However, see SHOULD-FIX #1 below about making the verification protocol concrete.

### SHOULD-FIX

- **SF-1: Verification protocol for PATCH body and FilterExpression is not actionable**
  - Section: Open Questions #1 and #2
  - Issue: The spec says the implementation team "must verify actual behavior against the live Anytype API" and "must test the PATCH body behavior against a live API" but does not define what a successful test looks like. What HTTP request should be made? What response constitutes "PATCH works" vs. "PATCH is silently ignored"? Without a concrete test protocol, the implementation team will have to design the experiment themselves, introducing ambiguity.
  - Why it matters: This is the highest-risk technical question in the entire module. A vague "verify before you start" instruction risks the implementation team either (a) not testing thoroughly enough or (b) spending excessive time designing the test. The spec should include a concrete test script or at minimum describe the exact request/response pair that distinguishes the two paths.
  - Cross-reference: Tech feasibility reviewer notes the technical-research.md documents the exact PATCH endpoint and body format — the spec should leverage this to define the test.

- **SF-2: The "first Anytype-native LLM wiki" claim needs qualification**
  - Section: Market Analysis > Positioning
  - Issue: The positioning statement claims this is "the first Anytype-native LLM wiki." This is likely true as of April 2026, but the spec provides no evidence of a search for prior art within the Anytype ecosystem specifically. The market research covers Obsidian-based implementations and general agent memory systems, but does not document whether anyone has attempted an Anytype-based wiki (e.g., via the official anytype-mcp server or community projects). The anytype-mcp repo exists and provides full CRUD — someone could have built a wiki layer on top.
  - Why it matters: Leading with a "first" claim in the README positioning that turns out to be false would undermine the module's credibility in exactly the community it targets. The claim is probably correct, but it is unverified.
  - Cross-reference: Market-fit and business-viability reviewers both flagged this. The market-research-update.md covers the Karpathy ecosystem thoroughly but the Anytype community ecosystem search is absent.

- **SF-3: Entity resolution thresholds lack empirical grounding**
  - Section: Ingest Pipeline, Entity Resolution
  - Issue: The auto-upsert thresholds (0.92 exact-title, 0.85 embedding similarity) are stated as defaults without any empirical basis. How were these numbers chosen? The research synthesis recommends a "configurable confidence threshold (e.g., 0.92 exact-title match or 0.85 embedding similarity)" — the spec adopted the examples as defaults. There is no data from testing bge-m3 similarity scores on actual entity pairs to validate that 0.85 is the right cutoff between "same entity" and "different entity."
  - Why it matters: If the default threshold is too high, legitimate matches will be surfaced as "proposed merges" that the user must review manually, making ingest noisy. If too low, distinct entities will be auto-merged, corrupting the knowledge graph. The spec correctly makes these configurable, which mitigates the risk — but the defaults should be acknowledged as provisional rather than presented as confident choices.

- **SF-4: Orphan detection has a time-based blind spot**
  - Section: Lint Suite, Lint Checks table
  - Issue: The orphan check filters by `wiki_ingested_at < now - 7 days`, meaning newly created objects with zero relations are excluded from orphan reporting for a full week. But the most common orphan creation scenario is a partial ingest failure — entities created but relations not wired due to an API error mid-pipeline. These orphans should be flagged immediately, not after 7 days. The 7-day grace period makes sense for manually-created objects (giving the user time to wire relations), but not for pipeline-created objects.
  - Why it matters: The spec explicitly handles partial ingest failures (line 123: "Ingest partial failures must report what completed and what failed") but the lint suite cannot catch the resulting orphans for a week. This is a detection gap for the most important failure mode.
  - Cross-reference: UX/needs and tech feasibility reviewers both identified this. The UX reviewer notes the ingest pipeline's WikiLog records partial failures, so the lint suite could use WikiLog entries to identify pipeline-orphans vs. manual-creation-orphans.

- **SF-5: Quick-start "under 15 minutes" claim assumes pre-existing dependencies**
  - Section: User Experience, Developer Experience, Success Criteria
  - Issue: The 15-minute quick-start assumes the user already has: (1) Anytype desktop installed and running, (2) Qdrant running, (3) Ollama running with bge-m3 pulled, (4) Python environment ready. The spec says "No new infrastructure dependencies beyond what anytype-rag already requires" — but for a community user who has never used anytype-rag, setting up Qdrant + Ollama + bge-m3 is itself a 15-30 minute task. The quick-start clock should start from `pip install anytype-rag`, not from dependency installation.
  - Why it matters: The 15-minute claim is the community hook identified in the product brief. If a new user hits the README, tries to follow the quick-start, and spends 45 minutes on dependency setup before even reaching bootstrap, the first impression is negative. The spec should either (a) redefine the 15-minute scope explicitly as "assuming dependencies are met" or (b) include dependency setup time in the estimate.
  - Cross-reference: UX/needs and business-viability reviewers both flagged this.

- **SF-6: Write token permissions are an unresolved open question that could break the quick-start**
  - Section: Open Questions #6, Security Considerations
  - Issue: Open Question #6 asks whether the existing read-scoped bearer token covers write operations or whether a new token is needed. The Security Considerations section notes "The wiki module requires write access. This means the bootstrap process must use a token with write permissions." These two sections contradict: one says it is unknown, the other assumes it is a different token. If a new token is required, the quick-start must include a token generation step, which adds complexity and time.
  - Why it matters: Token auth is the first thing that will fail when a user tries `wiki_bootstrap`. If the existing token works for writes, great. If not, the user hits an auth error on their first command — the worst possible first experience.

### SUGGESTIONS

- **SG-1: Add a "Prerequisites" section to the README structure.**
  The README structure (lines 467-474) lists 7 sections but none is explicitly "Prerequisites" or "Requirements." Adding one would set expectations before the quick-start and prevent the 15-minute disappointment described in SF-5.

- **SG-2: Consider a `wiki.status(space_id)` tool for quick health checks.**
  The four tools cover the full lifecycle, but there is no lightweight "is my wiki healthy?" check. `wiki.lint` is comprehensive but potentially slow (up to 60 seconds for 500 objects). A fast status command returning object counts, last ingest time, and any critical lint findings would be useful for daily operations.

- **SG-3: The tag taxonomy is Jan-specific and may not serve community users.**
  The default domain tags (`wiki_ai-research`, `wiki_infrastructure`, `wiki_business`, `wiki_engineering`, `wiki_governance`, `wiki_science`, `wiki_other`) reflect Jan's domains. A community user building a wiki about, say, cooking or law would find these irrelevant. Consider making the initial tag taxonomy configurable at bootstrap time, or documenting how to customize it post-bootstrap.

- **SG-4: The Comparison type may be premature for v1.**
  Of the six types, Comparison is the least grounded in the research. Hermes does not have a Comparison type. Karpathy does not mention one. The spec does not describe when the ingest pipeline would create a Comparison object (it only mentions entities and concepts in the extraction step). If ingest never creates Comparisons automatically, they are manual-only objects — which means they will likely remain empty for most users. Consider deferring Comparison to a later phase or explicitly documenting that it is a manual-creation type.

- **SG-5: The spec does not address content fetching for non-trivial URL types.**
  `wiki.ingest(source="https://arxiv.org/abs/2502.12110")` is listed as a test case. ArXiv pages serve HTML with links to PDFs — extracting useful text from an ArXiv URL requires either (a) downloading and parsing the PDF or (b) fetching the abstract-only HTML page. The spec says "Fetch source content (URL via httpx)" but does not specify what happens when the URL serves something other than clean text/markdown. PDFs, paywalled articles, JavaScript-rendered pages — these are all common source types that httpx alone cannot handle.

- **SG-6: Consider documenting the expected API call budget per operation.**
  The spec estimates "20-60 API calls" for a typical ingest. This is useful. Extending this to query (how many calls for index-navigation vs. vector-augmented mode?) and lint (how many calls for a 200-object wiki?) would help the implementation team design rate-limiting and caching strategies.

---

## Conditions (APPROVED WITH CONDITIONS)

1. **SF-1 must be addressed before tech handoff:** Add a concrete verification protocol for the PATCH body and FilterExpression tests — at minimum, describe the exact HTTP request and expected response for each outcome. This can be a short appendix to the spec.

2. **SF-2 should be verified before the README ships:** Search the Anytype community forum, the anytype-mcp repo issues, and GitHub for any prior Anytype-based LLM wiki attempt. If none is found, the "first" claim stands. If one is found, adjust the positioning. This does not block spec handoff but must be done before the README is published.

3. **SF-6 should be resolved early in Phase 1:** The write token question should be answered as the very first step of Phase 1 implementation, before any bootstrap code is written. If write access requires a different token, the quick-start documentation must account for it.

---

## What's Done Well

- **Problem statement is concrete and grounded.** Three specific user scenarios, not abstract handwaving. The "40+ AI research papers" example makes the pain real.
- **Dual-path design for PATCH body is excellent engineering.** Rather than blocking on the API question, the spec designs for both outcomes and defers the choice to implementation time. This is exactly the right level of pragmatism.
- **Market analysis is honest about competitors.** The ASMR analysis correctly separates it from the wiki pattern (different problem space), the OMEGA comparison is fair, and the Mem0/Zep positioning does not overstate Anytype's advantages.
- **The type schema design is thorough.** Six types with well-chosen properties, `wiki_` prefix convention to avoid collisions, and clear property-level specifications. This is ready for implementation.
- **Phased delivery is well-structured.** Phase 1 (bootstrap) as a standalone first PR is the right call — it provides value immediately and unblocks content collection.
- **Success criteria are measurable.** "Under 30 seconds," "zero asymmetric Relations," "under 60 seconds for 500 objects" — these are testable, not vague.
- **Error categorization (API/data/config) is a strong UX decision.** Distinguishing error types in MCP tool responses helps users self-diagnose.
- **File-back policy is treated as a first-class design concern,** per the product brief's explicit instruction. The 3+ sources AND 100+ words threshold is reasonable and configurable.
- **The spec follows the product brief faithfully.** Scope boundaries match, persona mapping is preserved, and no significant scope drift is detected. The brief's gaps and risks section is addressed point by point.

---

## Recommended Changes Summary

1. Add a concrete PATCH body verification protocol (test script or exact request/response description) to Open Questions #1.
2. Qualify the "first Anytype-native LLM wiki" claim or verify it with an Anytype ecosystem search.
3. Acknowledge entity resolution thresholds (0.92/0.85) as provisional defaults, not empirically validated.
4. Add pipeline-orphan detection (from WikiLog partial failures) to the lint suite, separate from the 7-day grace period.
5. Clarify quick-start scope: does "15 minutes" include or exclude dependency setup?
6. Resolve the write token contradiction between Open Questions #6 and Security Considerations.
