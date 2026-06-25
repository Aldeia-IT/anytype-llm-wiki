# Council Impl R1 — QA Director Review (#426)

**Ticket:** #426 Surface concept contradictions in wiki_lint
**Phase:** post-implementation (final delivery gate)
**Date:** 2026-06-25
**Reviewer:** QA Director
**Verdict:** SIGN-OFF (YES) — 0 BLOCKING, 2 ADVISORY

## Summary

The deliverable meets all three acceptance criteria with meaningful, fail-first
test coverage, honors every item of both spec addenda (post-spec 1–8, post-test
1–5), and resolves all impl-review findings (0 open). The central risk — the
`update_type` replace-not-merge graph-corruption footgun — is defended in depth
(four guards) and unit-tested on every path. The marker-after-loop ordering
invariant guard was independently verified to have teeth (perturbation test by
the reviewer, see below). The source-hardening that resolved the pre-existing
test collisions is a genuine safety improvement, not a regression mask. Regression
risk is LOW.

## Test-run result (verified by reviewer)

```
611 passed, 14 skipped, 2 xfailed, 50 warnings in 4.80s
```

Command: `uv run pytest tests/wiki/ -q`. Re-confirmed green after a perturbation
experiment was reverted (source diff empty, suite still 611 passed).

### Independent verification performed
- Ran the full `tests/wiki/` suite — green.
- Spot-checked all named key tests exist and assert substantively (see AC table).
- **Marker-ordering guard teeth check (post-test addendum item 1):** temporarily
  moved the schema-version stamp BEFORE the reconcile loop;
  `test_reconcile_partial_failure_recovers_on_rerun` assertion B failed with
  `'0.4.2' != '0.4.2'`. Reverted; confirmed source clean and suite green. The
  guard is NOT vacuous post-impl.
- Confirmed source landed: lint gate `bootstrap`+`lint.py:490` widened to
  `("wiki_entity","wiki_concept")`; `WIKI_SCHEMA_VERSION = "0.4.2"`;
  `SYSTEM_PROP_KEYS` exact constant; `wiki_last_reviewed` on `wiki_concept`.
- Confirmed docs: README "not yet flagged"/"planned follow-up" absent;
  MIGRATIONS 0.4.2 "re-bootstrap REQUIRED" + un-clearable-`critical` warning;
  new `docs/deploy-runbook.md` with golden rule + durable audit-log capture;
  CHANGELOG 0.4.2 entry.

## Regression-risk assessment

**Source-hardening of malformed `get_type` envelope — SOUND, not a mask.**
The new `get_type` call on the existing-types path broke 5 pre-existing bootstrap
tests whose blanket `respx.get()` mocks returned the list shape `{"data": [...]}`
for every GET, causing `get_type`'s `["type"]` access to `KeyError`. The impl
resolved this by hardening the source (`bootstrap.py:527-537`): a missing-`type`
KeyError or non-dict/no-`properties` body is treated like a partial read → warn +
record in `types_skipped` + NO PATCH. This is correct because:
1. The `except (KeyError, TypeError)` clause is narrow. Genuine transport/HTTP
   errors are NOT caught here — they propagate to the wrapper
   (`bootstrap.py:237-246`), proven by the partial-failure test where an
   `HTTPStatusError` on the 2nd PATCH propagates out and leaves the marker unstamped.
2. The fail-safe matches the spec's BL-6 philosophy exactly: never drive a
   destructive replace-PATCH on an incomplete read. A malformed envelope is
   functionally indistinguishable from a partial read.
3. For the affected legacy tests the type already carries all properties, so a
   skip is the correct no-op outcome regardless.

**The 3 "legitimate test edits" — all defensible.**
- `test_docs_disclosure.py::test_readme_discloses_concept_lint_surfacing_gap`:
  the #325-era assertion REQUIRED the README to describe the gap as an open
  "planned follow-up" — directly contradicting #426's spec §5 which closes it.
  The edit updates to the superseding #426 contract AND adds a strengthened
  `"not yet flagged" not in readme` absence assertion. Spec-superseding, not weakening.
- Two reconcile mocks under-modeled the real 7-property `wiki_concept` schema;
  assertions unchanged — fidelity fix to match the live `get_type` shape probed
  in `research.md §1b`. Defensible.

**Existing tests still pass** (611), no previously-passing test broken by impl.

## Findings

### ADVISORY

**QA-IMPL-ADV-1 — Pagination/shape guards are tested against a synthetic, not
live, contract.**
`research.md §1b` (test-phase live probe, BL-6.4) confirms the live Anytype
single-type GET returns `properties[]` inline with NO `pagination` key. The
pagination-abort and missing-`properties`-key tests therefore exercise SYNTHETIC
shapes (documented as such in the test docstrings). This is acceptable and
correct — the guards defend against an unadvertised future API change — but the
council should record that the `has_more`-abort path will never fire against
today's API, so its only value is forward-defense. No action required; documented
risk.
- Impact: none today; low residual forward risk fully mitigated by the guard.
- Recommended action: none; retain as-is.

**QA-IMPL-ADV-2 — `_make_concept` retains the pre-existing `wiki_description`
vs schema-declared `wiki_definition` inconsistency.**
Per spec SG-b this was deliberately NOT propagated to the new params and NOT
"fixed" (out of scope). Verified the impl honored this. Harmless test-fixture
inconsistency carried forward; flag only so it is not mistaken for a coverage gap.
- Impact: none on correctness; cosmetic test-fixture debt.
- Recommended action: track for a future cleanup ticket if desired; not for #426.

### BLOCKING
None.

## Addendum / AC verification table

| Item | Requirement | Status | Evidence |
|---|---|---|---|
| AC#1 | Concept contradiction fires `critical`, clears on `wiki_last_reviewed` | PASS | `test_concept_contradiction_unresolved` + cleared/no-contra guards; `lint.py:490` widened |
| AC#2 | Idempotent reconcile links `wiki_last_reviewed`, never drops props, no-op when complete, present in `_empty_result` | PASS | 4 `test_reconcile_*` + `test_result_has_required_keys`; `bootstrap.py` union-send |
| AC#3 | README gap clause removed (automatable) + CHANGELOG/MIGRATIONS/README prose | PASS | `test_docs_surfacing.py` (2 absence asserts); README/CHANGELOG/MIGRATIONS verified by inspection |
| post-spec 1 / QA-1 | Update `0.4.1` version pin → `0.4.2` | PASS | `test_wiki_schema_version_is_042` asserts `== "0.4.2"`; no `0.4.1` pin remains |
| post-spec 2 / QA-A2 | `get_type` read-side live probe recorded | PASS | `research.md §1b`; mock `_make_live_type_response` mirrors real shape |
| post-spec 3 / QA-A2 | Explicit pagination-abort test | PASS | `test_reconcile_pagination_abort_warns_no_patch` + missing-props variant |
| post-spec 4 / QA-A3 | Partial-failure test asserts marker UNSTAMPED | PASS | assertion B `schema_version_stamped != "0.4.2"`; teeth verified by perturbation |
| post-spec 5 / QA-A4 | Fail-first tests fail on substantive assertion | PASS | value asserts (`0==1`, `0>=1`, status), not Import/AttributeError (test-phase verified) |
| post-spec 6 / CTO-A2 | Empty/None `properties` refusal inside `update_type` | PASS | `TestUpdateTypeGuard` (3 cases); `ValueError` in `wiki_client.update_type` |
| post-spec 7 / CPO-1 | Lint gate + reconcile ship together; deploy runbook | PASS | single change; `docs/deploy-runbook.md` "REQUIRED" golden rule |
| post-spec 8 / CSO-3 | Durable audit log captured | PASS | SG-e INFO log before each PATCH; runbook §"Durably capture the reconcile audit log" |
| post-test 1 / QA-ADV-1 | Marker-ordering guard has teeth post-impl | PASS | reviewer perturbation: assertion B fails when stamp moved before loop |
| post-test 2 / QA-ADV-3 | AC#3 prose docs (CHANGELOG/MIGRATIONS/README) | PASS | inspected all three |
| post-test 3 / Infra-3 | Migration sequencing + deploy runbook + MIGRATIONS Unreleased warning | PASS | `docs/deploy-runbook.md`; MIGRATIONS §0.4.2 un-clearable-`critical` warning |
| post-test 4 / QA-ADV-5 | `update_type` refusal on single `ValueError` | PASS | impl-review confirms `ValueError`; guard-test tightened |
| post-test 5 / CSO-3 | Durable audit log (reaffirm) | PASS | confirmed at impl review |

## Sign-off

**YES — QA Director signs off.**

Rationale: All three acceptance criteria are met with traceable, meaningful,
fail-first tests; the full `tests/wiki/` suite is green (611 passed, 14 skipped,
2 xfailed), independently re-run. Every spec-addendum item (post-spec 1–8,
post-test 1–5) is honored and verified — including the one item that could only
be checked post-impl (marker-ordering guard teeth), which the reviewer confirmed
by perturbing the source and observing the guard fail correctly. The
graph-corruption footgun is defended in depth and tested on every path. The
source-hardening that resolved the pre-existing test collisions is a sound
fail-safe (narrow except, real errors still propagate), not a regression mask,
and the three test edits are spec-superseding or fidelity fixes. Regression risk
is LOW. The two ADVISORY findings are documented acceptable risk requiring no
action for #426.
