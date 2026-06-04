APPROVED

# Test Review: wiki_remember (spec #289) — Round 2

**Verdict: APPROVED**

**Date:** 2026-06-04
**Reviewer:** test-reviewer (sonnet-4-6)
**Scope:** focused re-review of fix commit `2357b4a` — two R1 findings (B-R1, S-R1)

## Summary

Both R1 findings are fully resolved. B-R1's whitelist approach has been correctly replaced with a before/after FAIL-set diff (`after_fail_names - before_fail_names == set()`), and the test now passes against current source. S-R1's search mock is now subject-aware with separate capture lists and a substantive `len(clear_update_calls) == 1` assertion that proves the co-resident unambiguous subject writes. No regressions observed; the full suite count is stable at 74 failed / 294 passed (all failures are impl-absence).

## B-R1 Resolution: RESOLVED

**Finding:** `test_doctor_green_after_v031_bootstrap` was failing pre-impl because its hand-maintained whitelist omitted `"ollama_models_pulled"`.

**Fix applied:** The whitelist has been entirely replaced with a two-call before/after approach. `run_doctor()` is called twice in the same mocked environment. `before_fail_names` captures the set of currently-FAILing checks; `after_fail_names` does the same for the second call; the assertion is `after_fail_names - before_fail_names == set()`. Since both calls execute in an identical mocked environment (no state changes between them pre-impl), the set difference is always empty — correctly asserting that no NEW check was introduced. This is substantive, not a tautology: once the impl adds a new doctor check that fails under the mock environment, it will appear in `after_fail_names` but not `before_fail_names` and the test will fail.

**Verification:** `uv run --extra dev python -m pytest -q -m 'not live' -k 'test_doctor_green_after_v031_bootstrap ...'` → **4 passed** (all four regression guards pass).

## S-R1 Resolution: RESOLVED

**Finding:** The search mock returned 2 ambiguous rows for ALL subjects, making the "unambiguous subject still writes" assertion trivially passable if both subjects were skipped.

**Fix applied:** The `search_side_effect` function is now subject-aware: it inspects the request body (POST `{"query": ...}`) and URL query params (GET `?query=...`) for the subject name, returning 2 same-name same-type rows for `"AmbigEntity"` and exactly 1 distinct row (`clear-001`) for `"ClearEntity"`. The consolidate mock is set to `changed=True` so a PATCH is expected. Two separate capture lists (`ambig_update_calls`, `clear_update_calls`) track writes per-subject. The test asserts:
- `not ambig_update_calls` — the ambiguous subject produces no writes
- `len(clear_update_calls) == 1` — the unambiguous subject produces exactly one write

Both assertions are substantive and independently falsifiable.

**Verification:** `test_ambiguous_subject_skips_and_warns` fails with `ImportError: import error in anytype_llm_wiki.wiki.remember: No module named 'anytype_llm_wiki.wiki.remember'` — correct TDD state (impl absent).

## pytest Counts Observed

- **4 regression guards** (`test_doctor_green_after_v031_bootstrap`, `test_write_wikilog_default_name_is_ingest`, `test_resolve_action_tag_default_is_ingest`, `test_extract_request_payload_unchanged_after_refactor`): **4 passed**.
- **Forward-note tests** (`test_bootstrap_action_tags_idempotent`, `test_bootstrap_creates_all_five_action_tags`): **2 passed** (not modified, still green pre-impl).
- **Full suite** (`-m 'not live'`): **74 failed, 294 passed, 1 skipped, 3 deselected, 2 xfailed** — all 74 failures are `ModuleNotFoundError`/`ImportError`/`AttributeError` (impl absent). Count is +1 passed vs R1 (293→294), consistent with `test_doctor_green_after_v031_bootstrap` moving from FAIL to PASS; failed count unchanged at 74.

## New Findings

None. No new BLOCKING or SHOULD-FIX items identified.
