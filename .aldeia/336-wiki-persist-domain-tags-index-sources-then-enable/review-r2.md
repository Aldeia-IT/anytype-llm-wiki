# Spec Review R2 (post-fix verification) — #336

**Date:** 2026-06-13
**Reviewer:** focused re-review agent + lead inline fixes.

## Verdict: **APPROVED**

All R1 findings independently verified RESOLVED against the spec text and the actual code (current branch + `#323` branch via `git show`):
- **B1 (BLOCKING):** §10.2b enumerates all four inverted `test_chunker.py` tests (159/164/179/315) with correct citations; §12 updated; surviving heading tests correctly identified. RESOLVED.
- **SF1:** resolver home flipped to `ingest.py` (matches the `_resolve_wiki_action_tag` precedent; `remember.py:39` imports from `.ingest`); import direction confirmed non-circular; inline-duplication language removed. RESOLVED.
- **SF2/D4b:** `_create_remember_source` writes a non-empty stub excerpt (source name) for note-less agent sources; AC-S-AGENT added. RESOLVED.
- **SF3, SF4:** per-candidate `props` append clarified (inside loop, both branches); `_create_source` shared-`props` covers reuse+create; AC-S-REUSE added. RESOLVED.
- **SF5:** OD-B presents three neutral options; not pre-decided; `type_key` distinguishes excerpts. RESOLVED.
- **SF6:** OD-A names manual backfill follow-on; corpus-coverage caveat surfaced in Open Question Q1. RESOLVED.
- **SF7:** AC-P3 asserts on `worklog.begin` meta + JSON round-trip (not `_apply_batch`). RESOLVED.
- **SF8:** AC-PAYLOAD + AC-RESOLVER added. RESOLVED.
- **SF9, SF10, SF11, SG1–SG4:** all RESOLVED. SG5 no-action (line drift hedged).

All #323 seam citations re-verified accurate.

## New findings (both prose-level, fixed inline by the lead — no further round needed)
- **NEW-1 (SHOULD-FIX, prose):** D11 said `wiki_query` "already calls `_domain_taxonomy`" — incorrect (it's defined in `ingest.py`, called only from `wiki_ingest`). `wiki_query` has a live `WikiClient` and CAN call it (a NEW call). **Fixed inline** — D11 now states this accurately.
- **SF1 wrapper note (trivial):** clarified that the `_resolve_wiki_status_tag`/`_resolve_wiki_source_type_tag` wrappers stay in `remember.py` and call the now-imported `_resolve_select_tag`. **Fixed inline** (D1).

## Open Decisions (remain Jan's calls at the Decide gate — by design, not defects)
- **OD-A:** forward-only domain_tags (existing corpus not retroactively tagged; auto-derivation proven impossible; manual backfill available as follow-on).
- **OD-B:** whether source excerpts surface in `semantic_search` by default — three options presented (surface-by-default / index-but-default-exclude / defer).
- **OD-C:** SET (replace) semantics for `wiki_domain_tags` on update.

## Hard dependency (carried to Decide/Implement)
#336 implementation MUST rebase onto #323 (which is approved-to-done but not yet merged to main). All deltas are specified against #323's seams.
