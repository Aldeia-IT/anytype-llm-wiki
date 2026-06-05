# Spec Scope: anytype-llm-wiki v0.6.0 — automated contradiction detection

**Ticket:** Aldeia-IT/aldeia-box#287
**Client:** anytype-llm-wiki
**Branch:** aldeia/287-anytype-llm-wiki-v0-6-0-automated-contradiction-de
**Date:** 2026-06-05

## Problem (one line)
`wiki_contradictions` ships schema-only (v0.3.0) and the v0.5.0 lint
`contradiction_unresolved` check is **passive**. v0.6.0 makes cross-object
contradiction detection **automatic at ingest** (populating `wiki_contradictions`
bidirectionally, `wiki_last_reviewed` null) and **re-activates** the lint check.
Tracked by master-spec OQ#8.

## Domains touched
- agent-operations (ingest extraction pipeline, LLM prompt extension)
- infrastructure (Anytype REST wire contracts, lint, idempotency/resume)

## Estimated complexity: **moderate** (high reuse of #284 ingest + #286 lint + #289 patterns)
Risk of bloat is real (see #289 lesson) — keep tight, reference inherited
constraints by ID, factor large prompts to a referenced file.

## Scope boundary (from Jan's pre-queue feedback — pin precisely)
- **#289 `wiki_remember`** does **same-object** (intra-entity) conflict flagging:
  sets `wiki_status=needs-review`, returns `conflicts_flagged`. It does NOT touch
  `wiki_contradictions`. (`remember.py::_flag_conflict_status`, `_same_type_candidates`.)
- **#287 (this)** does **cross-object** contradiction detection at **ingest**:
  populates `wiki_contradictions` (the property lint's passive check reads),
  bidirectional, `wiki_last_reviewed` null. Different surface, different signal.
- Document the #289 → #287 handoff explicitly in the spec.

## Key prior learnings to inject (Mem0)
1. **Wire-contract pinning (#289, council-caught, HIGH):** pin verb + path +
   the existing respx test mock to mirror for EVERY endpoint the feature calls.
   `WikiClient.search` → **POST** `/v1/spaces/{id}/search` (mirror
   `test_ingest.py` `respx.post()`). `list_tags` is a **property-scoped two-step**.
   Naming only the method lets the test phase guess the verb wrong (the GET/POST
   defect that slipped two review rounds in #289).
2. **Spec bloat (#289, HIGH):** review-fix loop ratchets up by appending. Rules:
   reference parent/inherited locked constraints by ID (don't recopy); keep large
   prompts/schemas as separate referenced files; spec-fixer CONSOLIDATES not only
   appends; ≥8 BLOCKING in R1 = scope/altitude signal to tighten/decompose.
3. **Unverified core contract (#284, HIGH):** every live AC needs an explicit
   test-plan row AND a CI-runnable seam-test backstop (fake Anytype client + fake
   extractor) — do NOT leave the core promise verified only by skip-gated live
   tests. For #287 the core promise is: ingest a contradicting claim → bidirectional
   `wiki_contradictions` link + null `wiki_last_reviewed` → lint reports it High →
   setting `wiki_last_reviewed` clears it. This MUST have a CI-runnable seam test.
4. **Spec coherence (#140):** single authoritative decision per question; deprecate
   rejected approaches; every declared variable/field both written and read.
5. **Base drift (#231):** verify base divergence at phase entry. (Checked: worktree
   HEAD == origin/main f121b27, lint #286 already landed. No drift.)
6. **Schema is by KEY (`wiki_*`), display names prefixed `Wiki …` at v0.4.1 (#303).**

## What already exists (do not re-spec — extend)
- Schema v0.4.1 (`types_schema.py`): `wiki_contradictions` (format `objects`),
  `wiki_last_reviewed` (format `date`), `wiki_status` (select) on Entity + Concept.
- Lint `contradiction_unresolved` check exists but **PASSIVE** (`lint.py:20-22,77-82,
  _PASSIVE_CONTRADICTION_NOTE`, `notes` in `_empty_report`). Activate it.
- Ingest pipeline (`ingest.py`): `_run_ingest`, `resolve_entity`, `_merge_extraction`,
  `_write_bidirectional_relations`, `_patch_relation`, `_rel_key`. Hook point.
- Bidirectional relation writer already exists (`_write_bidirectional_relations`) —
  reuse the pattern for the contradictions edge.
- `remember.py::_flag_conflict_status` — the #289 same-object path (boundary).

## Spec-deferred fold-ins to decide disposition (per ticket)
- Hard **ingest SLO** (`< 2 min p95` for 10k-word source) — release gate or keep aspirational?
- **Partial-state idempotency resume** (#284 AC#18) — if deferred from v0.3.0, ship
  here: re-ingest after partial failure reuses existing Source, logs `resumed_partial_ingest`.
  Researcher must confirm whether #284 actually shipped this (commit `2c36f55` "make
  re-ingest idempotent" suggests partial coverage — verify exact behavior).
- **Backlinks O(1)** (OQ#7) — native `backlinks` confirmed exposed; lint #286 already
  uses `_backlinks_inbound`. Confirm whether #287 needs it for contradiction lookup
  or it's already adopted.

## Out of scope
- Automated merge/resolution of contradictions (human-in-the-loop only).
- Multi-space federation.

## Docs/artifacts at risk of staleness if implemented
- `README.md` (ingest + lint sections, feature matrix, version table)
- `CHANGELOG.md` (v0.6.0 entry)
- `src/.../wiki/lint.py` passive-note docstrings (`_PASSIVE_CONTRADICTION_NOTE`)
- Master spec `.aldeia/140-.../spec.md` OQ#8 resolution note
- No root `CLAUDE.md` present (only `.aldeia/context/`); update context/technical.md if config vars added.
