# Spec Addendum — post-spec council (R1)

**Source:** [`council-spec-r1.md`](council-spec-r1.md)
**Date:** 2026-06-25
**Target phase:** test (then impl)
**Status:** Authoritative — the test and impl phases MUST honor these items as spec requirements.

## Additional acceptance criteria for the test/impl phase

1. **[QA-1 — spec factual error, verified by chair] Update the `0.4.1` version pin.**
   `tests/wiki/test_bootstrap.py:855-870` (`test_wiki_schema_version_is_041`) hard-asserts
   `WIKI_SCHEMA_VERSION == "0.4.1"`. The spec's Test Plan (`spec.md:494-497`) and
   `review-r1.md:97` are WRONG to claim no such pin exists and to instruct the test-writer not to
   edit one. The §1 bump to `0.4.2` will deterministically break this test. The test-phase worker
   MUST update this assertion (and its docstring/`AC-R11`/`D11` references) to the new version, and
   MUST run `grep -rn "0.4.1" tests/` to confirm no other hardcoded pin remains. Do not rely on the
   spec's stale "non-existent pin" instruction.

2. **[CSO-1/CTO-A1/Infra-A1/QA-A2] `get_type` read-side live probe (BL-6.4) is a hard entry
   condition for shipping the reconcile.** Before the §3 reconcile PATCH is enabled, issue a raw
   `GET /v1/spaces/{id}/types/{type_id}` against a bootstrapped type in the
   `wiki-validation-throwaway` space and record in `research.md`: (a) the exact per-property field
   set (does each entry carry `key`/`property_key`, `name`, `format`?); (b) whether `properties[]`
   is ever paginated (`pagination.has_more`) and its completeness/nested-pagination behavior. At
   least one `test_reconcile_*` mock MUST mirror the actual observed response shape — the three
   safety guards must be tested against the real contract, not a fictional one.

3. **[CSO-2/QA-A2] Add an explicit pagination-abort test.** Add a `test_reconcile_*` case where
   `get_type` returns `pagination.has_more is True` (or no `properties` key) and assert the reconcile
   ABORTS that type with a `warnings[]` entry and issues NO `update_type` PATCH. This is the sole
   destructive-path defense against the unverified read contract and currently has no dedicated test.

4. **[CTO-A3/QA-A3/Infra-A3] Strengthen the partial-failure recovery test.**
   `test_reconcile_partial_failure_recovers_on_rerun` MUST assert the schema-version marker is
   UNSTAMPED after the failing run (not merely that a clean re-run recovers). It is the sole
   automated guard on the marker-after-loop ordering invariant; treat it as a pre-merge gate.

5. **[QA-A4] Fail-first tests must fail on a meaningful assertion.** Confirm the three fail-first
   tests (`test_concept_contradiction_unresolved`, `test_reconcile_adds_missing_property`,
   `test_reconcile_never_drops_existing_properties`) go RED on a substantive assertion against the
   new behavior — not merely on an `ImportError`/`KeyError` from a not-yet-defined symbol.

6. **[CTO-A2] Pin the empty/None `properties` payload refusal inside `update_type` itself.** Place
   the guard in `update_type` (raise/abort on empty or `None` `properties`), not only in the §3
   caller, so a destructive `{"properties": []}` PATCH can never be issued regardless of call site.

7. **[CPO-1/Infra-A2] Migration sequencing enforced at release.** The lint gate (§4) and bootstrap
   reconcile (§3) MUST ship in the same change. "Re-running `wiki_bootstrap` is REQUIRED for existing
   spaces" must appear in the deploy runbook in addition to MIGRATIONS.md, so no operator hits an
   un-clearable `critical`. (Operational/release item — for the impl phase and release owner.)

8. **[CSO-3] Durable audit log.** Ensure the SG-e INFO-level union audit log emitted before each
   destructive `update_type` PATCH is durably captured by the deployment so a corruption event can
   be reconstructed post-hoc. (Operational item — for the impl phase.)

## Rationale

Items 1–6 are test-phase acceptance criteria. Item 1 is a verified factual error in the spec's own
test instructions: left unaddressed, the version bump breaks `test_wiki_schema_version_is_041` and a
reader following the spec literally would not fix it. Items 2–5 close the empirical and coverage gap
around the one genuine risk in the deliverable — the replace-not-merge graph-corruption footgun whose
read-side contract (`get_type`) is not yet empirically verified; the council accepted the spec's
"safe-by-construction" disposition only on the condition that the live probe and the
pagination/recovery tests land. Item 6 hardens the destructive-PATCH guard at its source. Items 7–8
are operational/release requirements ensuring the migration cannot strand an existing space in an
un-clearable `critical` state and that a corruption event remains diagnosable. All eight are
advisories (zero BLOCKING); they are recorded here because Task Intake reads spec addenda as
authoritative, whereas free-text council comments are easily missed by the next lead.
