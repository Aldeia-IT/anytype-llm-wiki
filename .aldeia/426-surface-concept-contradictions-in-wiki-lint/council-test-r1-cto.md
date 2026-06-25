# Council Test Review (R1) — CTO

**Ticket:** #426 — Surface concept contradictions in wiki_lint
**Phase reviewed:** test (post-test governance)
**Reviewer:** CTO
**Date:** 2026-06-25
**Verdict:** SIGN-OFF (no BLOCKING findings; advisories only)

---

## Scope of audit

This is a governance audit of technical readiness and reviewer diligence — not a
re-review. I spot-checked the central spec-gate condition, the fail-first contract,
reviewer diligence (R1→R2), the factual-error handling, and decomposition. All claims
verified against the live worktree source and the test suite (`uv run --extra dev
pytest tests/wiki/ -q` → **16 failed, 593 passed, 16 skipped, 2 xfailed** — matches the
stated baseline exactly; every failure is an intended fail-first/regression).

---

## 1. Central spec-gate condition (BL-6.4 read-side probe) — DISCHARGED

The spec council made the `get_type` read-side live probe a **hard entry condition**
(council-spec-r1 Advisory 1, addendum item 2). The CTO at the spec gate sharpened it:
the pagination/shape guard and the name/format fallback both baseline off the *same*
`get_type` read, so the probe also had to confirm property-set **completeness** and
**nested pagination**.

**Verified in `research.md §1b`** — this is a real live probe, not a prediction:

- **Exact per-property field set recorded:** each entry carries `object`, `id`, `key`
  (NOT `property_key`), `name`, `format` — transcribed verbatim from a live
  `GET /v1/spaces/{id}/types/{type_id}` against `wiki_t_2` in `wiki-validation-throwaway`.
- **Pagination/completeness recorded:** the single-type `get_type` response has **no
  `pagination` key** and no nested pagination on `properties[]`; the array is returned
  inline and complete. The probe explicitly distinguishes this from the *list*-types
  response (which does paginate). This is precisely the completeness + nested-pagination
  confirmation the CTO demanded at the spec gate.
- **System-prop echo confirmed:** `tag`/`backlinks` ARE echoed in the read and must be
  filtered via `SYSTEM_PROP_KEYS` before union-building.

**Mock fidelity (addendum item 2):** `_make_live_type_response()`
(`tests/wiki/test_bootstrap.py:2000`) mirrors the observed shape exactly — `type`
envelope, per-property `object/id/key/name/format`, **no `pagination` key**, system
props echoed. It is used by all success-path reconcile tests
(`test_reconcile_adds_missing_property`, `_never_drops_existing_properties`,
`_no_op_when_complete`, `_partial_failure_recovers_on_rerun`). The pagination-abort tests
use a *documented synthetic* shape and say so in-test. This satisfies "the three safety
guards are tested against the real contract, not a fictional one."

**Assessment:** The dominant cross-functional concern from the spec gate is fully
discharged with empirical evidence. The "safe-by-construction" framing the council
accepted conditionally is now backed by a real read contract.

## 2. Faithful spec→fail-first translation — VERIFIED

I spot-checked each named fail-first test against the actual change-sites and confirmed
a correct impl would pass and a buggy/destructive impl would fail:

- **`test_concept_contradiction_unresolved`** (`test_lint.py:1327`) — fails on
  `assert len(contra_findings_a) == 1` → `0 == 1` (entity-only gate at `lint.py:490`
  produces zero concept findings). Substantive, not ImportError. Covers all three
  sub-assertions (fires critical; cleared by `wiki_last_reviewed`; silent without
  contradictions), faithfully mirroring the entity pattern. Verified `lint.py:490` is
  still `if tk == "wiki_entity":` (pre-impl).

- **`test_reconcile_never_drops_existing_properties`** (`test_bootstrap.py:2411`) — the
  load-bearing replace-not-merge guard. Asserts the PATCH payload contains both the live
  `wiki_custom_user_prop` AND `wiki_last_reviewed` (union, not delta), AND that no
  SYSTEM_PROP_KEYS leak into the payload (F-2 addition). A delta-only impl (sending only
  `["wiki_last_reviewed"]`) would omit the custom prop and fail. This is the single most
  important test in the suite given the graph-corruption blast radius; it is correct.

- **`test_reconcile_partial_failure_recovers_on_rerun`** (`test_bootstrap.py:2698`) —
  the sole automated guard on the marker-after-loop ordering invariant (addendum item 4).
  Strengthened to assert (A) error propagates, (B) schema-version marker NOT stamped to
  `0.4.2` after the failing run, (C) clean re-run recovers. The sentinel-list pattern
  correctly avoids the test swallowing its own `AssertionError`. Verified it currently
  goes RED on assertion A (`status='error'`), the correct first failure point.

- **Pagination-abort** (`test_reconcile_pagination_abort_warns_no_patch`,
  `_missing_properties_key_aborts`) — addendum item 3. Asserts NO `/types/` PATCH +
  `warnings[]` entry + `types_skipped` record. Both clearly documented as synthetic.

- **`update_type` empty/None/missing-key guards** (addendum item 6) — three guard tests;
  one fails-first (method absent), two skip until the method exists. Correct staging so
  the impl writer gets one clear failing signal rather than three identical failures.

**Source pre-impl state confirmed** (all four change-sites unimplemented, as expected for
a fail-first phase): `WIKI_SCHEMA_VERSION = "0.4.1"`; `wiki_concept` lacks
`wiki_last_reviewed`; no `get_type`/`update_type`/`SYSTEM_PROP_KEYS`; bootstrap still
unconditionally `continue`s existing types at `:281`.

## 3. Reviewer diligence (R1→R2) — GENUINE, NOT RUBBER-STAMP

The internal test reviewer did real verification, not a document read:

- **Caught a real BLOCKING gap.** R1 F-1: the test-writer *deferred* AC#3 (the README
  substring-absence check) as a "manual-review gate" with the justification "the impl
  hasn't shipped the docs yet." The reviewer correctly identified this as the same logic
  that would invalidate every other fail-first test, cited project precedent
  (`tests/test_ci_config.py`), and demanded the assertion. This is exactly the kind of
  test-writer rationalization a rubber-stamp review would have waved through.
- **R1 ran the tests** — quoted actual failure modes (`assert 0 == 1`, `assert 0 >= 1`)
  and distinguished them from ImportError/KeyError.
- **R2 re-ran and verified the fix at the line level** — confirmed `test_docs_surfacing.py`
  fails RED on the substring `AssertionError` (not IO/FileNotFound), resolves the repo
  root portably via `parents[2]`, and will flip GREEN post-docs.
- **Two SHOULD-FIX items were substantive**, not cosmetic: F-2 (system-prop exclusion not
  asserted in the union payload — a genuine coverage hole in the highest-risk test) and
  F-3 (overly broad `except Exception` masking accidental crashes as valid guards). Both
  resolved and re-verified in R2.

I independently confirmed F-1's fix: `README.md:175` still contains both "not yet flagged"
and "planned follow-up", so the two assertions in `test_docs_surfacing.py` are genuine
fail-first guards (currently RED, in the 16-failure baseline).

The review did surface codebase mismatches (the AC#3 gap, the system-prop coverage hole)
— it is not the suspicious "flawless, no mismatches" pattern. Diligence confirmed.

## 4. Factual error handling (0.4.1 version pin / QA-1) — CORRECTLY HANDLED

The spec's Test Plan (`spec.md:494-497`) and `review-r1.md:97` both wrongly asserted no
hardcoded `0.4.1` pin existed and told the test-writer not to edit one. The chair verified
this was false (`test_wiki_schema_version_is_041`). The addendum (item 1) made the
correction authoritative.

**Verified the test phase honored the correction:** `test_bootstrap.py:860` is now
`test_wiki_schema_version_is_042` asserting `WIKI_SCHEMA_VERSION == "0.4.2"` (a positive
pin — stronger than the inequality the spec implied), currently RED. The `grep -rn "0.4.1"
tests/` sweep was run; remaining occurrences are prose/docstrings, not assertions. The
inherited error that propagated through R1 and R2 was caught at the council gate and
correctly discharged in the test phase. Good closed-loop.

## 5. Decomposition — NO SPLIT (concur with spec council)

I re-assessed from the engineering/module-boundary angle. The five change-sites (schema +
client methods + bootstrap reconcile + lint gate + docs) span multiple files but form a
**single dependency chain with a deliberate safety coupling**: the lint gate (§4) and the
bootstrap reconcile (§3) MUST ship together — splitting them would strand existing spaces
firing an un-clearable `critical` (a concept contradiction flagged with no
`wiki_last_reviewed` field to resolve it). That is the exact broken-UX this ticket exists
to prevent. The schema bump and client methods are pure prerequisites of the reconcile;
the docs are the user-facing closure of the same gate.

The combined scope is well within safe single-PR / single-impl-lead bounds: one risky
section (the replace-not-merge reconcile), already defended by four guards + audit log +
regression test, with a clean fail-first contract. A single impl lead can hold this
context. No SPLIT RECOMMENDATION.

---

## Findings

### BLOCKING
None.

### ADVISORY

**A-1 (carry-forward to impl, low) — partial-failure assertion B is vacuous pre-impl.**
In `test_reconcile_partial_failure_recovers_on_rerun`, assertion B (marker NOT stamped to
`0.4.2`) passes trivially pre-impl because the current code stamps `0.4.1`. The debrief
acknowledges this; the test correctly fails on assertion A first, so this is not a
fail-first defect. But B only becomes a *meaningful* guard post-impl. The impl reviewer
MUST confirm B is actually exercised once the reconcile + 0.4.2 stamp land (i.e. that a
mis-ordered marker stamp would make B go RED post-impl), since B is the sole automated
guard on the load-bearing marker-after-loop ordering invariant. Verify, do not assume.

**A-2 (impl/release, operational) — addendum items 7–8 are untested by design.** The
migration-sequencing requirement (lint gate + reconcile ship together; "re-bootstrap
REQUIRED" in the deploy runbook, not just MIGRATIONS.md) and the durable capture of the
SG-e union audit log are not pytest-testable and were correctly excluded from the test
phase. They remain live obligations for the impl phase and release owner. **Flagging to
Infrastructure Lead:** the un-clearable-`critical` strand risk and the audit-log durability
both have operational implications that belong on the impl/release checklist, not just in
docs.

**A-3 (impl, doc-completeness) — AC#3 has a manual-review remainder.** The automatable
README check is in place, but CHANGELOG (0.4.2 entry) and MIGRATIONS.md ("re-bootstrap
REQUIRED" + prerequisite-for-lint-gate note) are manual-review gates. The impl reviewer
must confirm these by inspection; the README test alone does not cover them.

**A-4 (impl, minor) — F-3 exception tuple is still broad.** The guard tests accept
`(ValueError, AssertionError, TypeError[, KeyError])`. R2 reasonably accepted this, but the
impl should settle `update_type`'s empty/None refusal on a single exception (suggest
`ValueError`) so the contract is unambiguous. Non-blocking.

---

## Sign-off

**SIGN-OFF.** The test phase is technically sound and faithfully translates the spec and
the eight-item council addendum into a fail-first contract. The central spec-gate
condition — the BL-6.4 `get_type` read-side live probe, including the
completeness/nested-pagination dimension the CTO required at the spec gate — is discharged
with a real, transcribed live probe, and at least one reconcile mock mirrors the observed
shape. The highest-risk path (replace-not-merge graph corruption) is guarded by a
union-not-delta regression test plus a system-prop-exclusion assertion. The verified
factual error (0.4.1 pin) was correctly corrected. The internal reviewer demonstrated
genuine diligence: caught a real BLOCKING AC#3 gap the test-writer had rationalized away,
and two substantive SHOULD-FIX items, then re-verified each fix at the line level in R2.
The ticket is coherent as a single change; no split warranted. The four advisories are
carry-forward obligations for the impl phase and release owner, none gating.

No veto.
