# Specification Review: wiki_query #324 — Relationship-Aware Retrieval (R2, confirming)

**Reviewed:** 2026-06-12
**Spec commit:** a18b10c
**Domain:** agent-operations (retrieval pipeline) + performance + security
**Review type:** Confirming re-review — verify R1 findings resolved; do not relitigate.
**Specialists invoked:** Completeness/QA (qa-director), Architecture (chief-technology-officer), Security (chief-security-officer), Infra/Performance (infrastructure-lead)

## Executive Summary

The spec-fixer (commit a18b10c) addressed every R1 finding — 4 BLOCKING + 10 SHOULD-FIX + suggestions. This R2 confirming review dispatched the original four-specialist panel to verify each finding is genuinely resolved **against the real code** (not just the spec's self-description), and to surface any new blocking issue the revisions introduced.

All four specialists returned a **CLEAR** domain verdict. Every R1 finding is RESOLVED with code-grounded evidence; no specialist found a new BLOCKING issue. The lead performed an independent spot-check of the most-cited code claims (below) and confirms them.

The spec carries one **Open Question (OQ1)** — retention of `wiki_subjects` as a deliberate deviation from the four-key #324 brief. This is a product-intent confirmation for Jan, correctly surfaced in the spec; it carries no security, architectural, or test weight (CISO and QA both noted it is cleanly bounded — a veto shrinks AC2 by one case with no other change). It is appropriately resolved at the Decide gate, not a blocker to phase exit.

**Verdict:** APPROVED

BLOCKING count: 0.

---

## R1 Finding Resolution (verified against code)

### BLOCKING (all RESOLVED)

- **B1 — `_neighbor_ids_of` return-shape.** RESOLVED. Spec (227-245) now returns `(id, relation_priority)` pairs with `prio = _RELATION_KEYS.index(key)`. Lead confirmed the current code (query.py:679-687) returns a flat `list[str]` that discards the relation key — the change is real and necessary; pseudocode is internally consistent. (CTO)
- **B2 — `_build_context` 4-tuple + real variable names.** RESOLVED. Spec (50-69) returns `(context_objects, surviving_candidates, surviving_neighbours, trim_warnings)`, partitioning on the real `candidate_id_set` (query.py:525). The phantom `candidate_id_set_before_trim` is gone (grep-confirmed). (CTO, Security corroborated)
- **B3 — list order is sole D5 carrier + test-meaning caveat.** RESOLVED. Spec (254-256) states neighbour dicts carry no rank field (`{"object_id","score":-1.0,"obj"}`, query.py:535 confirmed) so list order is the only D5 carrier; AC9 (469-479) carries the explicit `len(sources) <= 2` meaning-change caveat (real assertion at test_query.py:1680). (CTO/QA)
- **B4 — British-spelled test artifacts.** RESOLVED. All test-artifact identifiers are American; `TestNeighborhoodCacheReplacement` / `test_shared_neighbor_fetched_once` confirmed real at test_query_fetch_paths.py:73,75. Lead grep confirms the only "Neighbour" token in a test context is the prose instruction "use `Neighbor`, not `Neighbour`". (QA)

### SHOULD-FIX (all RESOLVED)

- **SF-A** default cap → 16 (≤ `SYNTH_MAX=24`, config.py:46 confirmed); inverted "headroom" framing explicitly dropped (spec 193-199). (CTO/Infra)
- **SF-B** all citation titles routed through `_safe_object_name` (query.py:265-275 confirmed: `[REDACTED]` + `synthesis_name_rejected`); inaccurate security claim corrected; AC11 binds it. (Security)
- **SF-C** `wiki_contradictions` deliberately deferred with rationale (spec 153-160; types_schema.py:95,111 confirmed). (CTO)
- **SF-D** Tier-1 seed rank pinned by sorting `candidate_entries` by `object_id` (spec 262-266). (CTO)
- **SF-E** fan-out observable at INFO via `neighbor_fanout: fetched=N` on the existing `result["warnings"]` list — no new required field (spec 280-285, AC6). (Infra)
- **SF-F** AC5 asserts **exactly** `min(distinct, cap)` and the D5-top N ids (spec 437-446). (QA)
- **SF-G** all-neighbours-trimmed → seeds-only edge documented (AC1, mapped test). (QA)
- **SF-H** failed neighbour consumes a cap slot, excluded from `sources_consulted` (spec 201-206, AC12). (QA)
- **SF-I** `_maybe_file_back` param `sources_consulted` **replaced** by `filed_sources` (before/after shown, spec 103-116). (CTO/QA)
- **SF-J** `.env.example` carries sibling-style multi-line comment with latency / API-pressure / waste notes (.env.example:58-62 confirmed). (Infra)

### SUGGESTION (incorporated)

SG-1 (ASCII `->`), SG-2 (D2 behaviour-preserving, AC7), SG-3 (no per-seed sub-cap accepted-risk in Security), SG-4 (per-session API pressure), SG-6 (`_TIMEOUT = 30` ceiling, _base_client.py:24 confirmed) all reflected. SG-5 promoted to AC12.

---

## New Issues Introduced by the Revisions

None. The revisions are mechanical refactors (return-shape changes, a param rename, an ordering carrier) plus a sanitization tightening:
- `_safe_object_name` routing strictly tightens the citation path (raw → policy-checked) — cannot introduce a leak.
- `filed_sources` replacement narrows the write sink (neighbours excluded from `wiki_drew_from`) — strictly reduces the injection-amplifier surface.
- Default 32 → 16 strictly reduces worst-case fan-out — a net resource improvement.

---

## Open Question (for Jan at Decide)

**OQ1 — `wiki_subjects` retention.** The spec retains `wiki_subjects` (a real `wiki_comparison` traversal edge shipped in v0.4.0) as a deliberate deviation from the strict four-key #324 brief, flagged for explicit confirm/veto. Non-blocking: a veto removes one key from `_RELATION_KEYS` and shrinks AC2 by one test case, no other change. Resolve at the Decide gate.

---

## Verification Audit (lead spot-checks)

- `_safe_object_name` (query.py:265-275): `[REDACTED]` + `synthesis_name_rejected` behaviour matches spec SF-B claim. ✔
- `_neighbor_ids_of` (query.py:679-687) currently returns flat `list[str]` — confirms B1 is a real, needed change. ✔
- `DEFAULT_WIKI_SYNTH_MAX_OBJECTS = 24` (config.py:46), `_TIMEOUT = 30` (_base_client.py:24) — match spec citations (SF-A, SG-6). ✔
- American test names at test_query_fetch_paths.py:73,75 — confirm B4 resolution. ✔
- Grep for "Neighbour" in test-artifact context: only the prose "use `Neighbor`, not `Neighbour`" instruction; all class/method names American. ✔

## Process note

Per R1, reviewer checklists live in `~/.claude/agents/<role>.md` (absent in the worktree). Reviewers were pointed at the real code paths directly; reviews are code-grounded, not document-only.
