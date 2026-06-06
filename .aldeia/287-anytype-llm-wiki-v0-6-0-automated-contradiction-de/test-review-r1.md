# Test Review: anytype-llm-wiki v0.6.0 Automated Contradiction Detection — Round 1

**Verdict: APPROVED**

## Review Date
2026-06-06

## Pytest Summary Line (observed)
```
15 failed, 84 passed, 6 deselected, 8 warnings in 1.55s
```
Matches the test-writer's declared summary exactly. AC-7 (`test_doctor.py`) is green (25 passed, 0 failed).

---

## 1. Spec Coverage

All 14 acceptance criteria plus addendum item 5 are covered.

| AC | Test | Status |
|---|---|---|
| AC-1 | `TestContradictionDetection::test_contradiction_bidirectional_write` | COVERED — asserts `contradictions_detected >= 1`, 2+ `wiki_contradictions` PATCHes, no target GET (BL-3), no `wiki_last_reviewed` PATCH |
| AC-2 | `TestContradictionDetection::test_no_detection_on_create` | COVERED — asserts `detect_contradictions` not called; `contradictions_detected == 0` |
| AC-3 | `TestContradictionCheck::test_contradiction_check_active` | COVERED — asserts finding fires, `"PASSIVE" not in detail`, `notes` free of passive string |
| AC-4 | `TestContradictionCheck::test_contradiction_cleared_by_review` | COVERED — existing predicate already correct; passes pre-impl (legitimate invariant guard, documented in debrief) |
| AC-5 | `TestContradictionDetection::test_detection_degraded` + `test_detection_degraded_warning_absent_on_clean_path` | COVERED — degraded path asserts warning present; contrast asserts warning absent |
| AC-6 | `TestReingestIdempotencyWikilog::test_resumed_partial_ingest_wikilog` | COVERED — class name diverges from spec (`TestReingestIdempotencyWikilog` vs `TestReingestIdempotency`); debrief explains rationale (mock-collision avoidance); coverage is complete |
| AC-7 | `tests/wiki/test_doctor.py` (existing, unmodified) | PASSED — 25 tests green, no changes needed |
| AC-8 | `test_contradiction_smoke` (`@pytest.mark.live`) | COVERED — deselected in CI run; live skip guard present |
| AC-9 | `test_ingest_slo_observation` (`@pytest.mark.live`) | COVERED — informational print, no hard gate (consistent with DI-2) |
| AC-10 | `TestContradictionDetection::test_anti_injection_preamble_present` | COVERED — asserts `_CONTRADICTION_PROMPT_PATH` exists + preamble present; monkeypatches to missing path to test fallback |
| AC-11 | `TestContradictionDetection::test_hallucinated_id_filtered` | COVERED — patches `_call_ollama_prompt`; exercises REAL filter logic |
| AC-12 | `TestContradictionDetection::test_self_reference_skipped` | COVERED — asserts no peer GET for `obj_id`; `obj_id` absent from result |
| AC-13 | `TestContradictionDetection::test_multiple_peers_contradict` | COVERED — 2 peers from `detect_contradictions`; asserts `contradictions_detected == 2`, >= 4 wiki_contradictions PATCHes |
| AC-14 | `TestContradictionDetection::test_dedup_no_op` | COVERED — target already carries peer; asserts A-side PATCH skipped, `contradictions_detected == 0` |
| Addendum 5a (linked-entities) | `TestReadmeDetectionScopeDisclosure::test_readme_discloses_linked_entities_only_scope` | COVERED |
| Addendum 5a (entity-only) | `TestReadmeDetectionScopeDisclosure::test_readme_discloses_entity_only_scope` | COVERED |
| Addendum 5a (passive-replaced) | `TestReadmeDetectionScopeDisclosure::test_readme_passive_section_replaced` | COVERED |
| Addendum 5b (honest-fixture comment) | `_make_objects_shaped_search_response` docstring | COVERED — parsing-contract-only comment present |

Minor naming deviation (AC-6): the spec names `TestReingestIdempotency::test_resumed_partial_ingest_wikilog` but the test uses `TestReingestIdempotencyWikilog::test_resumed_partial_ingest_wikilog`. The method name matches; the class name is suffixed to avoid collision with the existing `TestReingestIdempotency` mock pattern. Coverage is complete. This is a SUGGESTION to reconcile with spec naming at impl time if desired, not a coverage gap.

**PASSED** (with the minor AC-6 naming note above)

---

## 2. Edge Case Coverage

Edge cases are well-covered for the new contradiction detection surface:

- **Empty peer set (no wiki_relations):** Covered implicitly by AC-2 (create path → no detection) and the detection contract (empty candidate set → returns []).
- **Self-reference (peer_id == obj_id):** AC-12 explicitly tests this (SG-3).
- **Multiple peers:** AC-13 tests two-peer detection with 4+ PATCHes.
- **Dedup (already-linked):** AC-14 tests A-side skip and zero count.
- **LLM failure (hard error):** AC-5 tests `httpx.ConnectError` → degraded warning.
- **Hallucinated ID (LLM injects unknown id):** AC-11 tests the SG-2 filter.
- **Bidirectional write + no target GET:** AC-1 asserts both.
- **wiki_last_reviewed not touched:** AC-1 asserts no such PATCH key appears.

The edge cases are comprehensive for the v0.6.0 scope. Qdrant semantic pre-filter is explicitly deferred (DI-3) and therefore not tested.

**PASSED**

---

## 3. Assertion Correctness

All assertions cross-reference correctly against the spec:

- **AC-1:** `contradictions_detected >= 1` (correct — deduped `links_written`; spec §3.5), 2+ `wiki_contradictions` PATCHes (correct — bidirectional), no `wiki_last_reviewed` (correct — spec §3.4 final paragraph). BL-3 check: `target_gets = [u for u in get_calls if f"/objects/{target_obj_id}" in u and "?" in u]` — correct pattern per spec §3.8 WIRE LANDMINE 2.

- **AC-2:** `detect_called` list must be empty; `contradictions_detected == 0`. Both are correct against spec §3.2 (create branch skipped).

- **AC-3:** `"PASSIVE" not in detail` — correct per spec §3.7 change 3. `notes == []` is NOT checked in this test (only "passive until v0.6.0" substring), but the `test_wikilog_receipt_written_on_clean_run` test asserts `notes == []` as the post-v0.6.0 default (§3.7 change 2). Together they cover the full requirement.

- **AC-5 contrast:** `"contradiction_detection_degraded" not in result.get("warnings", [])` — correct, distinguishes "no contradictions" from "detection failed".

- **AC-11:** `_call_ollama_prompt` returns `(dict, None)` — correctly matches the real return type `tuple[dict | None, httpx.Response | None]`. The mock returns `({"contradictions": [...]}, None)`, which the real `detect_contradictions` will unpack as `parsed, _resp = _call_ollama_prompt(...)`. The mock is type-consistent.

- **AC-14:** `contradictions_detected == 0` with A-side PATCH skipped — correctly asserts the full dedup contract (spec §3.4: "skip the PATCH entirely if the dedup made no change").

- **AC-8 (live):** The assertion `total_contradictions >= 1 or len(contradiction_findings) >= 1` is slightly weaker than the spec's "assert `wiki_contradictions` bidirectionally set AND `wiki_lint` reports High finding" (OR vs AND). This is acceptable given LLM non-determinism; the spec acknowledges "live LLM output varies". **SUGGESTION (not blocking):** consider `and` instead of `or` with a clear failure message to provide stronger evidence.

**PASSED** (with the AC-8 OR-vs-AND suggestion)

---

## 4. Test Validity (will they fail now?)

Confirmed by actual test run: all 15 new/modified tests fail for the right reasons.

### Failure reasons verified:

| Test | Failure Mechanism | Pre-Impl Reason |
|---|---|---|
| `test_contradiction_bidirectional_write` | `AttributeError: ... has no attribute 'detect_contradictions'` | Correct — `monkeypatch.setattr` fails because attribute doesn't exist |
| `test_no_detection_on_create` | Same `AttributeError` on `monkeypatch.setattr` | Correct |
| `test_detection_degraded` | Same `AttributeError` | Correct |
| `test_detection_degraded_warning_absent_on_clean_path` | Same `AttributeError` | Correct |
| `test_anti_injection_preamble_present` | `AttributeError: ... has no attribute '_CONTRADICTION_PROMPT_PATH'` | Correct |
| `test_hallucinated_id_filtered` | `ImportError: cannot import name 'detect_contradictions'` | Correct |
| `test_self_reference_skipped` | Same `ImportError` | Correct |
| `test_multiple_peers_contradict` | `AttributeError` on `detect_contradictions` | Correct |
| `test_dedup_no_op` | `AttributeError` on `detect_contradictions` | Correct |
| `test_resumed_partial_ingest_wikilog` | `AssertionError: 'resumed_partial_ingest' not in wikilog payloads` | Correct — `_create_source` returns bare str, no was_resumed |
| `test_contradiction_check_active` | `AssertionError: PASSIVE in detail` | Correct — lint.py:429 still appends "(PASSIVE check — see #287)" |
| `test_wikilog_receipt_written_on_clean_run` | `AssertionError: notes != []` | Correct — lint still emits passive note |
| `test_readme_discloses_linked_entities_only_scope` | `AssertionError: 'linked entities' not in readme` | Correct |
| `test_readme_discloses_entity_only_scope` | `AssertionError: entity_only_disclosed is False` | Correct |
| `test_readme_passive_section_replaced` | `AssertionError: 'passive until v0.6.0' still present` | Correct |

**AC-4 (`test_contradiction_cleared_by_review`) passes pre-impl.** This is documented by the test-writer as expected: the existing predicate `(contradictions and not last_reviewed)` already correctly suppresses the finding when `wiki_last_reviewed` is set. This is a legitimate invariant-guard test, not an accidental no-op. The spec includes AC-4 "for completeness" — the criterion was already satisfied in v0.5.0.

No test passes for the wrong reason.

**PASSED**

---

## 5. Convention Compliance

This is a Python/pytest project (not bash). Checking against project conventions:

- **No hardcoded absolute paths under `/Users/`:** `test_docs_disclosure.py` uses `pathlib.Path(__file__).parent.parent.parent / "README.md"` — computed relative to `__file__`, not hardcoded. PASSED.
- **`/tmp/` for temp files:** `test_contradiction_smoke` and `test_ingest_slo_observation` use `tempfile.NamedTemporaryFile` which uses the OS-level temp dir. PASSED.
- **respx 0.23.x patterns:** All mocks use `respx.get()`, `respx.post()`, `respx.patch()` no-arg forms with `side_effect`. No `respx.patterns.M`. PASSED.
- **Imports inside test methods** (not at module level): All new symbols (`detect_contradictions`, `wiki_ingest`, etc.) are imported inside test methods to avoid collection-time import failures. PASSED — this was an explicit test-writer decision per the debrief and is correct.
- **Module-level imports:** The file uses `import httpx` and `import respx` at module level, which is correct (pre-existing, not new symbols).

One SUGGESTION: `test_readme_discloses_linked_entities_only_scope` computes `linked_entities_disclosed` (lines 86-92) but never uses it in the assertion (line 98 uses a simpler condition). The `linked_entities_disclosed` variable is dead code. This does not affect test correctness but may confuse readers. SUGGESTION: Either use `linked_entities_disclosed` in the assertion, or remove the dead-code computation.

**PASSED** (with dead-code suggestion)

---

## 6. Test Isolation

Each test is independently runnable:

- All `TestContradictionDetection` tests use `@respx.mock` or `MagicMock` — no shared mutable state.
- `TestReingestIdempotencyWikilog::test_resumed_partial_ingest_wikilog` uses `@respx.mock` with local closures.
- `TestContradictionCheck` tests in test_lint.py use per-test respx fixtures via `_standard_mocks`.
- `TestReadmeDetectionScopeDisclosure` tests read a static file — no side effects.
- Live tests gate on `ANYTYPE_SPACE_ID` env var; use `tempfile.NamedTemporaryFile` with `finally: os.unlink`.
- The `set_anytype_env` autouse fixture in test_ingest.py applies to all new tests via the standard pytest fixture mechanism.

No tests depend on execution order or each other's side effects.

**PASSED**

---

## 7. Existing Test Impact

### Pre-existing tests that will be affected by the v0.6.0 impl

**BL-4 sites (spec §7 "Existing test changes required") — ALREADY FIXED by test-writer:**

1. `tests/wiki/test_lint.py::TestContradictionCheck::test_contradiction_check_passive`
   — **Renamed** to `test_contradiction_check_active`; passive detail assertion replaced with `"PASSIVE" not in detail`. Confirmed in diff.

2. `tests/wiki/test_lint.py::TestStatusLifecycle::test_wikilog_receipt_written_on_clean_run`
   — **Updated**: `assert any("passive until v0.6.0" in str(n) ...)` replaced with `assert notes == []`. Confirmed in diff.

**`_create_source` return type change (spec §3.6 BL-6):**

3. `tests/wiki/test_ingest.py::TestReingestIdempotency::test_reingest_same_source_creates_zero_and_reuses_source` (line 2251)
   — Currently passes (pre-impl). After impl, `_create_source` will return `tuple[str|None, bool]` and the two call sites in `ingest.py` will unpack the tuple: `source_id, _ = _create_source(...)` → `result["source_object_id"] = source_id`. The assertion `r1["source_object_id"] == r2["source_object_id"]` compares strings post-unpack and will remain valid.
   — **No action required** IF impl correctly unpacks at both call sites per spec §3.6 BL-6. The impl must NOT store the tuple directly in `result["source_object_id"]` — the spec is explicit. This is an impl obligation, not a test failure.
   — The spec §7 says "Any test that asserts `_create_source` returns a bare `str`" needs updating; no such test exists (confirmed by `grep -rn "_create_source(" tests/`).
   — **Recommendation: MONITOR** — the impl-worker must unpack both call sites per BL-6 or this test breaks. No test change needed.

**No other existing tests assert behaviors that the spec is changing.**

---

## Summary

The test suite is well-constructed and spec-faithful. All 15 new/modified tests fail for the correct pre-impl reasons (missing attributes, wrong values). AC-4 passes pre-impl as a documented legitimate invariant (existing predicate already correct). Wire contract compliance is verified: search mocked as POST, get_object as GET with `?`, no target GET (BL-3), no `respx.patterns.M`. Addendum items 5a (README disclosure) and 5b (honest-fixture comment) are both implemented. Convention compliance is clean with two non-blocking suggestions: (1) dead `linked_entities_disclosed` variable in the linked-entities README test, and (2) live AC-8 uses OR rather than AND for the contradiction/lint assertion. Neither prevents the tests from serving as effective spec gates. The verdict is APPROVED.
