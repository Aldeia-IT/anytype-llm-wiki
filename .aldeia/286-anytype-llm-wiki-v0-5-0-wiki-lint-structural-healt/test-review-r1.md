# Test Review: wiki_lint v0.5.0 Round 1

**Verdict: NEEDS CHANGES**

## Review Date
2026-06-05

---

## 1. Spec Coverage

### Traceability matrix completeness

All 33 Test Plan rows from the spec are present in the file. The traceability matrix in the debrief correctly maps each AC to one or more tests. Coverage table follows at the end of this document.

### Per-AC assessment

**AC1 (D1 backlinks primary):** Three tests cover this. `test_asymmetric_relation_check_fires` seeds `backlinks=[]` to force the fallback. `test_backlinks_primary_no_traversal` seeds both sides with populated backlinks and asserts no asymmetric finding fires. `test_backlinks_malformed_falls_back` verifies graceful handling of non-list values.

**AC2 (stale_needs_review replaces stale_stub):** `test_stale_needs_review_fires` and `test_stale_stub_check_never_emitted` cover both halves. PASSED with one concern noted under Finding B1 below.

**AC3 (unreviewed_needs_review, High):** `test_unreviewed_needs_review_fires` covers this. BLOCKED — see Finding B1.

**AC4 (double-count rule):** `test_both_needs_review_checks_fire_on_aged_object` asserts both findings and both summary counts. BLOCKED — see Finding B1.

**AC5 (all 10 check types):** Ten dedicated tests, one per check. The duplicate sweep test (`test_duplicate_sweep_fires_when_opted_in`) covers `potential_duplicate` when opted in. PASSED on mapping; has the monkeypatch concern noted under Finding B2.

**AC6 (contradiction passive):** `test_contradiction_check_passive` verifies both the passive (pipeline) fixture and the active (manually populated) path. PASSED.

**AC7 (severity filtering):** Two filtering tests plus `test_duplicate_sweep_runs_regardless_of_threshold` cover all three branches. PASSED.

**AC8 (duplicate band + dedup):** Three dedicated tests. PASSED for band math and dedup; has the monkeypatch concern from Finding B2.

**AC9 (QA#25 three branches):** Three tests cover `wiki_schema_outdated`, `wiki_schema_missing`, and `wiki_schema_newer`. The newer-warns-and-continues test has a fragility issue noted in Finding S1.

**AC10 (QA#30 fires before write):** Two tests cover this. `test_pre_check_patch_decision_missing_fires_before_write` asserts zero GET and POST calls on QA#30 failure. PASSED.

**AC11 (WikiLog receipt + status lifecycle):** Three tests: clean run, partial run, skip on failure. PASSED.

**AC12 (budget warning + sweep cap):** Two tests. PASSED.

**AC13 (tag resolution two-step):** `test_tag_resolution_never_calls_space_level_tags` correctly registers a specific route for the space-level `/tags` endpoint and asserts `.called is False`. PASSED.

**AC14 (CLI + server registration):** `test_wiki_lint_registered_and_cli_routed` covers both CLI and server. Currently tests against not-yet-modified files (cli.py, server.py) — this is correct pre-impl behavior, the test will fail until implementation is done. PASSED structurally.

**AC15 (live smoke):** `TestLintLive` with two skip-gated tests. PASSED.

**AC16 (sweep opt-in, default off):** Three tests cover the CA-B1 requirement. PASSED structurally; has monkeypatch concern from Finding B2.

---

## 2. Edge Case Coverage

Edge cases present:
- Empty backlinks list vs absent backlinks vs non-list backlinks (three separate cases)
- Object with no `wiki_status` property is handled by the `G4` rule (treated as not-needs-review); this is covered implicitly by entities without `wiki_status` in most fixtures
- Self-match in duplicate sweep
- Reciprocal pair deduplication
- Object count at exactly 501 (just over budget)
- `WIKI_LINT_MAX_OBJECTS` overridden to 3 for sweep-cap test
- `_bounded_float` accepts valid values and rejects out-of-range and non-numeric

Missing but minor:
- No explicit test for an object with `wiki_sources=[]` (empty, not absent) in an age-based check — the spec says "An object with no resolvable source timestamp is treated as ungated." Not blocking since the grace-period tests do cover the non-empty path.

PASSED (no MAJOR gaps).

---

## 3. Assertion Correctness

Most assertions are correct. Two BLOCKING defects found:

**Finding B1 (BLOCKING) — `wiki_status` tag id mismatch makes all `needs-review` check tests unsatisfiable against a spec-faithful id-comparing implementation**

- File: `tests/wiki/test_lint.py`, lines 138, 173
- Affected tests: `test_unreviewed_needs_review_fires`, `test_stale_needs_review_fires`, `test_both_needs_review_checks_fire_on_aged_object`, `test_stale_stub_check_never_emitted`
- What's wrong: `_make_entity` and `_make_concept` produce `"wiki_status"` select properties with `id=f"tag-{wiki_status}"` (e.g., `"tag-needs-review"`). `_make_tags_response` returns a needs-review tag with `id="tag-needs-review-id"`. These two ids do NOT match.
- Why it fails: The spec says "Resolve once at the start of the lint run via the property-scoped two-step... storing the resolved `needs-review` tag id." This directs lint to call `_resolve_select_tag(client, space_id, "wiki_status", "needs-review")` which returns the id from the tag list — `"tag-needs-review-id"`. A spec-faithful implementation then checks `obj_select_id == resolved_tag_id` per object. Because `"tag-needs-review" != "tag-needs-review-id"`, no `unreviewed_needs_review` or `stale_needs_review` findings fire. Tests that assert `len(unreviewed) >= 1` fail. Tests that assert `len(stale_nr) >= 1` fail. `test_stale_stub_check_never_emitted` would pass vacuously (no stale_stub findings, but also no unreviewed findings — the test happens to pass for the wrong reason).
- Fix: Align the ids across both helpers. Either change line 138 (and 173) to `"id": f"tag-{wiki_status}-id"` to match `_make_tags_response`, OR change `_make_tags_response` to use `"id": f"tag-{tag['name']}"` for all tags. The simpler fix is to update `_make_entity` and `_make_concept`:
  - Line 138: `{"key": "wiki_status", "select": {"name": wiki_status, "id": f"tag-{wiki_status}-id"}}`
  - Line 173: same change
  - OR align the tag response to use `"id": "tag-needs-review"` (removing the `-id` suffix throughout `_make_tags_response`).
- Note: If the implementer chooses name-based comparison (`select["name"] == "needs-review"`) rather than id-based, the tests would pass as written. However, the spec explicitly states the purpose is to "avoid per-object resolution overhead" by resolving the id once — which implies id-based comparison. The test file must be correct against the spec-described behavior, not a shortcut implementation.

**Finding S1 (SHOULD-FIX) — `test_pre_check_schema_newer_warns_and_continues` uses a position-ordered GET iterator, which breaks if the implementation makes GET calls in a different order or count**

- File: `tests/wiki/test_lint.py`, lines 1646–1658
- What's wrong: The test builds a fixed-length iterator of GET responses: `[schema_newer, empty_list, properties, tags, search_response]`. The fifth entry is `_make_search_response([])` which is structurally identical to `_empty_list_response()` so it's harmless. The real issue is that the iterator is order-sensitive. If the implementation makes a properties GET before the second list_objects GET (e.g., for tag resolution before or during object enumeration), responses 2 and 3 swap, and the properties call gets an empty list response instead of a properties response — potentially breaking tag resolution.
- Why it matters: The spec states tag resolution runs after enumeration. If the implementation strictly follows spec order, this test works. But the test is fragile against any reordering and doesn't use URL-dispatched routing (unlike `_standard_mocks`). A URL-dispatched approach (like `_standard_mocks` but with a different initial response for list_objects) would be resilient.
- Fix: Rewrite this test to use a URL-dispatched side_effect (similar to `_standard_mocks`) where the newer-schema response is returned for the first `/objects` call, subsequent `/objects` calls return empty, and `/properties` + `/tags` calls return their normal responses regardless of call order.

---

## 4. Test Validity (will they fail now and pass post-impl?)

All CI tests currently fail with `ModuleNotFoundError` on `anytype_llm_wiki.wiki.lint` — this is the expected pre-impl state.

Post-impl analysis:

**Finding B2 (BLOCKING) — Duplicate sweep monkeypatch uses `try/except (ImportError, AttributeError): pass` that silently swallows both patch attempts pre-impl, providing no protection against the wrong patch target post-impl**

- File: `tests/wiki/test_lint.py`, lines 1147–1158, 1199–1209, 1252–1263, 1306–1317, 1383–1393, 1444–1451
- Affected tests: `test_duplicate_sweep_fires_when_opted_in`, `test_duplicate_sweep_excludes_outside_band`, `test_duplicate_sweep_self_match_and_pair_dedup`, `test_duplicate_sweep_off_by_default`, `test_duplicate_sweep_runs_regardless_of_threshold`, `test_duplicate_sweep_skipped_over_object_cap`
- What's wrong: All six duplicate sweep tests use the same dual-patch pattern with silent exception swallowing:
  ```python
  try:
      import anytype_llm_wiki.indexer as _idx_mod
      monkeypatch.setattr(_idx_mod, "semantic_search_core", fake_ssc)
  except (ImportError, AttributeError):
      pass
  try:
      import anytype_llm_wiki.wiki.lint as _lint_mod
      monkeypatch.setattr(_lint_mod, "semantic_search_core", fake_ssc, raising=False)
  except (ImportError, AttributeError):
      pass
  ```
  The first `try` block succeeds (indexer.py exists) and patches `indexer.semantic_search_core`. The second `try` block raises `ModuleNotFoundError` pre-impl and is silently caught.
- The concern: The established convention in `query.py` is `from .. import indexer` + `indexer.semantic_search_core(...)`, and `test_query.py` patches at `_idx_mod.semantic_search_core`. If `lint.py` follows the same convention (which the spec intends — the reuse map points to `indexer.py:20` with module-qualified reference), the `_idx_mod` patch is sufficient and correct. However, the silent `except: pass` pattern means:
  1. If lint deviates from convention and uses a direct `from anytype_llm_wiki.indexer import semantic_search_core` (binding at import time), the `_idx_mod` patch is a no-op and the fake is never invoked. Tests that assert `ssc_called` would then fail for the wrong reason (real Qdrant called, raises), not the expected testing reason.
  2. More importantly, for `test_duplicate_sweep_off_by_default`, if the `_idx_mod` patch silently fails (wrong target), the test would still pass vacuously because lint won't call `semantic_search_core` when `include_duplicates=False` — making the test false-green against an impl that always calls the sweep.
- Recommended fix: Follow the `test_query.py` convention exactly. Remove the dual-try pattern and use a single authoritative patch path. Since the spec says "monkeypatch at function boundary" and `query.py` establishes `import indexer; indexer.semantic_search_core(...)` as the convention, the lint-module patch is unnecessary. Use:
  ```python
  import anytype_llm_wiki.indexer as _idx_mod
  monkeypatch.setattr(_idx_mod, "semantic_search_core", fake_ssc)
  ```
  Remove the second `try/except` block entirely. If lint.py is not yet importable pre-impl, that's fine — the test already fails at `from anytype_llm_wiki.wiki.lint import wiki_lint`. The `try/except: pass` is creating silent failure modes that will be invisible post-impl.
- Note: The `_qdrant` patches in `test_duplicate_sweep_off_by_default` (lines 1308–1316) have the same issue. Apply the same fix.

**Other validity checks:**

- `test_wiki_lint_importable`, `test_wiki_lint_is_callable`, `test_wiki_lint_signature`: Correctly fail pre-impl. Will pass when `lint.py` is present with the right signature.
- Config resolver tests: Fail pre-impl because the config functions don't exist yet. Will pass when `config.py` is updated. PASSED.
- `test_pre_check_patch_decision_missing_fires_before_write`: The autouse fixture sets `ALDEIA_DIR` to the real `.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/` directory which contains `patch-decision.md`. The test overrides with `tmp_path`. This is correct — QA#30 passes by default and fails only in this test. PASSED.
- `test_pre_check_schema_outdated_fires_before_write`: Uses a fixed `respx.get().mock(return_value=...)` that returns the outdated-schema response for ALL GET calls. A spec-faithful lint that runs list_objects first gets the outdated schema marker and aborts. PASSED.
- Age-based tests all use `freeze_time` from `freezegun`. Deterministic. PASSED.
- `test_contradiction_check_passive`: The "passive" assertion (pipeline fixture) uses `wiki_contradictions=[]`, which should fire zero contradiction findings. The "active" assertion uses `wiki_contradictions=["obj-ref-contradiction"]` (non-empty) + `wiki_last_reviewed=None`. Per the spec, contradiction fires on non-empty `wiki_contradictions`. This will fire with `severity=high`. PASSED.

---

## 5. Convention Compliance

This is a Python project using pytest, not a bash project. Relevant conventions:

**autouse fixture for environment setup:** Present and correct. `set_anytype_env` is autouse, sets all required env vars, and points `ALDEIA_DIR` to the real patch-decision directory. Mirrors the pattern in `test_query.py`. PASSED.

**`@respx.mock` decorator pattern:** All HTTP-intercepting tests use `@respx.mock` as a class-method decorator. No tests use the context-manager form. This mirrors `test_ingest.py`. PASSED.

**No-arg `respx.get()` / `respx.post()` catch-alls:** Used throughout. No use of `respx.patterns.M`. PASSED.

**No hardcoded `/Users/` paths:** The `set_anytype_env` fixture uses `os.path.dirname(os.path.abspath(__file__))` relative to the test file. No hardcoded absolute paths under `/Users/`. PASSED.

**`freezegun` for time-based tests:** All age-based tests use `freeze_time`. PASSED.

**Live class gated with `@pytest.mark.live`:** `TestLintLive` has the correct marker. Tests skip when `ANYTYPE_SPACE_ID` is unset using `pytest.skip()`. PASSED.

**Finding S2 (SHOULD-FIX) — `_standard_mocks` URL routing for `get_object` detection is subtly fragile**

- File: `tests/wiki/test_lint.py`, lines 303–311
- The condition `"/objects/" in path and "?" in url_str` for detecting `get_object` is correct for `AnytypeReadClient.get_object` which adds `?format=md`. However, if lint ever calls `get_object` without the `format=md` param (which would be spec-nonconforming), this condition would fail and the call would fall through to the list_objects branch instead. This is a minor fragility, not a current defect.
- Fix: Not required — the condition correctly matches the spec-specified wire contract.

---

## 6. Test Isolation

All CI tests are decorated with `@respx.mock` which ensures each test gets a fresh respx context. The `monkeypatch` fixture is function-scoped by default in pytest. The autouse `set_anytype_env` fixture is function-scoped and properly resets env vars.

**`test_duplicate_sweep_off_by_default` — two calls in one `@respx.mock` context:**

- File: `tests/wiki/test_lint.py`, lines 1277–1355
- This test makes two `wiki_lint` calls within the same `@respx.mock` context, re-registering respx mocks between them. This is valid in respx — subsequent `respx.get().mock(...)` calls replace previous handlers within the same context. PASSED.

**`test_partial_status_on_get_object_failure` — stateful side_effect using function attribute:**

- File: `tests/wiki/test_lint.py`, lines 1763–1768
- Uses `if not hasattr(get_side_effect, "_list_count"): get_side_effect._list_count = 0` as a call counter. This is function-scoped (a new function is defined per test call), so it doesn't leak between tests. PASSED.

No order-dependency issues found. PASSED.

---

## 7. Existing Test Impact

The following existing tests cover behavior that the spec changes:

**`tests/wiki/test_server_registration.py`**

| Test | Current assertion | Spec impact | Action |
|------|-------------------|-------------|--------|
| `test_existing_tools_still_registered` | Asserts `semantic_search` and `reindex_anytype` in tool registry | Adding `wiki_lint` to `server.py` must not remove existing tools. This is an additive change. | No change needed — test remains valid. |

**`tests/wiki/test_server_registration.py` — `test_wiki_bootstrap_is_registered_mcp_tool`** — unaffected by this spec.

**`tests/wiki/cli.py` registration:** The new `test_wiki_lint_registered_and_cli_routed` test asserts `"wiki-lint" in cli.SUBCOMMANDS`. `cli.py` line 21 currently has `SUBCOMMANDS = ("wiki-bootstrap", "wiki-ingest", "wiki-remember", "wiki-query", "doctor")`. The impl-worker must add `"wiki-lint"` to this tuple. This is not a test impact — it is a required implementation change gated by the new test.

No existing tests assert behaviors that are REMOVED or CHANGED by this spec. All spec changes are additive (new function, new config accessors, new CLI subcommand, new MCP tool). PASSED.

---

## Summary

Two BLOCKING findings prevent approval:

**B1**: The `wiki_status` select property id in `_make_entity` and `_make_concept` (`f"tag-{wiki_status}"`, e.g. `"tag-needs-review"`) does not match the resolved tag id returned by `_make_tags_response` (`"tag-needs-review-id"`). A spec-faithful implementation that resolves the tag id via the property-scoped two-step and then compares per-object select ids will never fire `unreviewed_needs_review` or `stale_needs_review` findings, causing four tests to fail on a correct implementation. Fix: align the id values across both helpers.

**B2**: The dual-patch `try/except (ImportError, AttributeError): pass` pattern for `semantic_search_core` silently swallows both patch failures pre-impl and provides ambiguous coverage post-impl. The established convention from `test_query.py` is to patch only `_idx_mod.semantic_search_core`. The silent exception swallowing creates latent false-green risk. Fix: remove the dual-try pattern, patch only the indexer module attribute (following `test_query.py` convention).

One SHOULD-FIX: the iterator-based GET mock in `test_pre_check_schema_newer_warns_and_continues` is order-sensitive and fragile against implementation reordering of GET calls.

---

## Coverage Table

| Test Plan Row / AC | Test Name | Present | Satisfiable | Notes |
|---|---|---|---|---|
| `test_asymmetric_relation_check_fires` | same | Y | Y | AC1/AC5/AC13 |
| `test_backlinks_primary_no_traversal` | same | Y | Y | AC1 |
| `test_backlinks_malformed_falls_back` | same | Y | Y | AC1/SF10 |
| `test_pipeline_orphan_check_fires` | same | Y | Y | AC5 |
| `test_orphan_check_fires_after_grace` | same | Y | Y | AC1/AC5; source-derived age correctly seeded |
| `test_orphan_check_suppressed_within_grace` | same | Y | Y | AC1 grace period |
| `test_unreviewed_needs_review_fires` | same | Y | NO | **B1**: tag id mismatch |
| `test_stale_needs_review_fires` | same | Y | NO | **B1**: tag id mismatch |
| `test_both_needs_review_checks_fire_on_aged_object` | same | Y | NO | **B1**: tag id mismatch |
| `test_stale_stub_check_never_emitted` | same | Y | Y (vacuously if B1 not fixed) | AC2 |
| `test_contradiction_check_passive` | same | Y | Y | AC5/AC6 |
| `test_stale_check_fires` | same | Y | Y | AC5; source-derived age correctly seeded |
| `test_oversized_check_fires` | same | Y | Y | AC5/SF12 |
| `test_empty_type_check_fires` | same | Y | Y | AC5 |
| `test_duplicate_sweep_fires_when_opted_in` | same | Y | CONDITIONAL | **B2**: depends on impl import style; correct if impl follows query.py convention |
| `test_duplicate_sweep_excludes_outside_band` | same | Y | CONDITIONAL | **B2** same |
| `test_duplicate_sweep_self_match_and_pair_dedup` | same | Y | CONDITIONAL | **B2** same |
| `test_duplicate_sweep_off_by_default` | same | Y | CONDITIONAL | **B2**: false-green risk if patch fails silently |
| `test_duplicate_sweep_runs_regardless_of_threshold` | same | Y | CONDITIONAL | **B2** same |
| `test_duplicate_sweep_skipped_over_object_cap` | same | Y | Y | AC12/SF2; no fake needed since sweep is skipped |
| `test_severity_threshold_high_filters_medium_low` | same | Y | Y | AC7 |
| `test_severity_threshold_low_excludes_informational` | same | Y | Y | AC7/SF7 |
| `test_pre_check_schema_outdated_fires_before_write` | same | Y | Y | AC9/SF4 |
| `test_pre_check_schema_missing_aborts` | same | Y | Y | AC9/SF4 |
| `test_pre_check_schema_newer_warns_and_continues` | same | Y | FRAGILE | **S1**: iterator order-sensitive |
| `test_partial_status_on_get_object_failure` | same | Y | Y | AC11/SF6 |
| `test_pre_check_patch_decision_missing_fires_before_write` | same | Y | Y | AC10 |
| `test_pre_checks_fire_before_wikilog_write` | same | Y | Y | AC10 |
| `test_object_count_budget_warning_above_500` | same | Y | Y | AC12 |
| `test_wikilog_receipt_written_on_clean_run` | same | Y | Y | AC11/G1 |
| `test_wikilog_skipped_on_pre_check_failure` | same | Y | Y | AC11/SF6 |
| `test_tag_resolution_never_calls_space_level_tags` | same | Y | Y | AC13/ADV-2 |
| `test_wiki_lint_registered_and_cli_routed` | same | Y | Y | AC14 |
| `TestLintLive::test_end_to_end_lint` | same | Y | Y | AC15 |
| `TestLintLive::test_backlinks_field_shape_live` | same | Y | Y | AC15/ADV-1 |
| AC2 (stale_needs_review replaces stale_stub) | see above | Y | PARTIAL | Blocked by B1 on positive assertion |
| AC3 (unreviewed_needs_review High) | see above | Y | NO | Blocked by B1 |
| AC4 (double-count rule) | see above | Y | NO | Blocked by B1 |
| AC16 (sweep opt-in default off) | test_duplicate_sweep_off_by_default | Y | CONDITIONAL | B2 |

### Additional tests beyond spec (edge cases)

| Test | Valid / Noise | Notes |
|---|---|---|
| `TestWikiLintImport::test_wiki_lint_importable` | Valid | Hard import gate, fails pre-impl |
| `TestWikiLintImport::test_wiki_lint_is_callable` | Valid | Callable gate |
| `TestWikiLintImport::test_wiki_lint_signature` | Valid | Asserts all three params + correct defaults |
| `TestLintConfigResolvers::test_lint_config_importable` | Valid | Gates that all 6 config functions exist |
| `TestLintConfigResolvers::test_lint_*_default` (6 tests) | Valid | Defaults match spec table |
| `TestLintConfigResolvers::test_bounded_float_rejects_out_of_range` | Valid | Exercises `_bounded_float` guard |
