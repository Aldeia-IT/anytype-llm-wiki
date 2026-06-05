# Council Meeting — Post-test (Round 1)

**Date:** 2026-06-05
**Ticket:** #286 — anytype-llm-wiki v0.5.0 `wiki_lint` (structural health check)
**Phase reviewed:** test
**Client:** anytype-llm-wiki (open-source MCP server, MIT, Aldeia-IT)

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator |
| QA Director | Yes | minimum — quality-gate owner for the test contract |
| Chief Technology Officer | Yes | chair decision — reviewer diligence was the central risk (3 satisfiability BLOCKINGs across 2 rounds + lead spot-check) |
| Client Advocate | Yes | chair decision — client project with full context; CA-B1/AC16 opt-in win must be verifiably enforced |
| Chief Product Officer | Yes | chair decision — confirm the test contract preserves day-one product value (D3 live High, passive contradiction, double-count) |
| Chief Security Officer | No | test phase introduces no new data/PII/credential/network surface; CSO signed off the security posture at post-spec council; nothing to adjudicate |
| Legal Counsel | No | MIT, read-mostly tool; no regulatory delta in a test-suite increment |
| Infrastructure Lead | No | no deployment/resource surface in the test phase; the perf/Ollama concern (CA-B1) was resolved at spec and is now test-enforced (AC16) |

## Context Presented

The test phase produced the complete FAILING test suite for
`wiki_lint(space_id, severity_threshold="all", include_duplicates=False) -> LintReport`
in one new file `tests/wiki/test_lint.py`: **44 CI-mocked tests** (all 33 spec Test-Plan
rows + 11 supporting gates) + **2 skip-gated live smoke tests**, covering all 16 ACs. No
implementation exists yet — this is the pre-impl test contract. The phase ran 2 in-phase
review rounds plus a lead addendum: R1 NEEDS CHANGES (2 BLOCKING: tag-id mismatch, silent
try/except false-green) → fix → R2 APPROVED, but the lead caught a third BLOCKING (a
single-enumeration satisfiability defect R2 mis-classified as a non-blocking note),
re-fixed it (commit `1c5a0df`), and independently re-verified with a single-call stub.

**Chair's independent verification:** re-ran the suite — pre-impl state is
`44 failed, 2 deselected` (not live), `2 skipped` (live); `src/anytype_llm_wiki/wiki/lint.py`
absent; tree clean. The central test-phase claim holds.

## Discussion

The council converged from four independent seats on a single material issue, with three
members (QA, CA, CPO) signing off the suite outright and the CTO raising one BLOCKING.

- **QA Director** built the AC↔test map independently: all 16 ACs map to ≥1 test, every
  test maps to an AC or a supporting gate, no orphans; full `tests/wiki/` collects 486
  tests with no breakage (additive). Confirmed the three recurring "unsatisfiable-by-a-
  correct-impl" defects (B1 tag-id, B2 silent patch, lead-caught single-enumeration) are
  genuinely resolved, with the highest-risk instance proven by an independent single-call
  stub rather than asserted. Confirmed the post-spec QA advisories landed: the AC13
  negative `.called is False` assertion against space-level `/tags`, and age fixtures
  seeded on a linked `wiki_source` (not the object). **Signed off**, flagging the stale
  two-call guidance in `test-review-r2.md` as a mandatory impl carry-forward.

- **CTO** spot-checked the wire contracts against source (search POST; property-scoped
  two-step tag resolution; `get_object` GET `?format=md` envelope; single combined
  enumeration page) — all correct — and confirmed via `git show` that the `1c5a0df` fix
  produces a single combined page while the original fixture was genuinely two-page.
  **Raised BLOCKING-1:** the committed `test-review-r2.md` still carried emphatic,
  bolded "adopt the two-call pattern" guidance that is factually inverted post-`1c5a0df`.
  Because `_standard_mocks` returns the same page on every call, a wrong two-call impl
  would *pass most tests* — making this a silent trap (tests green, design wrong), not a
  paperwork nit, and one that would double the O(N) enumeration cost the perf budget is
  built to avoid. Veto-lift condition: strike the stale guidance OR issue an impl-brief
  pinning the single-enumeration constraint.

- **Client Advocate** verified the CA-B1 win is enforced by a real, fail-able assertion:
  `test_duplicate_sweep_off_by_default` tracks both `semantic_search_core` and `_qdrant`
  and asserts zero calls on the default path AND on `severity_threshold="all"` — zero
  bge-m3 load and zero Qdrant construction, protecting the shared local Ollama on Jan's
  single box. Confirmed the R1 silent-try/except false-green that would have vacuously
  certified this guarantee was caught and fixed. Live smoke correctly skip-gated (no CI
  breakage on the client's machine). **Signed off**, flagging that the docs-honesty
  carry-forwards (CPO-6 passive-contradiction caveat; CA-9 knob docs / don't oversell
  `pipeline_orphan`) were dropped from the test phase summary's hand-off list.

- **CPO** confirmed the test contract preserves product intent: D3 `unreviewed_needs_review`
  tested as a real populated High finding (the day-one value signal off the status
  `wiki_remember` sets); passive contradiction check tested; the double-count rule tested
  as intended behavior. Scope is disciplined (44+2 tests / 16 ACs, no creep). **Signed
  off**, with advisories to carry CPO-6 (passive-contradiction docs) and CPO-7
  (double-count detail legibility) into the impl brief as discrete tasks, since they live
  only in spec.md council-resolution prose, not the Files-Changed plan.

The chair notes the CTO's BLOCKING and QA's "mandatory carry-forward" are the same issue
at different severities; per consolidation rules the higher severity (BLOCKING) is held.

## Findings

### BLOCKING

1. **[CTO, corroborated by QA] Stale two-call impl guidance in `test-review-r2.md`
   contradicts the corrected single-enumeration fixtures and the spec.** The committed
   review file (lines ~83, 120–124, 172) instructs the impl-worker to "adopt the two-call
   pattern," which commit `1c5a0df` and the spec (Pre-Checks step 2, note G9;
   `query.py:408`) make wrong. Because the fixtures return the same combined page on every
   call, a two-call impl passes most tests silently while violating the spec and doubling
   the O(N) enumeration cost. **RESOLVED IN-MEETING by chair action** (see Resolutions).

### ADVISORY

1. **[CTO, endorsed by QA] Satisfiability defect-class recurrence is a review-rubric gap.**
   The same "unsatisfiable-by-a-correct-impl, masked by ImportError" class slipped through
   as advisory twice and was only caught by lead stub runs. Final state is sound *because*
   the lead ran an independent single-call stub. Make "run a spec-faithful stub against any
   client-driven enumeration suite" a mandatory test-review step (already captured in the
   test-reviewer's Mem0 calibration note — endorsed).
2. **[CTO, QA] `backlinks` field shape is a live-only, source-unverifiable assumption** —
   D1 primary path; CI cannot exercise it (only skip-gated `test_backlinks_field_shape_live`).
   Confirm the live shape as impl task ONE.
3. **[CTO, QA] Spec path drift** — `AnytypeReadClient`/`get_object` live at top-level
   `anytype_llm_wiki.anytype_client`, not under `wiki/`; the test imports the correct path.
4. **[CA] Docs-honesty carry-forwards dropped from the test phase summary** — CPO-6
   (passive-contradiction caveat in README) and CA-9 (compact knob docs, don't oversell
   `pipeline_orphan`) live only in spec.md:505; they must reach the impl brief.
5. **[CPO] CPO-6 / CPO-7 not in the impl Files-Changed plan** — passive-contradiction docs
   and double-count detail legibility must be discrete impl deliverables.
6. **[CPO] Passive-contradiction tested mixed, not isolated** — consider an all-empty-
   pipeline zero-finding assertion (non-gating).
7. **[CTO] No genuine multi-page enumeration test** — the >500 budget test uses one
   physical page; acceptable for v0.5.0.

## Resolutions

- **BLOCKING-1 resolved by the council chair within this meeting**, per the CTO's stated
  veto-lift condition. Two actions taken and committed on the branch:
  1. **Annotated `test-review-r2.md` at source** — a SUPERSEDED banner at the top of the
     file plus an inline "DO NOT FOLLOW" block on the "Implementation Note for impl-worker"
     section, pointing to the lead addendum and the new spec addendum. The trap is removed
     where the impl-worker would read it.
  2. **Issued `spec-addendum-post-test-r1.md`** (authoritative; read during Task Intake)
     pinning the single-enumeration constraint as a hard impl requirement and consolidating
     ADVISORY 2–5 (path drift, backlinks impl-task-one, docs-honesty CPO-6/CA-9,
     double-count legibility CPO-7) as explicit impl deliverables.
- All four members' suite sign-offs stand; no sign-off was withdrawn. The single BLOCKING
  was a committed-artifact hazard, not a test-suite defect — the suite required no rework.
- ADVISORY-1's review-process lesson is already in Mem0 (test-reviewer calibration note);
  endorsed, not re-filed.

## Recommendation

**Recommended target:** impl
**Confidence:** high
**Rationale:** The test suite is a sound, AC-complete, spec-faithful contract (4/4 members
sign off the suite). The pre-impl state is genuine (44 failed via clean ImportError, 2 live
skipped, `lint.py` absent, tree clean), regression risk is minimal, the CA-B1 opt-in win is
enforced by a real fail-able assertion, and the recurring satisfiability defect class was
caught and verified-fixed by an independent single-call stub rather than asserted. The one
BLOCKING was a committed-artifact documentation trap, resolved in-meeting by annotating
`test-review-r2.md` at source and issuing an authoritative spec addendum that pins the
single-enumeration constraint — exactly the CTO's veto-lift condition. The impl phase should
proceed, honoring `spec-addendum-post-test-r1.md` (single-enumeration; top-level
`anytype_client` import; backlinks impl-task-one; CPO-6/CA-9 docs honesty; CPO-7 double-count
legibility). The watcher applies the autonomy policy to the routing target.
**Dissent:** None. The CTO's BLOCKING and the three sign-offs are consistent — all agree the
suite is sound and the only gap was the stale committed guidance, now corrected.
