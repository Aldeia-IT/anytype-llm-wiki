# Spec Addendum — post-test council (R1)

**Source:** [`council-test-r1.md`](council-test-r1.md)
**Date:** 2026-06-05
**Target phase:** impl
**Status:** Authoritative — the implementation phase MUST honor these items as spec requirements.

The post-test review council signed off the test suite itself (4/4 on the suite) but
the CTO raised one **BLOCKING** documentation hazard: the committed
[`test-review-r2.md`](test-review-r2.md) contained inverted "two-call `list_objects`"
guidance that contradicts the corrected single-enumeration fixtures (commit `1c5a0df`)
and the spec — and because `_standard_mocks` now returns the same combined page on
every call, a wrong two-call impl would still pass most tests (a silent trap). The
council chair resolved the BLOCKING in-meeting by (a) annotating the stale guidance in
`test-review-r2.md` with a SUPERSEDED banner, and (b) issuing this addendum, which the
CTO accepted as the veto-lifting condition ("an impl-brief is issued pinning the
single-enumeration constraint"). These items are now hard requirements for impl.

## Additional acceptance criteria for the impl phase

1. **[CTO-BLOCKING-1 / QA-ADV-1] Single-enumeration constraint is mandatory.**
   `wiki_lint` MUST call `WikiClient.list_objects(space_id)` **exactly once** and reuse
   that one `all_objects` list for BOTH the QA#25 schema gate
   (`_schema_version_from_objects(all_objects)`, pure/no-I/O) AND the check battery —
   the `query.py:408` pattern, per spec Pre-Checks step 2 and note G9. A two-enumeration
   ("two-call") design is a spec violation that doubles the O(N) `list_objects` cost the
   perf budget is engineered to avoid. The corrected fixtures (`1c5a0df`) put the schema
   marker and wiki entities in ONE combined page (`{"data": [schema_marker, *objects],
   "pagination": {"has_more": False}}`, mirroring `test_query.py:556`) and will FAIL a
   two-call impl that filters zero entities from the first page. **The "two-call"
   guidance in `test-review-r2.md` is explicitly superseded and must be ignored.** The
   authoritative reference is `test-review-r2-lead-addendum.md`.

2. **[CTO-ADV-2 / QA-ADV-3] Import `AnytypeReadClient` / `get_object` from the
   top-level package.** The module is `anytype_llm_wiki.anytype_client` (top-level), NOT
   `anytype_llm_wiki.wiki.anytype_client`. The spec's reuse table and smoke-test prose
   are loosely worded; the committed test imports the correct path
   (`from anytype_llm_wiki.anytype_client import AnytypeReadClient`). Use the test's path.

3. **[CTO-ADV-1, endorsed by QA] Run a spec-faithful single-call stub check before
   declaring tests green.** The recurring defect class this phase
   (tests satisfiable only by a non-spec-faithful impl, masked pre-impl by ImportError)
   was caught three times and only fully resolved by the lead's independent single-call
   stub run. The impl-worker should likewise verify the real `wiki_lint` against the
   suite incrementally and not "fix" any test to accommodate a two-call design.

4. **[CTO-ADV-1 / QA-ADV-2] `backlinks` shape is impl task ONE.** D1's `obj["backlinks"]`
   primary path rests on a single live-API finding, unverifiable from source and
   unexercised in CI (only the skip-gated `test_backlinks_field_shape_live` fences it).
   Confirm the real shape against a live `get_object` BEFORE building the primary path,
   and ensure the malformed-fallback branch is correct.

5. **[CPO-6 / CA-9, BLOCKING-class for the impl-phase docs gate] Documentation honesty
   deliverables — discrete impl tasks, not buried prose.** The spec's Implementation
   Plan README row (spec.md:410) currently only mandates the duplicate-sweep opt-in /
   truthful perf-claim wording. The impl phase MUST additionally:
   - **(CPO-6)** State in README + the `wiki_lint` tool docstring + the LintReport output
     that the `contradiction_unresolved` check is **passive until v0.6.0/#287** — a green
     contradiction result is NOT a guarantee. Operator over-trust is a reputation risk
     under the Aldeia-IT OSS name.
   - **(CA-9)** Document the six `WIKI_LINT_*` knobs compactly with an explicit "you
     don't need to set any of these" note (brand voice: developer-facing, concise), and
     do NOT oversell `pipeline_orphan` — it is an honest ±300s timestamp heuristic with
     false negatives by design.
   - **(CA-B1, already in spec.md:410)** Keep the truthful perf claim: the advertised
     ≤60s/≤500 budget describes the default sweep-off path only.
   The impl-phase council should verify the README lint section against these before ship.

6. **[CPO-7] Double-count detail legibility.** When an aged needs-review object fires both
   `unreviewed_needs_review` (High) and `stale_needs_review` (Medium), the two findings'
   `detail` fields must make the shared object legible (e.g. both reference the same
   object id/title) so the `summary` counts do not read as double-counting confusion.

## Advisory (non-gating) for the impl/test phases

- **[CPO-ADV-1]** Consider adding an all-empty-pipeline fixture asserting zero
  `contradiction_unresolved` findings in isolation (the current `test_contradiction_check_passive`
  proves passivity inside a fixture that also contains a firing conflict entity). Strengthens
  the "green is not a guarantee" contract; not required for v0.5.0.
- **[CTO-ADV-3]** The `>500` budget test models 501 objects as one physical page; no test
  exercises genuine multi-page `has_more` traversal with the marker only on page 1. Acceptable
  for v0.5.0; note if multi-page robustness later becomes a concern.

## Rationale

Items 1–2 are correctness contracts the corrected fixtures already enforce but which a
naive reading of the superseded `test-review-r2.md` would violate — pinning them here (the
file the impl lead reads during Task Intake) is the council's veto-lifting remedy. Items
4–6 are the post-spec council's carry-forward advisories (4–10) plus the CPO/CA test-phase
findings; they were tracked only in spec.md's Council-Resolution prose (line 505) and were
dropped from the test phase summary's hand-off list, so they are consolidated here as
explicit impl deliverables to prevent silent loss before the OSS release.
