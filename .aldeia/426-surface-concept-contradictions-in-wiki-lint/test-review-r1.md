# Test Review: Surface concept contradictions in wiki_lint Round 1

**Verdict: NEEDS CHANGES**

## Review Date
2026-06-25

## 1. Spec Coverage

**PASSED — except one BLOCKING gap for AC#3.**

| Criterion | Tests | Status |
|-----------|-------|--------|
| AC#1: concept contradiction fires critical, cleared by wiki_last_reviewed | `test_concept_contradiction_unresolved` (fail-first, sub-a); `test_concept_contradiction_cleared_by_review` (sub-b); `test_concept_no_contradictions_no_finding` (sub-c) | PASSED |
| AC#2: bootstrap reconciles wiki_last_reviewed; types_reconciled entry; no double-skipped | `test_reconcile_adds_missing_property` (fail-first) | PASSED |
| AC#2: existing props not dropped (union, not delta) | `test_reconcile_never_drops_existing_properties` (fail-first) | PASSED |
| AC#2: no-op when all props present | `test_reconcile_no_op_when_complete` (forward guard) | PASSED |
| AC#2: types_reconciled in _empty_result on every run | `test_result_has_types_reconciled_key`; `test_types_reconciled_empty_on_fresh_space` | PASSED |
| **AC#3: README surfacing-gap clause removed (automatable check)** | **(none)** | **BLOCKING — see finding F-1** |
| Addendum item 1: WIKI_SCHEMA_VERSION pin updated to 0.4.2 | `test_wiki_schema_version_is_042` (renamed from 041) | PASSED |
| Addendum item 2: get_type mock mirrors live response shape | `_make_live_type_response()` helper used in all reconcile tests | PASSED |
| Addendum item 3: pagination-abort guard | `test_reconcile_pagination_abort_warns_no_patch`; `test_reconcile_missing_properties_key_aborts` | PASSED |
| Addendum item 4: partial failure leaves marker unstamped; re-run recovers | `test_reconcile_partial_failure_recovers_on_rerun` | PASSED |
| Addendum item 5: fail-first on meaningful assertion | Verified — see item 4 | PASSED |
| Addendum item 6: update_type refuses empty/None/missing properties | `test_update_type_raises_on_empty_properties` (fail-first); `*_none_properties` (skip); `*_missing_properties_key` (skip) | PASSED |
| Spec §1: SYSTEM_PROP_KEYS constant + exact membership | `test_system_prop_keys_exists`; `test_system_prop_keys_exact_membership` | PASSED |
| Spec §1: wiki_concept WIKI_TYPES has wiki_last_reviewed + format=date | `test_wiki_concept_schema_has_wiki_last_reviewed`; `test_wiki_concept_wiki_last_reviewed_has_date_format` | PASSED |
| Addendum items 7–8: operational/release items | None — correctly identified as non-pytest | PASSED |

### BLOCKING finding F-1: AC#3 README substring-absence assertion is missing

`tests/wiki/test_lint.py` and `tests/wiki/test_bootstrap.py` — no file, no line (assertion absent).

The spec's AC#3 explicitly requires "one automatable check": a `substring-absence assertion
("not yet flagged" not in README.read_text())`. The current README (`README.md:175`) still
contains the clause `"not yet flagged by wiki_lint — a planned follow-up"`. This assertion
would fail red pre-impl and pass post-impl when docs land — it is a legitimate fail-first test.

The test-writer's justification ("the implementation hasn't shipped the docs change yet") would
invalidate every other test in this suite by the same logic. The project already has precedent
for static README assertions in `tests/test_ci_config.py` (lines 31, 52, 186–190).

**Required fix:** add a test to `tests/wiki/test_lint.py` (or `tests/test_ci_config.py`) of the form:

```python
def test_readme_concept_contradiction_surfacing_clause_removed():
    """AC#426-3: README must not contain the surfacing-gap clause from #325.
    
    FAILS until README.md removes the 'not yet flagged by wiki_lint' sentence
    and replaces it with a statement that concept contradiction surfacing is live.
    """
    from pathlib import Path
    readme = (Path(__file__).resolve().parents[2] / "README.md").read_text(encoding="utf-8")
    assert "not yet flagged by" not in readme, (
        "AC#426-3: README must remove the surfacing-gap clause from #325; "
        "found 'not yet flagged by' in README.md. "
        "FAILS until README.md is updated per spec §5."
    )
```

The exact parent-path depth depends on where the test is placed. In `test_lint.py`
(`tests/wiki/test_lint.py`) use `parents[2]`; in `test_ci_config.py` (`tests/test_ci_config.py`)
use `parents[1]` (or use the existing `REPO_ROOT` and `README_MD` constants already defined there).

This is the **only BLOCKING finding**. All other criteria are covered.

## 2. Edge Case Coverage

**PASSED — with one SHOULD-FIX observation.**

The following edge cases are covered:
- No `wiki_contradictions` prop at all (concept clean — `test_concept_no_contradictions_no_finding`).
- `wiki_last_reviewed` set clears the finding (`test_concept_contradiction_cleared_by_review`).
- `get_type` returns `pagination.has_more=True` (synthetic abort — `test_reconcile_pagination_abort_warns_no_patch`).
- `get_type` returns no `properties` key (synthetic abort — `test_reconcile_missing_properties_key_aborts`).
- Existing user props preserved in union (`test_reconcile_never_drops_existing_properties`).
- No-op when fully reconciled (`test_reconcile_no_op_when_complete`).
- `update_type` called with `{"properties": []}`, `None`, or missing key (three guard tests).
- Mid-loop failure on the 2nd type (`test_reconcile_partial_failure_recovers_on_rerun`).

**SHOULD-FIX — F-2:** `test_reconcile_never_drops_existing_properties` asserts that
`wiki_custom_user_prop` and `wiki_last_reviewed` appear in the PATCH payload but does
NOT assert that `tag` and `backlinks` (system props echoed in the live response) are
**absent** from the payload. If the impl sends system props in the union, this test would
not catch it. The `SYSTEM_PROP_KEYS` membership test pins the constant, but no test
verifies the constant is actually respected during the union-building step.

Location: `tests/wiki/test_bootstrap.py`, `TestReconcileNeverDropsExistingProperties`.

Suggested addition after `assert "wiki_last_reviewed" in union_keys`:

```python
system_keys_in_payload = union_keys & {"tag", "backlinks", "created_date", "creator", "links"}
assert not system_keys_in_payload, (
    f"AC#426-2 regression: system props must NOT appear in update_type payload "
    f"(Anytype auto-re-adds them); found: {system_keys_in_payload}"
)
```

## 3. Assertion Correctness

**PASSED.**

All checked assertions match the spec:

- `check == "contradiction_unresolved"` and `severity == "critical"` — correct per `lint.py:500`
  and spec §4.
- `properties_added == ["wiki_last_reviewed"]` — sorted list, matches spec AC#2.
- `wiki_concept not in types_skipped` when in `types_reconciled` — correct per spec §3
  (the no-missing branch moves the record, not both lists).
- `len(concept_reconciled) == 1` — exact count, not partial match.
- `WIKI_SCHEMA_VERSION == "0.4.2"` — positive pin, correct.
- `SYSTEM_PROP_KEYS == {"tag", "backlinks", "created_date", "creator", "links"}` — exact set,
  matches spec §1.
- `"properties" not in live_type` and `pag.get("has_more") is True` abort conditions — both
  covered by dedicated test cases, assertions check `warnings[]` and `types_skipped` correctly.

The `wiki_contradictions` object format uses bare string list (`["contra-id-1"]`) with
`"objects"` key, which matches the entity test pattern and mem0 reference 56845bac. Correct.

## 4. Test Validity (will they fail now?)

**PASSED — all 14 failing tests fail on substantive behavioral assertions.**

Verified by running the three named fail-first tests:

1. **`test_concept_contradiction_unresolved`** (`tests/wiki/test_lint.py:1327`):
   `assert 0 == 1` — `len(contra_findings_a) == 1` fails because the entity-only gate at
   `lint.py:490` produces zero concept findings. Not an ImportError or AttributeError.

2. **`test_reconcile_adds_missing_property`** (`tests/wiki/test_bootstrap.py`):
   `assert 0 == 1` — `len(concept_reconciled) == 1` fails because bootstrap has no reconcile
   loop and `types_reconciled` is absent from the result. Substantive count assertion.

3. **`test_reconcile_never_drops_existing_properties`** (`tests/wiki/test_bootstrap.py:2476`):
   `assert 0 >= 1` — no PATCH to `/types/` path was made. The assertion message confirms no
   union-send logic exists yet. Substantive behavioral assertion.

The three named tests from addendum item 5 all fail on value/count assertions, not on
`ImportError`/`AttributeError`/`KeyError`. Confirmed.

The 11 other failures also fail on substantive assertions (version mismatch, missing dict
keys, `hasattr` failure for `update_type`, `warnings[]` length checks, etc.) — none fail
vacuously.

Full suite baseline (pre-impl): `14 failed, 711 passed, 39 skipped, 2 xfailed`. No
pre-existing test was broken by the new test additions.

## 5. Convention Compliance

**PASSED — Python/pytest conventions.**

The project uses pytest/respx (not bash). Applicable conventions checked:

- `@respx.mock` decorator used consistently on all HTTP-mocking tests. No bare context
  managers that could leak state.
- `respx.get().mock(side_effect=...)` and `respx.patch().mock(side_effect=...)` — correct
  no-arg form. No `respx.patterns.M` anti-pattern found in any new or existing test.
- Route ordering in every GET handler: `if "/types/" in path` appears **before**
  `if path.endswith("/types")`, satisfying SF-1. Verified in all five reconcile tests
  that install a custom GET handler.
- PATCH route isolation: `_install_success_routes` is not modified. Reconcile tests install
  their own `respx.patch().mock()` scoped to each test, avoiding clobber of existing
  PATCH-capture tests.
- No hardcoded `/Users/` paths in any new test code.
- `monkeypatch.setenv()` used for all environment variable injection.
- `pytest.skip()` used (not bare `return`) in guard tests when `update_type` is absent.
- `_make_live_type_response()` helper mirrors the verified `get_type` response shape from
  `research.md §1b`: `{"type": {"object","id","key","properties":[{object,id,key,name,format},...]}}`
  with NO `pagination` key. System props (`tag`, `backlinks`) included in the helper's output.

**SHOULD-FIX — F-3 (minor):** The exception catch in `test_update_type_raises_on_none_properties`
and `test_update_type_raises_on_missing_properties_key` (`tests/wiki/test_bootstrap.py`,
`TestUpdateTypeGuard`) uses a broad `except Exception` with a check on the exception class
name string:

```python
if "HTTPStatusError" in type(exc).__name__ or "ConnectError" in type(exc).__name__:
    pytest.fail(...)
pass  # other guard exceptions accepted
```

This accepts any non-HTTP exception including `AttributeError`, `NotImplementedError`,
or any accidental crash as a valid "guard raised". A buggy impl that crashes for an
unrelated reason would pass these tests. Prefer restricting to `(ValueError, AssertionError,
TypeError)` in the outer `except` to match the named-exception clause above it.

## 6. Test Isolation

**PASSED.**

Each test is independently runnable:

- Every test installs its own respx mocks inside the `@respx.mock` context.
- Local sentinel variables (`patch_payloads`, `type_patch_calls`, `schema_version_stamped`,
  `raised_exc`, `result_failing_holder`) are defined inside each test body — no shared
  mutable state between tests.
- The partial failure test (`test_reconcile_partial_failure_recovers_on_rerun`) re-uses a
  single `@respx.mock` scope for both the failing and clean re-run calls. This is
  intentional and correct: the GET mock persists, and `respx.patch().mock()` is re-called
  mid-test to replace the PATCH handler for the re-run. The re-mock pattern is consistent
  with how `respx.mock` contexts work (route replacement, not stacking).
- No tests depend on machine state (running services, specific users, or home directory).
- No tests depend on execution order.

## 7. Existing Test Impact

**PASSED — one existing test already updated; no others impacted.**

The only existing test materially affected by this spec is:

| Test file:name | Change made | Status |
|---------------|-------------|--------|
| `tests/wiki/test_bootstrap.py::TestSchemaVersionBumped::test_wiki_schema_version_is_041` | Renamed to `test_wiki_schema_version_is_042`; version pin updated `"0.4.1"` → `"0.4.2"`; docstring updated | UPDATED correctly by test-writer |

All other version comparisons in the suite use the dynamic `_ts.WIKI_SCHEMA_VERSION` symbol
(e.g. `test_bootstrap.py:711`) — they do not hardcode the version string and will remain
correct after the bump.

The `grep -rn "0.4.1" tests/` check confirms no remaining hardcoded `0.4.1` assertion. The
three remaining occurrences are prose/docstring comments (lines 857, 867 in test_bootstrap.py;
line 2096 in test_lint.py) — none are assertions.

The lint gate change (`tk == "wiki_entity"` → `tk in ("wiki_entity", "wiki_concept")`) does
not invalidate any existing entity test. The entity contradiction tests in `TestContradictionCheck`
remain correct because the widened gate only adds the concept branch — it does not change
entity behavior.

The existing `test_result_has_required_keys` (`tests/wiki/test_bootstrap.py:144`) does not
include `types_reconciled` in its required-keys list. Post-impl, `types_reconciled` will be
present in the result but this test does not check for it (not a breakage — it checks a
subset, and new tests cover `types_reconciled` specifically).

## Summary

The test suite is well-structured, correctly mocked, and the 14 intentional failures are
all substantive behavioral assertions. One BLOCKING gap exists: AC#3's automatable check
(README substring-absence assertion for the surfacing-gap clause) was omitted with
incorrect justification. Two SHOULD-FIX items are flagged: the `test_reconcile_never_drops_existing_properties`
test does not assert that system props are excluded from the PATCH payload, and the guard
tests for `None`/missing-key `properties` accept overly broad exception types. The README
assertion must be added before advancing to impl; the SHOULD-FIX items can be addressed
alongside it.
