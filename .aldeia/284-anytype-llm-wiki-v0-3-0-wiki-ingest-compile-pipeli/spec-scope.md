# Spec Scope: 284 — anytype-llm-wiki v0.3.0 (`wiki_ingest`)

**Date:** 2026-06-03
**Repo:** anytype-llm-wiki
**Ticket:** #284
**Master spec:** `.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/spec.md` (status SPEC, council-approved)

## Nature of this spec

This is an **increment spec**, not a from-scratch spec. The master spec (#140) is the
authoritative design baseline for the whole module and already specifies `wiki_ingest`
(Workflow 2 / Ingest Pipeline / Entity Resolution Semantics / Extraction Prompt Structure /
v0.3.0 delivery phase ACs). This spec does NOT re-derive that design. It:

1. **References** the master spec for the bulk of the ingest design (file layout, signatures,
   SSRF, extraction prompt, entity-resolution pseudocode, failure-modes table).
2. **Resolves the open decisions** the master spec deliberately left to "v0.3.0 time".
3. **Locks in the now-verified Anytype constraints** (the master spec carried dual code paths
   pending verification; verification is done — `patch-decision.md` committed).
4. **Adds the newly-discovered indexer property-gap requirement** (not in the master spec).
5. **Firms the v0.3.0 acceptance criteria**, adding ACs for the new/resolved items.

## Domains touched

- agent-operations (the wiki module / MCP tool surface)
- infrastructure (indexer/Qdrant, Ollama extraction, fcntl lock)
- security (SSRF, prompt-injection — already designed in master; increment re-confirms)
- product (Karpathy "compile once" premise; retrievability is the user-visible payoff)

## Estimated complexity: moderate

Most of the design exists. The genuinely new/decision work is bounded to three areas plus
constraint-locking. But two of the three (marker home, indexer gap) are load-bearing and
were surfaced by live findings post-v0.2.0, so they need careful spec treatment.

## The three open decisions this spec MUST resolve

### Decision 1 — Indexer property-gap closure (NEW; release blocker)
**Problem (reproduced live this session, `llm-wiki-test`: `objects_checked: 22, objects_indexed: 0`):**
`indexer.py` → `chunk_object(obj)` chunks only `obj["markdown"]` (the body, fetched via
`get_object(..., format=md)`). Wiki objects store knowledge in **properties**
(`wiki_facts`, `wiki_description`, `wiki_definition`, `wiki_summary`), NOT in the body. So a
freshly-curated wiki yields **0 chunks** → invisible to `semantic_search` → the entire
"compile once, query later" premise fails.
**Constraint that shapes the fix:** PATCH of an object `body` is **silently ignored**
(`patch-decision.md`), so "ingest writes a markdown body representation" cannot be refreshed
on the update path (re-ingest of an existing entity). CREATE-time body works, but updates do
not. This strongly favors **extending the chunker/indexer to embed designated wiki text
properties** over the write-a-body approach. Research must confirm the property data shape
returned by the read API and design the chunker extension (which property keys, how chunked,
metadata/heading attribution, dedup vs body chunks).

### Decision 2 — Schema-version marker home reconciliation (mandated before v0.3.0)
Master spec (§Schema Compatibility, AC #13) says the **root Collection** carries
`wiki_schema_version`. v0.2.0 impl instead stamped it on the **per-run WikiLog** because the
system `collection` type "did not reliably persist a custom property" (known-limitations #2;
impl-review-r2 SHOULD-FIX-1 / ADVISORY-1). v0.3.0 `wiki_ingest` is the **first consumer** that
reads the marker (every tool's schema-compat check reads `wiki_schema_version`). So the marker
home must be made authoritative and single-valued now. Options:
- **(a)** Implement spec as written: stamp the long-lived root Collection (single property
  PATCH — `patch_property_updates: works` now), treat WikiLog stamp as informational.
- **(b)** Amend the master spec / AC #13 to name a different long-lived singleton marker home,
  with spec-writer sign-off.
Research must determine whether a custom text property reliably persists on the system
`collection`-typed root object via the now-verified property-PATCH path, and recommend (a) or
(b) with a concrete, testable mechanism. The chosen home must be a **single authoritative
value**, not `_max_version` over an unbounded WikiLog set.

### Decision 3 — `wiki_action` select-tag pre-creation
`wiki_action` is a `select`; writing a select value requires a pre-created tag option
(known-limitations #3; impl-review-r2 SHOULD-FIX-2 — v0.2.0 dropped it silently). v0.3.0
writes a WikiLog per ingest and must populate `wiki_action`. Spec must specify creating the
needed `wiki_action` tag options (at least `ingest`; ideally the full enum
`ingest|query|lint|bootstrap|archive` so later versions inherit them) before setting the
value, and where that creation happens (bootstrap vs lazy-on-first-use in ingest).

## Verified constraints to LOCK (no dual paths in shipped spec)
From `patch-decision.md` (anytype 2025-11-08):
- `patch_body_updates: silently_ignored` → ingest updates content via **properties only**
  (`implementation_path: fallback_properties_only`). Drop the master spec's "Primary path —
  PATCH body works" branch entirely.
- `filter_expression: no_op` → type-scoped search must use Qdrant payload filter or
  client-side filtering, NOT Anytype-native `type_key` FilterExpression.
- `patch_property_updates: works` → property updates are the durable write mechanism.

## Key prior learnings to inject (Mem0)
- `scrub_credentials` urlparse pitfall + doctor must scrub endpoint URLs (security; v0.2.0 debrief).
- fcntl.flock concurrency tests MUST use `multiprocessing.Process` (not threads/asyncio/mock).
- Spec ambiguity anti-pattern: **deprecate rejected approaches explicitly**; do not leave both
  in the document (this is exactly why the dual PATCH path must be collapsed to one).
- README claims must not exceed spec positioning (Legal/CPO, #140 R2).

## Hermes operational policies to (re)affirm in spec
Session orientation; append-only WikiLog; contradiction = document-both-and-flag (passive
until v0.6.0); cross-link min ≥2 outbound; page-threshold policy. These are in the master spec;
the increment spec references them, it does not restate them in full.

## Out of scope (per master spec roadmap)
`wiki_query` (v0.4.0), `wiki_lint` (v0.5.0), automated `wiki_contradictions` (v0.6.0),
PDF/JS sources, auto-merge below threshold, multi-space federation.

## Files at risk of staleness if implemented
- `README.md` (How it works + ingest diagram + extraction config table + trust note)
- `CHANGELOG.md`, `MIGRATIONS.md`, `.env.example`, `NOTICE`
- `docs/known-limitations.md` (items #2 and #3 get reconciled → update/close)
