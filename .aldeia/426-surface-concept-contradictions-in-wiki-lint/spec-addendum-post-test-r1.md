# Spec Addendum — post-test council (R1)

**Source:** [`council-test-r1.md`](council-test-r1.md)
**Date:** 2026-06-25
**Target phase:** impl
**Status:** Authoritative — the impl phase MUST honor these items as spec requirements.

These items supplement (do not replace) the still-authoritative `spec-addendum-post-spec-r1.md`
items 7–8. The test phase satisfied addendum items 1–6; items 7–8 and the additions below are
impl/release obligations.

## Additional acceptance criteria for the impl phase

1. **[CTO-A1/QA-ADV-1/Infra] Verify the marker-ordering invariant guard has teeth post-impl.**
   `test_reconcile_partial_failure_recovers_on_rerun` assertion B (schema-version marker NOT
   stamped to `0.4.2` after a mid-loop `update_type` failure) is the SOLE automated guard on
   the marker-after-loop ordering invariant, and it passes vacuously pre-impl. After
   implementing the reconcile, the impl phase MUST confirm this assertion actually fails if the
   schema-version stamp is moved before the reconcile loop (e.g. by a deliberate local
   perturbation during review), and MUST keep the stamp strictly AFTER the loop completes
   (`bootstrap.py` stamps at `:419`/`:446`; reconcile lands in the existing-types branch at
   `:281-285`).

2. **[QA-ADV-3/CPO-ADV-1/CTO-A3] Complete the AC#3 prose docs (manual-review gates).** Beyond
   the automatable README substring-absence test, the impl MUST: (a) add a CHANGELOG.md entry
   for the 0.4.2 schema bump and concept-contradiction surfacing-is-live; (b) add the
   MIGRATIONS.md note (see item 3); (c) replace the README surfacing-gap clause with a positive
   "concept-contradiction surfacing is live" statement so the automatable test flips green. The
   post-impl council will verify (a)–(c) by inspection.

3. **[Infra-3/CPO-ADV-2] Migration sequencing + deploy runbook (sharpens spec-addendum item 7).**
   - The repo currently has NO operational deploy runbook (`docs/releasing.md` is PyPI-publish
     only). MIGRATIONS.md alone does NOT satisfy spec-addendum item 7's "deploy runbook"
     requirement. The impl MUST create or extend an operational runbook stating that re-running
     `wiki_bootstrap` is REQUIRED (not optional) for every existing space.
   - The MIGRATIONS.md 0.4.2 note belongs in the "Unreleased" section (`MIGRATIONS.md:89`) and
     MUST explicitly warn that running the new `wiki_lint` before re-bootstrapping yields an
     un-clearable `critical`. Follow the v0.3.0 section precedent (`MIGRATIONS.md:60-75`).
   - The lint gate (§4) and bootstrap reconcile (§3) MUST ship in the same change (reaffirms
     spec-addendum item 7) — shipping the gate without reconcile reintroduces the un-clearable
     `critical` footgun.

4. **[CTO-A4/QA-ADV-5] Settle `update_type` payload-refusal on a single exception type.**
   Implement the empty/`None`-`properties` refusal (spec-addendum item 6) raising a single,
   specific exception (suggest `ValueError`), and tighten the corresponding guard-test
   assertions away from the broad `except Exception` fallthrough / wide exception tuple now in
   place. Non-blocking but expected at impl.

5. **[CSO-3/Infra] Durable audit log (reaffirms spec-addendum item 8).** Ensure the SG-e
   INFO-level union audit log emitted before each destructive `update_type` PATCH is durably
   captured by the deployment so a corruption event is reconstructable post-hoc. Confirm at
   impl-phase code review.

## Rationale

All five items are ADVISORY (zero BLOCKING) — the council reached unanimous SIGN-OFF. They are
recorded here because Task Intake reads spec addenda as authoritative, whereas free-text council
comments are easily missed by the next lead. Item 1 protects the single guard on the
graph-corruption-recovery ordering invariant from silently rotting. Item 2 ensures the
user-facing closure signal (which for this ticket lives substantially in docs) actually lands.
Item 3 closes a concrete operational gap the test phase could not test — the absence of a deploy
runbook — and prevents stranding an existing space in an un-clearable `critical`. Items 4–5
harden the destructive-PATCH path at its source and keep a corruption event diagnosable.
