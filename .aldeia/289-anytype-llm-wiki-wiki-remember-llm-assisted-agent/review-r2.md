# Specification Review (Round 2): `wiki_remember` (#289)

**Reviewed:** 2026-06-04
**Spec version:** commit fb35625 + lead inline residual fixes
**Reviewers:** Architecture/Completeness (CTO), Security (CSO) — focused re-review verifying the R1 resolutions against actual source.
**Verdict:** **APPROVED**

Round 1 raised 9 BLOCKING + 16 SHOULD-FIX + 7 SUGGESTION. The spec-fixer (`fb35625`) addressed all of them. Two independent re-reviewers verified the resolutions against the live codebase (not the spec's self-description).

## CTO (architecture + completeness) — APPROVED
All assigned BLOCKING resolutions verified PASS against source:
- **B3** PASS — bootstrap `_ensure_wiki_status_tags`/`_ensure_wiki_source_type_tags` consume `prop_map` (key-as-id fallback, `bootstrap.py:314-318`) like `_ensure_wiki_action_tags` (`bootstrap.py:519`); D5↔D6 split (bootstrap-seeds vs runtime-resolves) is unambiguous.
- **B4** PASS — single source_type rule (substring "conversation" → conversation, else agent); contradictory variants deleted.
- **B5** PASS — `subject_hint` fallback honors `kind="concept"`; concept-branch test added.
- **B6** PASS — `_write_wikilog(action_name="ingest")` change in §3 scope + §11.1 + ordered step; default preserves `f"ingest {subject}"` (`ingest.py:256`); remember-prefix AC + ingest-regression AC.
- **B7** PASS — AC-R6 now a twice-driven CI convergence test (stateful mock client; no `update_object` on call 2; stable object_id).
- **B2/B8** PASS — empty (`[CONFIG ERROR] empty_knowledge`) and oversize (`[DATA ERROR] knowledge_too_large`, cap `_KNOWLEDGE_MAX_CHARS=32_000`) both enforced before lock/LLM; hard-gate tests spy that lock/extract are never called.
- **B9** PASS — multi-candidate tie-break (`ambiguous_subject` warning + skip, never guess); grounded in `resolve_entity` first-match semantics (`ingest.py:184-186`).
- **SF6/SF9/SF12/SF15** PASS — `_MAX_SUBJECTS=8` cap + shared-lock disclosure; AC-R23 reframed as a regression guard (no new doctor check); degraded-read symmetry; `_resolve_wiki_action_tag` default-ingest regression test.

Cross-cutting: single-approach rule holds after edits; every new R2 AC (R25–R31, R12b, SF15, B5 concept) maps to a named non-tautological §10 test; load-bearing code citations all resolved correctly. No BLOCKING unresolved or newly introduced.

## CSO (security) — APPROVED WITH CONDITIONS (conditions are impl-time, not spec)
- **B1** PASS — `consolidated_text` → `sanitize_property_value` on write (AC-R27 spy test) + `fact_actions[].action` closed-enum validation with drop-on-unknown; conflict-flagging derives from `conflicts[]`, not from an inferred `action="conflict"` string (a malformed entry cannot fabricate/suppress a flag).
- **B2** PASS — `knowledge` hard cap before lock/LLM (DoS/OOM gate).
- **SF4** PASS — `source` note `scrub_credentials` → sanitize → truncate; lock source_ref scrub (`util.py:204`) noted, not bypassed.
- **SF5** PASS — relation endpoint client-side `type.key` check (no same-name wrong-type wiring).
- **G2/G4** PASS — consent gate documented as non-interactive self-ack (`extraction.py:253-265`); no-nested-conflict-marker regression test.
- R1 strengths intact / strengthened: dual-DATA anti-injection framing; never-silently-overwrite invariant (SF1 strengthens it — flag runs independent of the PATCH-skip gate); both HARD GATES still require driving the real entry point.

CSO conditions are implementation-review checks (confirm the live-path tests drive the real entry point; confirm the exact `sanitize_property_value(consolidated_text)` value reaches `update_object`) — carried forward to the impl phase, not spec changes.

## Residual SUGGESTION/ADVISORY items — resolved inline by the lead
1. Citation precision: `config.py:18` → `src/anytype_llm_wiki/wiki/config.py:18` (two sites + one prose ref). **Fixed inline.**
2. Lock param name: `space_ingest_lock(space_id, source=…)` → `source_ref=…` (two sites, matches the real signature). **Fixed inline.**
3. CTO ADVISORY-2 (lock-hold wall-clock under the cap): the spec already discloses worst-case `N × WIKI_EXTRACT_TIMEOUT` with `N ≤ _MAX_SUBJECTS=8` (§7, §8.3) — disclosure requirement met; no change needed.

## Outcome
Zero BLOCKING, zero SHOULD-FIX remaining. All SUGGESTION/ADVISORY residuals applied inline. The spec is approved for advancement. The two CSO impl-time conditions are recorded for the implementation reviewer.
