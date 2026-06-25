# Council Impl Review R1 — CTO

**Ticket:** #426 Surface concept contradictions in wiki_lint
**Phase:** post-implementation governance review
**Reviewer:** CTO (engineering accountability / reviewer-diligence audit)
**Date:** 2026-06-25
**Disposition:** SIGN-OFF (YES) — 0 BLOCKING, 4 ADVISORY, no split recommendation

---

## Summary

This is a technically sound, well-defended implementation of a genuinely
dangerous change — a destructive replace-not-merge PATCH against the typed graph.
I did not re-review from scratch; I spot-checked the highest-risk claims against
the actual code and tests, and I independently exercised the single most important
guard (the marker-ordering invariant) with a live source perturbation. Every
claim I checked held. The phase reviewers did real codebase verification, not a
document-only pass, and the impl-fixer's readability refactors preserved every
guard. All four prior CTO advisories (CTO-A1..A4) are honored in code.

Verification performed (not trusted from the docs):
- Ran the full wiki suite: **611 passed, 14 skipped, 2 xfailed** — exactly the
  baseline the reviewers claimed.
- **Perturbed the source** to stamp the schema marker before the reconcile loop;
  the ordering-invariant test (`test_reconcile_partial_failure_recovers_on_rerun`
  assertion B) went RED with the expected message, then restored source. The
  "guard has teeth" claim in the phase summary is independently confirmed.
- Read `bootstrap.py::_reconcile_existing_type`, `wiki_client.get_type/update_type`,
  the `lint.py` gate, `types_schema.py`, the reconcile + lint tests, the
  live-probe transcript in `research.md`, and all four docs diffs.

---

## Addendum verification (CTO-A1..A4 + cross-cutting items)

| Item | Requirement | Status | Evidence |
|---|---|---|---|
| CTO-A1 / post-test item 1 | Marker stamp strictly AFTER reconcile loop; guard has teeth | HONORED | Reconcile in type loop `bootstrap.py:288-318`; both marker stamps after — Collection PATCH `:431`, WikiLog `:467`. Perturbation test confirmed RED when stamp moved before loop. |
| CTO-A2 / spec-addendum item 6 | Empty/None `properties` refusal inside `update_type` | HONORED | `wiki_client.py:40-45` raises `ValueError` before any HTTP call; `test_update_type_raises_on_empty_properties` guards it. |
| CTO-A3 / post-test item 2 | Complete AC#3 prose docs | HONORED | CHANGELOG 0.4.2 + surfacing-live; MIGRATIONS Unreleased section with un-clearable-`critical` warning; README gap clause removed; `test_docs_surfacing.py` added. |
| CTO-A4 / post-test item 4 | Settle payload-refusal on a single specific exception | HONORED | Single `ValueError` (not a broad tuple). Guard test accepts `ValueError` and fails if an HTTP call is reached. |
| spec item 2 / BL-6.4 | Live-probe `get_type` read side before shipping | HONORED | `research.md §1` carries a verbatim live transcript: per-prop `key`/`name`/`format` present, NO pagination on single-type reads, system props echoed. |
| spec item 3 / CSO-1 | Pagination-abort test | HONORED | `test_reconcile_pagination_abort_warns_no_patch`: asserts NO PATCH + warning + types_skipped. |
| items 5/8 | Durable audit log | HONORED | `docs/deploy-runbook.md` mandates durable capture of the `wiki_reconcile ...` INFO line emitted at `bootstrap.py:605`. |
| items 3/7 | Migration sequencing + deploy runbook | HONORED | `docs/deploy-runbook.md` created; lint gate + reconcile ship together. |

---

## Findings

### BLOCKING
None.

### ADVISORY

**A-1 — Marker is stamped in TWO places; the test only directly tracks one path.**
What I verified: read `bootstrap.py` marker stamps (Collection PATCH `:431`, WikiLog
`:467`) and the failing-run test's `patch_response_failing` capture. The test catches
ANY `wiki_schema_version` PATCH on the objects endpoint, so it transitively covers
both stamps — and my perturbation (which stamped via the Collection path) was caught.
Impact: low. The invariant is sound; just noting the dual-stamp design is not
obvious from the test name. Recommended action: none required; optionally a one-line
comment near `:431`/`:467` noting both are post-loop.

**A-2 — Error-propagation path is via wrapper, not a raw raise.** What I verified:
`update_type` HTTPStatusError is caught by the `wiki_bootstrap` wrapper at
`bootstrap.py:239` and converted to `status="error"` (HTTP 500 → `[API ERROR]`),
not re-raised to the caller. The partial-failure test handles both raise and
status-error paths, so the ordering invariant still holds. Impact: none — this is
the established error-handling contract. Noted only so a future reader does not
expect `wiki_bootstrap` to raise.

**A-3 — `is_upgrade` no longer drives the property work, but `schema_upgrade`
report block + `properties_added` still do.** What I verified: reconcile is correctly
gated only on the per-type missing-set (`:290-294`), independent of `is_upgrade`
(spec §3 / BL-2 honored). However `properties_added` (`:337-362`, reported in the
`schema_upgrade` block at `:446`) is computed from the create/skip property loop,
which is a separate mechanism from `types_reconciled`. For a 0.4.1→0.4.2 reconcile
of an already-bootstrapped space, the newly-linked `wiki_last_reviewed` surfaces in
`types_reconciled` but may NOT surface in the `schema_upgrade.properties_added`
list (it is reported as `properties_skipped`/`already_exists` at the space level).
Impact: low — cosmetic reporting only; `types_reconciled` is the authoritative
signal and is tested. Recommended action: none for this ticket; note for any future
"upgrade report" consumer that `types_reconciled` is the source of truth for linked
props on existing types.

**A-4 — Pre-existing `ruff F841` (unused `status_tag_map`/`source_type_tag_map` at
`:411-412`).** What I verified: confirmed present on `main` per debrief; not
introduced by this change. Impact: none on #426. Recommended action: out of scope;
worth a cleanup ticket independently.

---

## Split Recommendation

**No split recommendation.** Although the ticket touches four surfaces (schema,
wiki_client transport, bootstrap reconcile, lint gate), they are tightly coupled by
a single load-bearing invariant: the lint gate is un-clearable without the schema
property, which is only delivered by the bootstrap reconcile. Splitting would
re-introduce the exact un-clearable-`critical` footgun the spec exists to prevent
(the addenda explicitly require the gate and reconcile to ship together). The
combined diff is well-scoped, the risky surface (reconcile) is isolated in one
function with its own dense test class, and a single impl lead held the full
context without dropping details. Module boundaries here are a feature, not a split
signal.

---

## Reviewer-diligence assessment

The impl-review R1 was diligent, NOT document-only:
- It cites a re-run green suite (611) which I reproduced exactly.
- Its findings are concrete and code-anchored (line numbers, specific guard names,
  the `_prop_key` 8-call-site DRY observation), not generic prose.
- It correctly classified the destructive-PATCH path as the central risk and
  dispatched an impl-fixer for readability == auditability — appropriate for
  safety-critical code — with an explicit "no guard may be weakened" constraint
  that the debrief and my own test re-run confirm was honored (same 611 count, no
  test modified).
- The one place the spec was factually WRONG (the "no 0.4.1 pin exists" claim) was
  caught by the post-spec council addendum and fixed in the test phase
  (`test_wiki_schema_version_is_042`). That is the system working.

Reviewer blind spots: none material. The only thing the impl-review under-stated is
the dual-stamp nature of the marker (A-1) and the wrapper-not-raise error path
(A-2) — neither affects correctness. The live-probe entry condition (BL-6.4) was a
genuine risk the council gated on, and it was actually performed with a verbatim
transcript rather than predicted — exactly the "verified not hedged" standard.

---

## Sign-off

**YES.** The implementation is technically accurate, aligned with the live Anytype
contract (verified by a real probe, not a guess), and defends the replace-not-merge
data-corruption footgun in depth: empty-payload `ValueError` at source, malformed-
envelope abort, pagination guard, monotonic-union guard, SYSTEM_PROP_KEYS exclusion,
union-send, and an audit log before every PATCH — each path unit-tested. The
marker-ordering recovery invariant has independently-verified teeth. All four CTO
advisories and all cross-cutting addenda are honored in code, tests, and docs. The
four ADVISORY items are cosmetic/reporting and do not gate advancement. No split
warranted.
