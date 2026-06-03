# Spec Review — #284 v0.3.0 `wiki_ingest` increment (Round 2)

**Date:** 2026-06-03
**Spec:** `.aldeia/284-anytype-llm-wiki-v0-3-0-wiki-ingest-compile-pipeli/spec.md` (commit `923b9f9`)
**Reviewer:** focused re-review sub-agent (fresh context) + lead verification
**Scope:** verify R1 fixes are correct, complete, and internally coherent; catch any regression the fixes introduced.

## Verdict: APPROVED

All **5 BLOCKING** (B1-B5), all **9 SHOULD-FIX** (SF1-SF9), and all **5 SUGGESTIONS** (G1-G5) from `review-r1.md` are resolved. No new contradiction introduced. Code-grounded claims re-verified.

### B2 (the load-bearing fix) — verified coherent across ALL sections
The empty-body-on-create invariant for ingest-authored objects tells one consistent story across §4.1 Decision 1, the §4.1 dedup-guard paragraph, the §4.1 Mermaid flowchart (both branch labels), §5.1, AC-P7, and the Appendix (which now carries an explicit deprecation row forbidding a non-empty body on `wiki_ingest` CREATE). The reviewer specifically searched for residual "create-time body may contain content" permissions for ingest objects and found the remaining hits are all in rejection/rationale or deletion contexts — not permissions. Manually-created-with-body objects still get body chunks (the only case the guard's body branch serves). No regression.

### Other BLOCKING — resolved
- **B1:** `WIKI_SCHEMA_VERSION` bump to `"0.3.0"` named as a hard prerequisite in §4.2, §7.1, §10.1. (Code confirmed still `"0.2.0"` at `types_schema.py:25`, so the named bump is necessary.)
- **B3:** Defensive `.get(...)` access mandated in the extended `chunk_object`; AC-P8 + `test_property_chunk_missing_space_id_tolerated`.
- **B4/B5:** AC-L1 (no body/markdown key in update PATCH; mock-spy) and AC-L2 (client-side type filter on mixed-type search) present, concrete, with §9.5 test rows.

### SHOULD-FIX — resolved
SF1 (AC-S1 `WIKI_EXTRACT_ENDPOINT` scrub + fixture + test), SF2 (property-value injection residual-risk note + sanitizer-on-values AC), SF3 (`objects_skipped: []` restored), SF4 (AC-M1a/M1b split + b-1 test), SF5 (V2 release-blocking + update-path end-to-end AC-P7), SF6 (`_read_schema_version` reuses scan-loop, AC-M3 reconciled to `type.key=='wiki_log'`), SF7 (`max(collection, wikilog)` read), SF8 (§5.2 prescriptive — drop `filter=`, always post-filter), SF9 (V4 sequenced before marker test/impl). All verified.

### SUGGESTIONS — applied
G1 (AC#13 disambiguation), G2 (AC#14 wording), G3 (wiki_facts growth note), G4 (citation hygiene + `_find_root_collection` type-guard), G5 (known-limitations #3 forward-port note).

### Internal-consistency sweep — clean
§5 / §8 / §9 / §11 / Appendix agree. Every new AC has a §9 test row. AC numbering (P1-P8, M1a/M1b/M2-M5, T1-T5, L1/L2, S1) has no collisions. No dangling cross-references.

## Minor observation (non-blocking — no revision required)
- **AC-M5** (upgrade-path Collection PATCH) is Option-(a)/V4-PASS specific but not explicitly tagged "gated on V4 PASS" the way AC-M1a is; its Collection-PATCH assertion is covered transitively by `test_bootstrap_patches_collection_on_fresh_space` rather than a dedicated upgrade-path test. Harmless; can be tightened during the test phase. Recorded as a carry-forward note, not a blocker.

## Outcome
Zero BLOCKING / SHOULD-FIX remaining. Spec is ready to advance. Per the spec-phase exit policy, the ticket routes to **Decide** (watcher-routed council review precedes Jan's decision).
