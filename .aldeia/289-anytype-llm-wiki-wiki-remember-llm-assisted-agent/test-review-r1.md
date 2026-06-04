# Test Review: wiki_remember (spec #289) — Round 1

**Verdict: NEEDS CHANGES**

**Date:** 2026-06-04
**Reviewer:** test-reviewer (sonnet), consolidated by dev-lead
**Scope:** commit `991af3e` — tests/wiki/{test_remember.py (new), test_extraction.py, test_bootstrap.py, test_ingest.py}

## Summary

The test suite is comprehensive and correctly structured: every test named in spec §10 is present, and every AC-R1–AC-R31, AC-R-S1/S2, AC-R12b, plus all 8 council-addendum items are traced to a named test. 75 new-surface tests fail for the correct reason (implementation absent); the designated regression guards pass. One BLOCKING finding: a MUST-PASS regression guard (`test_doctor_green_after_v031_bootstrap`) fails pre-impl for a test-bug reason rather than impl-absence. One SHOULD-FIX on the ambiguous-subject test's mock. One forward note for the impl phase.

## Observed pytest result

- Full `tests/wiki/` suite (`-m 'not live'`): 75 failed, 293 passed, 1 skipped, 3 deselected, 2 xfailed.
- New-surface failures verified to fail on `ModuleNotFoundError`/`ImportError`/`AttributeError` (impl absent) — correct TDD state — EXCEPT the one BLOCKING test below.
- Regression guards `test_write_wikilog_default_name_is_ingest`, `test_resolve_action_tag_default_is_ingest`, `test_extract_request_payload_unchanged_after_refactor` PASS against current source.

## Coverage

**§10.1 (test_extraction.py):** all 9 consolidate tests present (+2 acceptable extras: `test_consolidate_property_name_entity/_concept`).
**§10.2–§10.5 (test_remember.py):** all 37 named tests present.
**§10.6 (test_bootstrap.py):** all 9 present. **§10.6 ingest guards:** both present, PASS.
**§10.7:** `test_live_wiki_remember_end_to_end` present, `@pytest.mark.live`.

**Addendum items 1–8:** all honored by a named test:
- 1 → `test_supersede_recorded_in_wikilog_notes`
- 2 → `test_conflict_path_surfaces_sources_overwrite`
- 3 → `test_consent_banner_fires_on_live_path`, `test_space_lock_held_returns_ingest_in_progress`, `test_empty_knowledge_rejected_before_lock`, `test_oversize_knowledge_rejected_before_lock` (all drive the real entry point with mock-spies at the boundary)
- 4 → `test_consolidated_text_sanitized_on_write` (byte-for-byte `== sanitize_property_value(consolidated_text)`)
- 5 → `test_remember_twice_converges_no_op` (twice-driven, stateful mock, `update_calls == []` on call 2)
- 6 → `test_conflict_flag_when_patch_skipped`, `test_ambiguous_subject_skips_and_warns`
- 7 → `test_bootstrap_status_tags_seed_via_prop_map_keyfallback` (+ source_type sibling)
- 8 → `test_extract_request_payload_unchanged_after_refactor` (PASSES)

## Findings

### BLOCKING

**B-R1 — `test_doctor_green_after_v031_bootstrap` (test_bootstrap.py:~1951) fails pre-impl for a test-bug reason.**
This test is specified (AC-R23 / SF9 / addendum item 7) as a regression guard that MUST PASS against current source. It currently FAILS: its `known_check_names` whitelist omits `"ollama_models_pulled"` — a doctor check that exists in the CURRENT shipped `doctor.py` (`_check_ollama_models_pulled`, ~line 203), pre-dating #289. The mocked environment has no Ollama, so that pre-existing check reports FAIL, and because it is not in the whitelist the assertion wrongly classifies it as a "new #289 check." Reproduced:
`AssertionError: ... new FAIL checks not present before #289: ['ollama_models_pulled']`.
**Fix:** the robust resolution is to compare the set of FAILing doctor checks BEFORE vs AFTER the v0.3.1 bootstrap and assert no NEW name appears (the AC's actual intent — "no NEW ERROR-level check introduced by v0.3.1"), rather than asserting against a hand-maintained whitelist. A minimal alternative is to add `"ollama_models_pulled"` (and any other pre-existing checks) to `known_check_names`, but the before/after-set approach is preferred because it is robust to environment-dependent pre-existing failures.

### SHOULD-FIX

**S-R1 — `test_ambiguous_subject_skips_and_warns` (test_remember.py:~2204) cannot prove the co-resident unambiguous subject still writes.**
Addendum item 6 requires asserting that a co-resident UNAMBIGUOUS subject still writes while the ambiguous one is skipped. The test's `search_side_effect` returns two `AmbigEntity` rows for ALL searches regardless of the subject being resolved, so the impl would also see the unambiguous `ClearEntity` as ambiguous. The `not update_calls` assertion passes trivially if BOTH are skipped, leaving the "unambiguous subject still writes" requirement unproven.
**Fix:** make the search mock subject-aware — return the 2 same-name same-type rows ONLY for the ambiguous subject's name, and a single distinct row for the unambiguous subject — then assert the unambiguous subject produced exactly one write (its `update_object`/`create_object`) AND the ambiguous one produced none.

### Forward note (impl-phase handoff — do NOT change pre-impl)

**N-R1 — `test_bootstrap_action_tags_idempotent` (test_bootstrap.py:~1336) and `test_bootstrap_creates_all_five_action_tags` (~1290) encode the v0.3.0 count of 5 action tags.**
These pre-existing #284 tests currently PASS and MUST stay green pre-impl. Once the impl adds `"remember"` to `_WIKI_ACTION_TAGS` (6 tags), `test_bootstrap_action_tags_idempotent`'s `len(... ) == 5` assertion will break. This is an expected TDD consequence; the impl-worker must update these two assertions from 5→6 when adding the tag. It is NOT a defect in the current test commit and must not be "fixed" now (doing so would break the must-pass-pre-impl invariant).

## Test quality (passed)

- Assertions are substantive and AC-specific (byte-for-byte sanitize; `update_calls == []` hard equality; `assert_not_called()` spies on lock/extract/create for the entry gates).
- Hard-gate/input-validation tests mock-spy at the `wiki_remember` boundary, not isolated helpers (addendum item 3 satisfied).
- CI tests fully mocked (respx + monkeypatch); live tests marked `@pytest.mark.live`; `tmp_path` used (no hardcoded `/tmp` or `/Users` paths); test isolation clean.
