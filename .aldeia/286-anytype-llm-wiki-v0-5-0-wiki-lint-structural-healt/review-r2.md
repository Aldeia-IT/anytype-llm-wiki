# Spec Review R2 — wiki_lint v0.5.0 (#286)

**Date:** 2026-06-05
**Scope:** Focused re-review of the R1 fix cycle (2 BLOCKING + 12 SHOULD-FIX + 9 SUGGESTION). Reviewer: general-purpose agent (architecture + completeness lens) + lead spot-check.
**Spec:** `.aldeia/286-.../spec.md` (revised, commit d4a2606)

## Verdict: **APPROVED** — ship it. No conditions.

All 2 BLOCKING and all 12 SHOULD-FIX R1 findings are genuinely resolved and faithful to the codebase. No new BLOCKING or SHOULD-FIX defects, no internal contradictions introduced by the edits. One optional SUGGESTION (non-blocking).

## BLOCKING — both resolved (verified against source)

- **B1 (duplicate band):** RESOLVED. `index_threshold()`/`÷1000` fully purged from all band/AC/test sites (only explanatory "do-not-use" mentions remain). Band `[0.70, 0.85)` via new `WIKI_LINT_DUPLICATE_MAX_SCORE` (default 0.85) + new `_bounded_float([0,1])` guard. 0.85 matches the master embedding auto-upsert threshold (master §424c, line 1563); 0.70 floor matches §424d/§600. Half-open band, self-match exclusion (`candidate_id != object_id`, sound vs `semantic_search_core` `object_id` at indexer.py:75), sorted-tuple pair canonicalization. Tests satisfiable (0.75 fires; 0.60/0.95 excluded; dedup test exercises both exclusion paths).
- **B2 (sweep cost/cap):** RESOLVED. Per-phase budget arithmetic honest — the ~51s non-sweep figure for 500 objects is corroborated by master spec line 602 ("~500 API calls, p50 100ms, ~50s, within 60s but tight"); the get_object fan-out is the genuine floor. Sweep gated to `severity_threshold="all"` + auto-skip above `WIKI_LINT_MAX_OBJECTS` (2000). Consistent with SF7 severity ordering everywhere. The two warnings (`lint_object_count_exceeded_budget` >500 advisory; `lint_sweep_skipped_object_cap` >2000 action) are distinct and non-overlapping.

## SHOULD-FIX — high-risk fixes verified against source
- **SF5 (age-derivation across 3 checks):** CORRECT. `wiki_ingested_at` is on `wiki_source` only (types_schema.py:79); entity/concept carry `wiki_sources` (93/109). The cross-source dereference (most-recent linked source) is the generous/false-positive-avoiding choice and sound for staleness. "No resolvable source → ungated" does NOT mask orphans — the age-independent `unreviewed_needs_review` High check still fires.
- **SF4 (schema 3 branches):** CORRECT. Matches query.py:424–448 exactly; `_cmp_versions` (ingest.py:447) sign assumptions correct.
- **SF9 (contradiction scoped to entity):** CORRECT. `wiki_last_reviewed` on `wiki_entity` (types_schema.py:97), absent from `wiki_concept` (105–113). Scoping to entity is right; check is passive until v0.6.0 regardless.

## Cross-cutting
- AC↔test mapping complete: all 15 ACs map to named tests; the new tests (partial-status, severity-low, dedup, schema-missing/newer, sweep-skip) are present. "10 checks" relabel landed consistently (AC5, check table, signature note). No surviving "9 checks" except correct "master's 9 → now 10" framing. `severity_threshold` default consistently `"all"`. SF11 scrub wording now matches util.py:98–141.
- Anti-bloat: 367→458 growth justified (budget table, schema branches, age note, resolution log) — no master-content restatement.

## SUGGESTION (non-blocking, optional)
- The `## Review Resolution (R1)` log (~27 lines) may be trimmed post-merge once the audit trail is no longer needed. Appropriate to retain through ship.

## Lead disposition
APPROVED with zero remaining BLOCKING/SHOULD-FIX. Advancing to Phase 8 (finalize). The single SUGGESTION is cosmetic and intentionally retained through ship as an audit artifact.
