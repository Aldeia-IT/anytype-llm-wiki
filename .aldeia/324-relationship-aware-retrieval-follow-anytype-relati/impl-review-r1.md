# Implementation Review: 324-relationship-aware-retrieval — Round 1

**VERDICT: APPROVED WITH CONDITIONS**

**Date:** 2026-06-12
**Branch tip reviewed:** 85c3080
**Reviewers:** Security+Spec-compliance (independent), Correctness+Quality (independent), Lead inline checks
**Suite state:** `uv run pytest tests/wiki/ -q -m "not live"` → 553 passed, 6 skipped, 2 xfailed, 0 failed.

## Summary

The #324 delta (D1–D6) is faithfully implemented in `query.py` + `config.py`, with the
three post-test-council addendum tests (AC-T1/T2/T3) added and empirically binding (the
lead confirmed AC-T1(b) goes RED under a no-sort mutation). All seven load-bearing
invariants — SF1 file-back bound, SF-B citation sanitization, SF-H cap-on-attempts, B2
membership partition, D5 sole-carrier ordering, ASCII warning string, no new attacker
surface — verified CLEAN by both reviewers independently and by the lead's line-by-line
read of the diff. No CRITICAL or MAJOR findings.

Conditions below are all MINOR; addressed in the fix round to reach zero open findings.

## Findings

### CRITICAL
None.

### MAJOR
None.

### MINOR (conditions — addressed in fix round)

**M1 — Duplicate `synthesis_name_rejected` warning (both reviewers, diff-introduced).**
`_safe_object_name` runs once inside `_truncate_object_content` (query.py:294) during
context build for every surviving object, then AGAIN at the citation-title path
(query.py:614) for the same surviving candidate+neighbour. A surviving object with a
policy-rejected name now appends `synthesis_name_rejected: {raw}` to `result["warnings"]`
TWICE (new for candidates; entirely new for neighbours). Cosmetic — AC11/AC-T2 use
`any(...)` membership so tests stay green — but it pollutes the warnings list, and the
inline comment at query.py:624-625 ("no re-sanitization → no duplicate warnings") refers
only to the `filed_sources` reuse, not this candidate-vs-context double-pass. FIX: route
the citation-title `_safe_object_name` call through a throwaway warnings list (the warning
is already emitted during context build for the same object), and correct the comment.

**M2 — AC-T1(b) docstring numeric error (Correctness reviewer, test comment).**
test_query_fetch_paths.py:1414-1416 docstring states the wiki_subjects neighbour's D5 key
as `(0, 2, ...)`, but `_RELATION_KEYS.index("wiki_subjects")` is 4, not 2. The assertion
*message* (line 1478) correctly says "relation_priority 4" and the test outcome is
unaffected (both 2 and 4 lose to wiki_relations' 0). FIX: correct the docstring number.

### MINOR (pre-existing — out of #324 scope, optional)

**M3 — Unused `warnings_sink` param in `_build_context` (Correctness reviewer).**
The function appends to a local `trim_warnings` and never reads `warnings_sink`. Signature
is unchanged by this diff (pre-existing). Optional cleanup: remove the dead param and its
single call-site argument. Low risk; per core discipline ("if something is unused, delete
it") the fixer may remove it since the function is already touched in this diff.

## Lead inline checks (Pass 1 + Pass 2)

- Spec Ordering steps 1–7: all present and correct (verified line-by-line against spec D1–D6).
- `_RELATION_KEYS` = 5 keys, `wiki_sources` at index 2, `wiki_subjects` retained (OQ1 — Jan confirmed "keep 5 keys").
- All 12 ACs + AC-T1/T2/T3 pinned by passing tests; addendum order-isolation empirically binding (no-sort mutation → AC-T1(b) RED).
- No regression: `_build_context` (3→4-tuple), `_neighbor_ids_of` (str→tuple), `_maybe_file_back` (param rename) are module-private with single internal callers, all updated; no external/test callers of old shapes.
- `.env.example` `WIKI_QUERY_MAX_NEIGHBORS=16` block present and correct (landed in spec phase).
- README roadmap line for #324 dropped (shipped).
- No secrets, no hardcoded `/Users/` paths in test bodies, credential scrubbing intact.
