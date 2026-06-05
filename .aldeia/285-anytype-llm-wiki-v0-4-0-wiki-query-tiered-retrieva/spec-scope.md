# Spec Scope: 285 — anytype-llm-wiki v0.4.0 (`wiki_query`)

**Date:** 2026-06-04
**Repo:** anytype-llm-wiki
**Ticket:** #285
**Master spec:** `.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/spec.md` (status SPEC, council-approved)
**Hard dependency:** v0.3.0 `wiki_ingest` (#284, merged — incl. the indexer property-embedding fix)

## Nature of this spec

This is an **increment spec**, not a from-scratch spec. The master spec (#140) is the
authoritative design baseline and already specifies `wiki.query` (§"Query Pipeline
(wiki.query — v0.4.0)" lines 449–518; v0.4.0 module map + delivery ACs lines 878–905;
§Schema Compatibility lines 1590–1607; canonical `type_key` values lines 230–284;
relation property semantics lines 254–281). **This spec does NOT re-derive that design.**
It:

1. **References** the master spec for the bulk of the query design (data-flow diagram,
   signature, QueryResult schema, tier definitions, boundary semantics, file-back policy,
   compounding, FilterExpression decision, MCP conventions, deeplink formats).
2. **Locks the now-verified Anytype constraint** the master spec left as a dual path:
   FilterExpression is a **confirmed no-op** (`patch-decision.md`, live 2026-06-03), so
   Tier 1 ships the **fallback path only** (list-objects + property query params +
   client-side filtering). No dual path in shipped code.
3. **Grounds every helper/wire-contract** against the post-#284 codebase (the spec-writer
   must name real functions, real HTTP verb+path, and the existing test mock to mirror —
   not invented helpers).
4. **Firms the v0.4.0 acceptance criteria** into a single authoritative, testable list,
   including the QA#25 / QA#30 pre-checks activated at v0.4.0 and the boundary matrix.

**Anti-bloat directive (Mem0, #289 lesson):** #289 reached ~1,700 lines / 34 ACs for a
feature its own scope brief called "moderate, ~80% reuse." The review→fix loop ratchets
size UP by appending. This spec MUST stay lean: reference the master spec rather than
restating it, resolve findings by *tightening*, and target a tight AC set (aim ≤ ~15
firmed ACs, not a sprawl). Inherited constraints are referenced, not recopied as guard ACs.

## Domains touched

- agent-operations (the `wiki_query` MCP tool surface, synthesis, file-back)
- infrastructure (Qdrant `semantic_search` reuse, Anytype read/write clients, per-run cache)
- security (SSRF is N/A — no URL fetch in query; prompt-injection on synthesized content;
  pre-checks fire before any write)
- product (the Karpathy "compile once, query later" payoff; the compounding mechanism;
  completes the 15-minute community quick-start)

## Estimated complexity: moderate

The design is already specified in the master spec; v0.3.0 (#284) landed the read/write
clients, WikiLog, schema-compat check, patch-decision pre-check scaffolding, file-back-style
object creation, and the indexer property-embedding fix that Tier 2 depends on. The genuinely
new work is bounded: a new `wiki/query.py` (tiered retrieval + 1-hop cached neighborhood +
synthesis + file-back gate), a `wiki-query` CLI subcommand, and `server.py` registration.
High reuse of #284 patterns — but two areas need careful spec treatment (below).

## Areas requiring careful spec treatment

### A — Tier 2 depends on the #284 indexer fix (prerequisite, must be stated)
Wiki knowledge lives in **properties** (`wiki_description`, `wiki_definition`, `wiki_facts`,
`wiki_summary`), not the object body. Pre-#284 the indexer chunked body markdown only, so
`semantic_search` could not surface wiki knowledge. #284 extended the chunker/indexer to embed
designated wiki text properties. The spec MUST state #284's indexer decision as a **hard
prerequisite for meaningful Tier-2 retrieval**, and the `semantic_search(types=[...])` call
MUST target the canonical wiki `type_key`s (`wiki_entity`, `wiki_concept`, `wiki_comparison`,
`wiki_query`). Research confirms how `semantic_search` accepts a type filter and what payload
fields it returns (object_id mapping back to Anytype).

### B — FilterExpression no-op → single fallback path + 500-row warning
`patch-decision.md` (anytype 2025-11-08): `filter_expression: no_op`. The master spec's
"single canonical path with pre-v0.4.0 verification" therefore resolves to the **fallback**:
Tier 1 enumerates candidates via list-objects + property query params + **client-side
filtering** by `type_key`. The spec must DROP the "if FilterExpression works" branch entirely
(deprecate the rejected approach explicitly — do not leave both paths in the document). It
must specify the `filterexpression_fallback` warning emitted when the pre-filter result set
exceeds 500 rows (per master spec line 517), with the exact warning string.

## Verified constraints to LOCK (no dual paths in shipped spec)
From `patch-decision.md` (anytype 2025-11-08):
- `filter_expression: no_op` → Tier 1 candidate enumeration uses list-objects + client-side
  `type_key` filter. Single path.
- `patch_property_updates: works` → file-back writes the Query object's properties (question,
  answer, `wiki_drew_from` relations, timestamps) via the property path.
- `patch_body_updates: silently_ignored` → do NOT rely on object body for the filed Query's
  durable content; the answer text lives in a wiki text property so the next `reindex_anytype`
  embeds it (this is what makes filed queries retrievable — the compounding mechanism).

## Pre-checks to activate at v0.4.0 (firm as ACs)
- **QA#25 — `wiki_schema_outdated`**: `wiki_query` against a space whose `wiki_schema_version`
  is older than code's `WIKI_SCHEMA_VERSION` → `[CONFIG ERROR] wiki_schema_outdated` naming
  found+expected. `_newer` → warn-and-continue. Mirrors v0.3.0 AC. (master spec lines 904, 1590–1607)
- **QA#30 — `patch_decision_missing_or_invalid`**: missing/malformed `patch-decision.md` →
  `[CONFIG ERROR] patch_decision_missing_or_invalid` **before any Anytype write or Qdrant
  call**. (master spec lines 744, 905)
- Both pre-checks fire **before** any Anytype write or URL fetch (there is no URL fetch in
  query, but the ordering guarantee is identical to ingest).

## Core-contract test backstop (Mem0, #284 lesson — do NOT repeat)
On #284 three council members flagged that the core product promise (end-to-end
retrievability after ingest) was verified ONLY by `@pytest.mark.live` gates with no
CI-runnable backstop. For #285 the core promises are: (1) query returns an answer + ≥1 cited
source with deeplink; (2) `retrieval_mode` reflects count vs threshold; (3) a filed Query
object is retrievable on a subsequent query after reindex. The spec's test plan MUST provide
**CI-runnable (mocked) backstops** for these contracts — the live smoke test is additive,
skip-gated like v0.2.0/v0.3.0 live tests, not the sole verification.

## Wire contracts to pin (Mem0, #289 lesson)
The spec MUST pin, for every endpoint `wiki_query` calls: HTTP **verb + path + the existing
test mock to mirror**. Naming only the client method lets the test phase guess the verb wrong.
At minimum:
- `semantic_search(...)` → its actual server tool signature + the Qdrant/embedder path it runs.
- candidate enumeration (list-objects) → `GET /v1/spaces/{space_id}/objects?...` (verb/path
  per `anytype_client`/`wiki_client`) → mirror the respx mock in `test_ingest.py` / `test_wiki_client.py`.
- object fetch (`get_object`) → verb/path + mock to mirror.
- Query-object create + relation writes → verb/path + the `test_ingest.py` create mock to mirror.
- respx note: use no-arg `respx.post()/get()/patch()` for match-any (Mem0: `respx.patterns.M`
  raises at registration in installed respx 0.23.x).

## Key prior learnings to inject (Mem0)
- **Verify helper names against the actual codebase** — spec-writers invent intuitive helpers
  that don't exist. Research enumerates the real `wiki/` surface first.
- **Deprecate rejected approaches explicitly** — collapse the FilterExpression dual path to one.
- **Spec coherence**: cross-check every paragraph describing the same artifact; diagrams are
  normative, not illustrative — diagram steps must match pseudocode.
- **Anti-bloat**: tighten, don't append; reference the master spec.

## Reviewer dispatch note (Mem0)
The reviewer subagent types named in phase-spec.md (`completeness-reviewer`,
`spec-architecture-reviewer`, `security-reviewer`, `infra-reviewer`) are **not registered
Agent tool types** in this sandbox. Dispatch the review team as **general-purpose agents**
with the full role persona, the checklist reading list, and the anti-injection line embedded
in each prompt.

## Files at risk of staleness if implemented
- `README.md` (How it works + add a query section/diagram; quick-start now completes the loop)
- `CHANGELOG.md` (v0.4.0 entry), `MIGRATIONS.md` (only if `WIKI_SCHEMA_VERSION` bumps — it
  should NOT need to; query adds no new schema property), `.env.example`
  (`WIKI_INDEX_THRESHOLD`, `WIKI_FILE_BACK_MIN_SOURCES`, `WIKI_FILE_BACK_MIN_WORDS` if not
  already present)
- `docs/known-limitations.md` (Tier-2 quality bounded by index freshness / reindex cadence)

## Out of scope (per master spec roadmap)
`wiki_lint` (v0.5.0); automated `wiki_contradictions` population (v0.6.0); multi-space
federation (deferred); hard ingest/query SLO (v0.6.0+); multi-hop (>1) neighborhood traversal.
