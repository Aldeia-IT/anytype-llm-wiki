# Product Review: Wiki Library Module (Round 2)

**Reviewed:** 2026-04-14
**Spec Version:** 60323cf (HEAD of spec/wiki-library-module-port-llm-wiki-pattern-onto-any)
**Review method:** Two-angle re-review (technical verification, product coherence) focused on verifying Round 1 fixes

## Executive Summary

Round 1 identified 0 BLOCKING, 6 SHOULD-FIX, and 6 SUGGESTION findings. The spec has been revised to address all 12. This Round 2 re-review verifies those fixes and checks for regressions introduced by the revisions.

All 6 SHOULD-FIX items have been adequately addressed. The fixes are substantive, not cosmetic -- Appendix A adds concrete curl-based verification protocols, pipeline orphan detection is now a distinct lint check with immediate flagging, the "first" claim is properly qualified, thresholds are labeled provisional, the quick-start scope is explicit, and the write token contradiction is resolved. The 6 SUGGESTION items (Prerequisites section, wiki.status deferral, configurable tags, Comparison clarification, supported source types, API call budget) are also addressed appropriately -- some incorporated directly, others explicitly deferred with rationale.

No new BLOCKING or SHOULD-FIX issues were introduced by the fixes. The spec remains coherent after the revisions. One minor suggestion is noted below.

**Verdict:** APPROVED

---

## Round 1 Fix Verification

### SHOULD-FIX Items

**SF-1: Verification protocol for PATCH body and FilterExpression -- RESOLVED**

The spec now includes Appendix A (lines 643-797) with copy-pasteable curl commands for both the PATCH body test (A1) and the FilterExpression test (A2). Each protocol includes: exact HTTP requests with headers, a step-by-step procedure (read baseline, write with marker, read again), and a decision matrix mapping observed outcomes to implementation paths. The PATCH test includes a marker string with timestamp for unambiguous verification, and the FilterExpression test uses three steps (baseline count, filtered count, zero-result count) to distinguish between "works," "no-op," "partial implementation," and "inconsistent" outcomes. Open Questions #1 and #2 now cross-reference Appendix A explicitly. This is concrete and actionable -- the implementation team can execute these tests without designing the experiment.

**SF-2: "First Anytype-native LLM wiki" claim qualification -- RESOLVED**

The Problem Statement (line 24) now uses "to our knowledge, the first Anytype-native LLM wiki implementation" instead of the unqualified "first" claim. The positioning statement (line 169) mirrors this: "To our knowledge, the first Anytype-native LLM wiki." A verification requirement (line 171) explicitly states that the Anytype community forum, anytype-mcp repo issues/PRs, and GitHub must be searched before the README ships, with instructions to revise positioning if a prior implementation is found. The claim is now hedged, the verification is documented, and the fallback is defined.

**SF-3: Entity resolution thresholds acknowledged as provisional -- RESOLVED**

The ingest pipeline section (line 326) now includes an explicit note: "These thresholds are provisional defaults adopted from the research synthesis examples, not empirically validated against bge-m3 similarity data on actual entity pairs. They should be tuned during Phase 2 testing against real ingest data." The configuration reference table (lines 474-475) labels both thresholds as "provisional -- tune during Phase 2." This sets the right expectation for implementers and users.

**SF-4: Pipeline orphan detection -- RESOLVED**

The lint checks table (lines 429-430) now has two distinct orphan checks:
1. **Pipeline orphan** (High): Cross-references WikiLog entries containing failure/partial-failure text against objects created in the same ingest run. Objects with zero `wiki_relations` from a partial-failure run are flagged immediately with no grace period.
2. **Orphan entity/concept** (High): The original 7-day grace period check, now explicitly scoped to "manually created or from successful ingest."

This directly addresses the R1 concern that the most common orphan scenario (partial ingest failure) had a 7-day blind spot. The test plan (line 597) includes a specific acceptance test for the pipeline orphan path.

**SF-5: Quick-start scope clarified -- RESOLVED**

The 15-minute claim is now consistently qualified across all occurrences:
- User story (line 51): "within 15 minutes of `pip install` (with prerequisites already running)"
- Success metric (line 58): "with all prerequisites met (Anytype desktop running, Qdrant running, Ollama running with bge-m3 pulled, Python 3.11+)"
- README structure (line 483): "measured from `pip install anytype-rag` with all prerequisites already met"
- Community positioning success criteria (line 566): same qualification

Additionally, the README structure (line 482) now includes a "Prerequisites" section listed before the Quick-start, addressing SG-1.

**SF-6: Write token contradiction resolved -- RESOLVED**

The Security Considerations section (line 537) now reads: "Whether the existing anytype-rag bearer token (currently used only for read operations) also covers write operations is unresolved (see Open Question #6). Phase 1 implementation must verify this as its first step: attempt a write operation (e.g., creating a test type) with the existing token." This no longer asserts that a different token is needed -- it acknowledges the question is open, defers to Open Question #6, and defines a concrete verification step as the first Phase 1 action. The contradiction between "unknown" and "requires write token" is eliminated.

### SUGGESTION Items

**SG-1: Prerequisites section in README -- INCORPORATED** (line 482)

**SG-2: wiki.status tool -- DEFERRED** (lines 639, explicit rationale: v1 already provides `wiki.lint` with `severity_threshold="critical"` as partial substitute; fifth MCP tool increases surface area before core four are validated)

**SG-3: Configurable tag taxonomy -- INCORPORATED** (lines 275-283, bootstrap accepts optional `domain_tags` parameter with example)

**SG-4: Comparison type clarification -- INCORPORATED** (lines 257, explicit note that ingest does not auto-create Comparisons; two creation paths documented; reconsidering if consistently empty after Phase 2-3)

**SG-5: Supported source types -- INCORPORATED** (line 321, explicit list of supported types: plain text, markdown, HTML; explicit unsupported types with error behavior: PDFs, paywalled articles, JS-rendered pages)

**SG-6: API call budget per operation -- ALREADY PRESENT in R1 for ingest; now expanded in Resource Impact section (lines 517-519) with query and lint estimates.

---

## Regression Check

### Comparison type clarification (SG-4) -- no contradictions introduced

The note at line 257 clarifies that ingest extracts entities and concepts only, not Comparisons. This is consistent with:
- The ingest pipeline steps (lines 320-332) which mention "entities (with descriptions), concepts (with definitions)" as extraction targets, with no mention of Comparisons.
- The IngestResult schema (lines 304, 307) which includes `entity|concept|comparison` in the type enum -- this is technically broader than what ingest produces, but the `comparison` value is needed because wiki.query file-back may create Comparisons (documented in line 257). No contradiction.
- The lint suite's `object_counts` (line 401) which includes `comparison: 0` -- correct, the type exists in the schema even if ingest never populates it.

### Supported source types (SG-5) -- no contradictions introduced

The explicit scoping of v1 to plain text, markdown, and HTML (line 321) is consistent with:
- The ingest pipeline step 1 "URL via httpx" -- httpx fetches HTML, which is then converted.
- The test plan's arxiv example (line 583) -- arxiv URLs serve HTML abstract pages, which are within scope. The test is valid.
- The `wiki_source_type` select options (line 230): `article | paper | transcript | repo | other`. The "paper" option could imply PDF support, but the source type classifies the *content*, not the *fetch format* (a paper can be ingested as its HTML abstract page or as a pre-converted markdown file). No contradiction, but this is a minor ambiguity -- see suggestion below.

### Configurable tags (SG-3) -- no gaps created

The `domain_tags` parameter at bootstrap (lines 275-283) is well-specified: optional, defaults to Jan's domains, community users pass their own list, existing tags skipped on re-run. The `wiki_` prefix convention is preserved for custom tags (example uses `wiki_cooking-techniques`). No gap.

### Deferred wiki.status (SG-2) -- no gaps created

The deferral rationale is sound: `wiki.lint(severity_threshold="critical")` provides the critical-findings portion of a status check, and the four core tools should be validated before adding a fifth. The deferral is tracked in the Deferred Items section with an explicit trigger for reconsideration ("after Phase 4 ships if lint performance is an issue").

---

## Findings

### BLOCKING

No findings at BLOCKING severity.

### SHOULD-FIX

No findings at SHOULD-FIX severity.

### SUGGESTIONS

- **SG-R2-1: "paper" source type option could confuse users about PDF support**
  - Section: Type Schema, Source type properties (line 230)
  - Issue: The `wiki_source_type` select includes "paper" as an option, while the ingest pipeline explicitly states PDFs are unsupported in v1. A user ingesting an arxiv paper via its HTML abstract page would correctly tag it as "paper," but the presence of "paper" as a source type alongside the "no PDF support" note could cause momentary confusion. This is minor -- the source type classifies the content's nature, not its format, and the DATA ERROR message for PDFs (line 321) is clear. No action required; noting for awareness.

---

## What's Done Well

- **Appendix A is excellent.** The copy-pasteable curl protocols with decision matrices are exactly what the implementation team needs. The PATCH test's marker-string approach and the FilterExpression test's three-step count comparison are well-designed experiments.
- **Pipeline orphan detection is the right design.** Splitting orphan detection into two checks (pipeline-orphan with no grace period, manual-orphan with 7-day grace) directly addresses the most common failure mode without penalizing manual creation workflows.
- **Consistent qualification of the 15-minute claim.** Every occurrence of the quick-start timing now carries the same prerequisite qualification. No ambiguity remains.
- **Write token resolution is clean.** The Security Considerations section no longer contradicts Open Question #6. The "verify as first Phase 1 step" instruction is actionable and prevents the token issue from blocking the quick-start design.
- **Comparison type note is thorough.** The explicit documentation of when Comparisons are created (manual or query file-back), when they are not (ingest), and the reconsideration trigger (Phase 2-3 usage data) is the right level of pragmatism for a v1 feature.
- **Deferred Items section is well-curated.** Each deferral has rationale and a trigger for reconsideration, not just "out of scope."

---

## Recommended Changes Summary

No changes required. One informational suggestion noted (SG-R2-1) that does not require action.
