# Spec Addendum — post-test council (R1)

**Source:** [`council-test-r1.md`](council-test-r1.md)
**Date:** 2026-06-12
**Target phase:** impl
**Status:** Authoritative — the implementation phase MUST honor these items as spec requirements.

## Additional acceptance criteria for the impl phase

These are coverage gaps in the (approved) failing-test suite that a *plausible faulty
implementation* could slip through while keeping the suite green. The post-test council
approved the test phase, but requires the impl phase to close these before final
delivery (the impl-worker adds the tests; the post-impl review verifies them).

1. **[AC-T1] Bind the D5 sort sub-keys, not just the outcome.** The current D5 ordering
   tests (AC4 `test_higher_rank_seed_neighbor_survives_trim`, AC5 `test_cap_warning_and_d5_top_n_fetched`,
   AC9 `TestContextBudgetD5Extension`) pass under fixtures where discovery order already
   equals D5 order — the rank-0 seed is always also the `object_id`-lexicographic winner,
   and `relation_priority` is never exercised (every neighbour uses `wiki_relations`,
   priority 0). An impl that does D1+D4 over the discovery-ordered distinct-id list but
   **omits the `sorted(..., key=(seed_rank, relation_priority, object_id))` call** would
   still turn these green. The impl phase MUST add at least:
   - one fixture where `seed_rank` and `object_id` **disagree** (a rank-0 neighbour whose
     `object_id` sorts lexicographically *after* a rank-1 neighbour) under a cap/budget
     admitting exactly one — asserting the rank-0 neighbour survives; and
   - one fixture where a single seed carries neighbours under **two different relation
     keys**, with the lower-priority key listed **first** in the object's `properties`
     (e.g. a `wiki_subjects` neighbour before a `wiki_relations` neighbour) under a cap
     admitting exactly one — asserting the higher-priority (`wiki_relations`) neighbour
     survives.
   This converts the outcome-binding tests into order-isolating tests and is the only
   guard for spec B3 ("list order is the sole carrier of relation priority").

2. **[AC-T2] Pin citation-title sanitization for the candidate/seed partition.** AC11
   (`test_rejected_neighbor_name_redacted_in_sources`) binds redaction only on the
   *neighbour* citation title. Spec D1/SF-B widens `_safe_object_name` to **all** citation
   titles, candidates included (pre-#324 seed titles used raw `obj.get("name","")`,
   query.py:567-568). The impl phase MUST add an assertion that a policy-rejected
   *candidate/seed* name also yields `title == "[REDACTED]"` (plus the
   `synthesis_name_rejected` warning) in `sources_consulted`, closing the partition
   symmetry so a faulty impl cannot sanitize neighbour titles while leaving seed titles raw.

3. **[AC-T3] Make `wiki_subjects` traversal binding (or add a constant guard).** AC2's
   `test_wiki_subjects_relation_traversed` reaches subjects as Tier-1 candidates (present
   in `list_resp`), not via `get_object` traversal, so a regression dropping
   `wiki_subjects` from `_RELATION_KEYS` would not be caught — and `wiki_subjects` is the
   OQ1-retained edge whose retention Jan confirmed. The impl phase MUST either mirror the
   `TestWikiSourcesTraversal` pattern for `wiki_subjects` (subject absent from `list_resp`,
   reachable only via traversal) **or** add a standalone constant guard asserting
   `"wiki_subjects" in _RELATION_KEYS`.

## Rationale

The post-test council approved the suite as fit to gate implementation — all 12 ACs are
pinned, the R1 "fails-forever" BLOCKING is genuinely resolved, and the load-bearing
security invariants are guarded by non-tautological tests. These three items are the
narrow residual: places where the *approved* tests bind an outcome that a specific class
of faulty impl could reproduce without honoring the underlying contract (D5 sort,
candidate-title sanitization, `wiki_subjects` retention). AC-T1 was raised independently
by both QA Director and CTO before cross-comparison, which is why it leads. Capturing
them here — rather than only in the meeting summary — ensures the impl lead reads them
during Task Intake and the post-impl review treats them as required checks, not optional
hardening.
