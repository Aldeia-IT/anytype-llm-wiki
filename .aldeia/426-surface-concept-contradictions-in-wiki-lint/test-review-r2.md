# Test Review: Surface concept contradictions in wiki_lint Round 2

**Verdict: APPROVED**

## Review Date
2026-06-25

## Scope

Focused re-review of the three findings from R1 (commit 879c95d, diff base e059d1a).
Only the changed lines are assessed; no new unrelated findings are introduced.

## F-1: BLOCKING — README substring-absence assertion (RESOLVED)

New file: `tests/wiki/test_docs_surfacing.py`

Path resolution at line 17 uses `Path(__file__).resolve().parents[2]`, which is portable:
`tests/wiki/test_docs_surfacing.py` is three levels inside the repo root
(`tests/wiki/ → tests/ → repo root`). No hardcoded `/Users/` path anywhere in the file.

Both tests were run directly:

```
uv run --extra dev pytest tests/wiki/test_docs_surfacing.py -q
```

Result: 2 failed. Both fail on the `AssertionError` at the substring check (not an IO error,
not a `FileNotFoundError`). The README is read successfully — the assertions fail because
`README.md` still contains `"not yet flagged"` (line 40) and `"planned follow-up"` (line 59).
The failure message in both cases includes the matched substring, confirming the assertion
fires on content, not on a path problem.

Post-impl, once the README is updated per spec §5, both assertions will flip to PASS. The
primary test (`test_readme_surfacing_gap_clause_removed`) directly satisfies the spec's
AC#3 automatable check (`"not yet flagged" not in README.read_text()`).

**F-1: RESOLVED.**

## F-2: SHOULD-FIX — System props excluded from reconcile PATCH payload (RESOLVED)

Addition in `tests/wiki/test_bootstrap.py` at lines 2499–2509, appended to
`TestReconcileNeverDropsExistingProperties::test_reconcile_never_drops_existing_properties`:

```python
system_keys_in_payload = union_keys & {"tag", "backlinks", "created_date", "creator", "links"}
assert not system_keys_in_payload, (...)
```

The assertion is correct and catches the specified regression:

- `union_keys` is computed from all PATCH payloads sent to `/types/` endpoints (lines 2484–2488),
  exactly the same set used by the existing union assertions.
- The intersection against the hardcoded five-element set (`"tag"`, `"backlinks"`,
  `"created_date"`, `"creator"`, `"links"`) matches the SYSTEM_PROP_KEYS spec definition
  from §1 and the existing `test_system_prop_keys_exact_membership` assertion.
- The assertion is `assert not system_keys_in_payload` — a non-empty intersection fails,
  empty intersection passes. Correct logic.
- The hardcoded set (rather than importing `SYSTEM_PROP_KEYS`) is a valid independent guard:
  if `SYSTEM_PROP_KEYS` were incorrectly modified in implementation, this test would still
  catch the original five system prop keys being sent.
- The assertion runs after the `wiki_last_reviewed` check (line 2495), so pre-impl the test
  still fails on the earlier `type_patch_payloads >= 1` assertion (line 2476). Post-impl, a
  buggy implementation that sends system props in the union will fail specifically on this
  new assertion.

**F-2: RESOLVED.**

## F-3: SHOULD-FIX — Tighter exception types in update_type guard tests (RESOLVED)

Both tests in `TestUpdateTypeGuard` now use `pytest.raises(...)` with specific exception tuples
instead of the broad `except Exception` fallthrough:

- `test_update_type_raises_on_none_properties` (line 2940):
  `with pytest.raises((ValueError, AssertionError, TypeError)):`
- `test_update_type_raises_on_missing_properties_key` (line 2960):
  `with pytest.raises((ValueError, AssertionError, TypeError, KeyError)):`

The `pytest.raises` context manager strictly requires one of the listed exceptions to be raised
within the block. Any other exception — including `AttributeError`, `NotImplementedError`,
or an accidental crash — propagates out of the `with` block as an unexpected exception and
causes the test to ERROR (not PASS). This is a genuine tightening: an accidental crash can no
longer masquerade as a valid guard.

The `pytest.skip()` guard (`if not hasattr(_wc.WikiClient, "update_type"): pytest.skip(...)`)
is preserved in both tests (lines 2936–2937 and 2956–2957), so both tests remain SKIPPED
pre-impl (not ERRORING). This matches the R1 requirement to preserve the pre-impl skip
behavior.

`KeyError` in the missing-key test is appropriate: a natural guard implementation may perform
a bare `type_def["properties"]` access, which raises `KeyError` on a dict without that key.

The exception tuple remains reasonably tight. `AttributeError` and `NotImplementedError` are
excluded — those would now cause an ERROR, not a silent PASS.

**F-3: RESOLVED.**

## Full Suite Regression Check

Expected (per fixer debrief): 16 failed, 711 passed, 39 skipped, 2 xfailed.

Actual run result:
```
16 failed, 711 passed, 39 skipped, 2 xfailed, 50 warnings in 5.65s
```

Matches exactly. The 16 failures are:

- 2 new README substring tests in `test_docs_surfacing.py` (F-1)
- 14 pre-existing failures in `test_bootstrap.py` (12) and `test_lint.py` (1),
  plus `test_update_type_raises_on_empty_properties` (already failing pre-fix)

No previously-passing test regressed.

## Summary

All three R1 findings are correctly resolved. F-1 (BLOCKING) is addressed by a new portable
test file that fails RED on the substring assertion (not on IO), correctly resolves the repo
root from `__file__`, and will flip GREEN once the README is updated. F-2 is resolved by a
correctly scoped set-intersection assertion that independently guards the exact five
SYSTEM_PROP_KEYS. F-3 is resolved by converting broad `except Exception` fallthrough to
`pytest.raises` with specific exception tuples, preserving pre-impl skip behavior. The full
suite baseline is unchanged at 711 passed.
