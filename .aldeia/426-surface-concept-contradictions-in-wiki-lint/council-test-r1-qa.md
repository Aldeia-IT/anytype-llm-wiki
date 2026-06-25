# Council Test Review R1 — QA Director

**Ticket:** #426 — Surface concept contradictions in wiki_lint
**Phase:** post-test governance review (test → impl gate)
**Date:** 2026-06-25
**Reviewer:** QA Director (review council)
**Scope:** strategic quality-gate readiness, not line-by-line (internal test review APPROVED at R2).

---

## Verdict: SIGN-OFF (advance test → impl)

No BLOCKING findings. The test deliverable faithfully covers all three spec ACs and
addendum items 1–6, the fail-first guards are genuine and non-vacuous, and the central
replace-not-merge graph-corruption footgun is guarded from multiple angles. Five ADVISORY
items are recorded; all are impl-phase carry-forwards, none gate advancement.

---

## Verification performed (not taken on faith)

- Ran `uv run --extra dev pytest tests/wiki/ -q`. Confirmed the failure set: **16 failed**
  (identical to the R2-reported set), `593 passed, 16 skipped, 2 xfailed` in this
  environment. The pass/skip split differs from R2's `711 passed / 39 skipped` only because
  several integration tests skip without live Qdrant/Anytype services here — **the 16-failure
  set is byte-identical**, and every failure is an intended fail-first/regression guard for
  the new behavior. No previously-passing test is broken.
- Read all 16 failing test bodies plus the 3 forward guards and 2 skipped guards.
- Cross-checked `_make_live_type_response()` (test_bootstrap.py:2000) against the live
  `get_type` probe transcript in `research.md §1b` — the success mock mirrors the verified
  contract (top-level `type` envelope, per-property `key`/`name`/`format`, NO `pagination`
  key, system props echoed). Addendum item 2 genuinely satisfied.
- Confirmed both README target phrases (`"not yet flagged"`, `"planned follow-up"`) exist
  exactly once, in the single clause #426 rewrites (README.md:175).

---

## AC + addendum coverage assessment

| Item | Test(s) | Genuine guard? | Status |
|---|---|---|---|
| AC#1 concept contradiction surfacing | `test_concept_contradiction_unresolved` (fail-first, `0==1` on finding count + severity), + 2 forward guards (cleared / no-contradiction) | Yes — fails on substantive finding-count assertion, not import error | COVERED |
| AC#2 reconcile adds prop | `test_reconcile_adds_missing_property` (fail-first, `len(reconciled)==1`, `properties_added==["wiki_last_reviewed"]`, not-double-skipped) | Yes | COVERED |
| AC#2 never-drops (footgun) | `test_reconcile_never_drops_existing_properties` (union incl. custom prop AND new prop, AND system-props-absent) | Yes — directly defends the central risk | COVERED |
| AC#2 no-op when complete | `test_reconcile_no_op_when_complete` (forward guard, PATCH count == 0) | Yes | COVERED |
| AC#2 `types_reconciled` in `_empty_result` | `test_result_has_types_reconciled_key`, `test_types_reconciled_empty_on_fresh_space` | Yes | COVERED |
| AC#3 README clause removed | `test_readme_surfacing_gap_clause_removed`, `test_readme_planned_followup_clause_removed` | Yes — fails on substring AssertionError, README read succeeds | COVERED |
| Addendum 1 (version pin 0.4.1→0.4.2) | `test_wiki_schema_version_is_042` (renamed); `grep` confirmed no other hardcoded 0.4.1 assertion | Yes | SATISFIED |
| Addendum 2 (get_type read-side probe + mock fidelity) | research.md §1b probe recorded; `_make_live_type_response` mirrors it | Yes | SATISFIED |
| Addendum 3 (pagination-abort) | `test_reconcile_pagination_abort_warns_no_patch` + `test_reconcile_missing_properties_key_aborts` (both: no PATCH, warning emitted, type in types_skipped) | Yes | SATISFIED |
| Addendum 4 (partial-failure: marker UNSTAMPED) | `test_reconcile_partial_failure_recovers_on_rerun` (A: error propagates; B: `schema_version_stamped != "0.4.2"`; C: clean re-run recovers) | Yes — but see ADV-1 on B's pre-impl vacuity | SATISFIED |
| Addendum 5 (fail-first on meaningful assertion) | Verified the 3 named tests fail on value/count assertions (`0==1`, `0>=1`), not ImportError/AttributeError | Yes | SATISFIED |
| Addendum 6 (empty/None payload refusal in update_type) | `test_update_type_raises_on_empty_properties` (fail-first) + None/missing-key guards (skip pre-impl, tightened to `pytest.raises`) | Yes | SATISFIED |
| Addendum 7–8 (release/ops) | None — correctly identified as non-pytest impl/release items | n/a | DEFERRED to impl (see ADV-4) |

---

## Regression risk assessment

**LOW.** Evidence:

- The only existing test materially touched is the version-pin assertion
  (`test_wiki_schema_version_is_041` → `_042`, value `0.4.1`→`0.4.2`), correctly updated.
  `grep -rn "0.4.1" tests/` confirmed no other hardcoded assertion remains (residuals are
  prose/docstrings).
- The lint gate widening (`tk == "wiki_entity"` → `tk in ("wiki_entity", "wiki_concept")`)
  is purely additive — existing entity contradiction tests in `TestContradictionCheck`
  remain valid; the concept branch only adds coverage.
- `_install_success_routes` was NOT given a global PATCH side-effect, so existing
  PATCH-capture tests are not clobbered; reconcile tests scope their own `respx.patch()`.
- The replace-not-merge footgun — the single highest-risk correctness point — is guarded by
  a layered test set: (a) `never_drops` asserts the live user prop survives in the union;
  (b) the same test asserts SYSTEM_PROP_KEYS are absent from the payload; (c) pagination/shape
  abort tests assert NO PATCH on a truncated read; (d) the empty/None payload refusal lives
  in `update_type` itself. This is adequate test pressure on the corruption risk.

---

## Findings

### ADVISORY ADV-1 — Partial-failure assertion B is vacuously true pre-impl (real teeth only post-impl)
`test_reconcile_partial_failure_recovers_on_rerun` assertion B checks
`schema_version_stamped["value"] != "0.4.2"`. Pre-impl the marker is stamped `"0.4.1"`, so B
passes regardless of ordering; the test correctly fails on assertion A pre-impl. B only gains
teeth once the impl exists AND chooses to stamp `0.4.2`. This is acceptable (the test-writer
documented it, and B is the sole automated guard on the marker-after-loop invariant), but it
means **the ordering invariant is not actually exercised until impl lands**.
*Impact:* a buggy impl that stamps the marker before the loop is caught only if B remains a
positive check and the loop ordering is wired through the tracked collection/WikiLog PATCH
path (which the test does track, lines 2788–2796 — sound).
*Recommended action:* impl-reviewer (post-impl council) must re-confirm B fails when the
marker stamp is deliberately moved before the loop. No test change required now.

### ADVISORY ADV-2 — `"planned follow-up"` README assertion is broader than the AC requires
AC#3's mandated automatable check is `"not yet flagged" not in README`. The secondary
`test_readme_planned_followup_clause_removed` asserts `"planned follow-up"` is absent from the
*entire* README. Today that phrase appears exactly once (the target clause), so the test is
correct. But it constrains the impl never to use that common phrase elsewhere.
*Impact:* negligible now; a latent over-constraint.
*Recommended action:* none required. If impl needs the phrase elsewhere, scope the assertion
to the surfacing paragraph. Noted for impl awareness only.

### ADVISORY ADV-3 — AC#3 manual-review sub-criteria are not (and cannot be) automated
AC#3 has three prose sub-criteria beyond the README substring check: CHANGELOG 0.4.2 entry,
MIGRATIONS.md "re-bootstrap REQUIRED" note, and README "surfacing is live" statement. Only
the substring-absence check is automated; the rest are correctly a manual impl-review gate.
*Impact:* these can silently ship incomplete if the impl-reviewer skips them.
*Recommended action:* the post-impl review council MUST verify all three by inspection. Carry
forward explicitly into the impl-review checklist — do not assume the green README test covers
the docs AC.

### ADVISORY ADV-4 — Addendum items 7–8 (release/ops) carry no test coverage by design
Item 7 (lint gate §4 + reconcile §3 MUST ship in the same change; "re-bootstrap REQUIRED" in
the deploy runbook) and item 8 (durable capture of the SG-e union audit log) are not
pytest-testable. They are real release-gating requirements: shipping the lint gate without the
reconcile would strand existing spaces in an un-clearable `critical`.
*Impact:* if impl/release drops either, the migration footgun the ticket exists to avoid is
reintroduced — but at deploy time, invisible to this suite.
*Recommended action:* impl phase and release owner must honor 7–8. Flag to the council chair /
CPO that AC quality at release depends on these non-automated gates. The impl-reviewer must
confirm §3 and §4 land in the same commit/PR.

### ADVISORY ADV-5 — F-3 guard exception tuple remains broad; empty-properties test still has a permissive fallthrough
The None/missing-key guard tests were tightened to `pytest.raises((ValueError, AssertionError,
TypeError[, KeyError]))` (good). However `test_update_type_raises_on_empty_properties` retains
the older `except Exception: ... pass  # other exceptions accepted as guard` fallthrough
(test_bootstrap.py:2913–2920) — it only fails on HTTPStatusError/ConnectError. An accidental
`AttributeError`/`NotImplementedError` crash would still be accepted as a "guard raised" in
that one test.
*Impact:* low — the other two guard tests are tight, and all three pin the same behavior.
*Recommended action:* impl should settle `update_type` on a single refusal exception
(`ValueError` recommended) and, optionally, tighten this last test to match. Non-blocking.

---

## Sign-off statement

**As QA Director, I SIGN OFF on the test phase for #426 and approve advancement to impl.**

All three spec acceptance criteria and addendum items 1–6 are faithfully covered by genuine
fail-first / forward-regression guards; the 16 intended failures are all substantive
behavioral assertions verified by direct execution; no previously-passing test regressed; and
the replace-not-merge graph-corruption footgun — the one genuine risk in this deliverable — is
guarded from union-preservation, system-prop-exclusion, pagination-abort, and in-method
empty-payload-refusal angles. The five ADVISORY items are impl-phase carry-forwards (ordering
invariant re-confirmation, README assertion scope, manual docs sub-criteria, release-sequencing
items 7–8, and one permissive guard-test fallthrough); none gate the test→impl transition.

**Impl must be told:** (1) re-confirm partial-failure assertion B fails when the marker stamp
is moved before the loop (ADV-1); (2) complete and have the impl-reviewer inspect the three
manual AC#3 docs sub-criteria (ADV-3); (3) ship lint gate §4 and reconcile §3 in the same
change and honor the deploy-runbook / audit-log release items 7–8 (ADV-4).
