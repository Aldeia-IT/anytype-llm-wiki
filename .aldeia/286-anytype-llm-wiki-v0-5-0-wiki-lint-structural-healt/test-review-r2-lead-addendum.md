# Lead Addendum to Test Review R2 — wiki_lint v0.5.0 (#286)

**Author:** test-phase lead
**Date:** 2026-06-05
**Verdict impact:** R2 (`test-review-r2.md`) returned APPROVED. The lead caught one additional **BLOCKING** satisfiability defect that R2 surfaced but mis-classified as a non-blocking "implementation note." It was resolved in a second fix cycle (commit `1c5a0df`) and independently re-verified by the lead. Final state: **APPROVED**.

---

## Lead-caught BLOCKING — single-enumeration satisfiability

**What R2 said (mis-classified):** "The `_standard_mocks` counter-based fixture design requires lint to make TWO separate `list_objects` calls … A single-call implementation (as `query.py` uses) would fail the test mocks. The impl-worker should adopt the two-call pattern."

**Why that is BLOCKING, not advisory:** The spec is explicit that lint performs **one** enumeration and reuses it for both the QA#25 schema gate and the check battery:
- Spec Pre-Checks step 2: *"Enumerate objects (one paginated list_objects sequence) → all_objects"*; step 3 derives schema via `_schema_version_from_objects(all_objects)` on that same list; note **G9** states the single enumeration read runs intentionally between QA#30 and QA#25.
- The pinned reuse pattern `query.py:408` calls `write_client.list_objects(space_id)` exactly once and filters that same `all_objects` for wiki types.
- `bootstrap._schema_version_from_objects` docstring: *"Pure — does no I/O so callers that already enumerated the space can avoid a second `list_objects` (N+1)."*

The original fixture put the schema marker in `list_objects_responses[0]` (`has_more: False`) and the wiki entities in `list_objects_responses[1]`. Because `WikiClient._paginated_get` stops when `has_more` is false, a single spec-faithful `list_objects()` call returns **only the marker**; the entities at index 1 are reachable only by a **second** `list_objects()` call. A spec-faithful single-enumeration impl therefore filters zero wiki objects and fires **zero findings** — failing `test_asymmetric_relation_check_fires`, all orphan/needs-review/stale/oversized/empty-type tests, and the duplicate-sweep tests. The suite was satisfiable **only** by an impl that diverges from the spec (two enumerations). Tests must conform to the spec, not the reverse — hence BLOCKING.

**Fix (commit `1c5a0df`):** `_standard_mocks` now returns **one** combined enumeration page `{"data": [schema_marker, *wiki_objects], "pagination": {"has_more": False}}`, mirroring `test_query.py:556`. The schema marker (`name=="Wiki"`, `type.key=="collection"`) is recognized by `_schema_version_from_objects` and excluded by the wiki-type filter. 26 callsites updated. Multi-page cases (>500 budget, sweep cap) model a single logical enumeration via internal `has_more` pagination with the marker on the first page.

---

## Independent lead verification (strongest gate)

The lead did **not** accept the fixer's stub claim at face value. The lead authored an independent throwaway single-call stub of `wiki_lint` (query.py pattern: one `list_objects` call → `_schema_version_from_objects(all_objects)` → filter wiki types → property-scoped two-step needs-review tag resolution → checks) and ran the two highest-risk previously-broken tests against it:

```
tests/wiki/test_lint.py::TestAsymmetricRelationCheck::test_asymmetric_relation_check_fires  PASSED
tests/wiki/test_lint.py::TestNeedsReviewChecks::test_unreviewed_needs_review_fires           PASSED
2 passed in 0.02s
```

The check loop reached the seeded entities and findings fired with a **single** `list_objects` call. The stub was deleted; the committed state has **no** `src/anytype_llm_wiki/wiki/lint.py`, and the full suite fails pre-impl (44 failed, 2 live deselected) and live tests skip-gate (2 skipped).

---

## Process note

Two in-phase review rounds plus the lead's spot-check were required to surface this. It is the same defect *class* as the #289 wire-contract lesson (tests unsatisfiable by a correct impl, masked pre-impl by ImportError) — but on enumeration *call-count/shape* rather than verb/path. Recorded to Mem0 for future test-review calibration: **when reviewing a client-driven enumeration suite, confirm the mock's page/`has_more` shape is satisfiable by the spec's single-enumeration pattern (run a single-call stub), don't only read the tests.**
