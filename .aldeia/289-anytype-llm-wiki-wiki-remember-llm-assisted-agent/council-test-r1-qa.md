# Council Test Review (R1) — QA Director

**Ticket:** #289 anytype-llm-wiki `wiki_remember` (v0.3.1)
**Phase reviewed:** TEST (pre-impl gate)
**Reviewer:** QA Director (governance lens — not line-by-line; technical test review already ran R1→R2 APPROVED)
**Date:** 2026-06-04
**Verdict:** **SIGN-OFF — advance to impl.** 0 BLOCKING, 3 ADVISORY (all impl-phase carry conditions, none gating).

---

## What I verified

I traced every acceptance criterion to a named, substantive test and independently re-ran the suite.

- **Suite state reproduced:** `74 failed / 294 passed / 1 skipped / 3 deselected / 2 xfailed` on `-m 'not live'` — matches the chair's verified facts exactly.
- **`live` marker is registered** (`pyproject.toml:45`) and CI tests are fully mocked (respx + monkeypatch, `tmp_path`), so the live smoke gate (AC-R7/R24) is genuinely deselected, not silently collected.
- **Regression guards + #284 forward-note tests:** the 4 guards (`test_doctor_green_after_v031_bootstrap`, `test_write_wikilog_default_name_is_ingest`, `test_resolve_action_tag_default_is_ingest`, `test_extract_request_payload_unchanged_after_refactor`) + the 2 forward-note tests (`test_bootstrap_action_tags_idempotent`, `test_bootstrap_creates_all_five_action_tags`) → **6 passed** pre-impl. Correct.

### Q1 — AC/addendum traceability (every AC-R + addendum item → substantive falsifiable test)
**PASS.** Every AC-R1–R31, AC-R-S1/S2, AC-R12b, and every addendum item 1–8 maps to a named test, and the high-stakes ones are substantive, not tautological:
- **Item 4 / AC-R27 sanitize-on-write** (`test_consolidated_text_sanitized_on_write`, test_remember.py:1090) asserts the spied `wiki_facts` PATCH value `== sanitize_property_value(consolidated_text)` **byte-for-byte** with an embedded U+200C, after a setup-guard that the raw text differs from sanitized. The raw LLM output is provably never written. This is the strongest form the addendum demanded.
- **Item 1 supersede audit** (`test_supersede_recorded_in_wikilog_notes`:2813) asserts the superseded prior text appears in the WikiLog notes payload. (See ADV-1 on assertion looseness — non-blocking.)
- **Item 2 sources-overwrite** (`test_conflict_path_surfaces_sources_overwrite`:2881) asserts a `sources_overwrite_on_conflict` warning in the result — the council-chosen mechanism.
- **Item 8 extract-refactor guard** (`test_extract_request_payload_unchanged_after_refactor`, test_extraction.py:1056) asserts model == `config.extract_model()`, `options == _DETERMINISTIC_OPTS` on BOTH generate and chat payloads, the generate→chat malformed-JSON fallback, and prompt-vs-messages format. Plus `test_extract_model_not_pulled_detection_unchanged` covers the 404 path. This is the real wire-behavior lock the CTO asked for, and it PASSES today.

### Q2 — Highest-stakes properties driven end-to-end against the real entry point (addendum items 5 & 6)
**PASS.**
- **AC-R6 twice-driven convergence** (`test_remember_twice_converges_no_op`:379) calls `wiki_remember` twice with a stateful mock client whose `search` returns the call-1-created object on call 2. Asserts call-1 `action="created"`, call-2 `action="consolidated"`, **`update_calls == []`** on call 2 (hard equality), and a stable `object_id` across both calls. This is the convergence property proven end-to-end, not gate-fixtured.
- **AC-R28 conflict-independence** (`test_conflict_flag_when_patch_skipped`:862) uses an already-`needs-review` entity with `changed=False` + non-empty `conflicts[]`; asserts the `wiki_facts`/`wiki_definition` text PATCH is skipped, `action="consolidated"`, yet `conflicts_flagged >= 1` and the WikiLog still records `conflicts_flagged`. Proves conflict-flagging runs independent of the D3 normalize gate (SF1).
- **AC-R29 ambiguity-no-write** (`test_ambiguous_subject_skips_and_warns`:2204) — the S-R1 fix is real: the search mock is subject-aware (2 same-name same-type rows for `AmbigEntity`, 1 distinct row for `ClearEntity`). Asserts `not ambig_update_calls` AND **`len(clear_update_calls) == 1`** — so it proves both the ambiguous skip and that the co-resident unambiguous subject still writes. Plus `action="error"`/`error="ambiguous_subject"`/`status="partial"`.
- **Entry gates (item 3)** drive the real boundary: `test_empty_knowledge_rejected_before_lock`:2637 and `test_oversize_knowledge_rejected_before_lock`:2679 use `mock_lock.assert_not_called()` + `mock_extract.assert_not_called()` + a create-call spy proving no `create_object`. `test_space_lock_held_returns_ingest_in_progress`:2703 mocks the lock to raise and asserts `[DATA ERROR] ingest_in_progress` + `extract` never called. `test_consent_banner_fires_on_live_path`:2736 records call order and asserts consent precedes extract. None imports an isolated helper — all hit `wiki_remember`.

### Q3 — Regression posture
**SOUND.** The #284 surface is protected on two axes: (a) the generalized seams keep their defaults guarded (`_write_wikilog` default name `ingest {subject}`, `_resolve_wiki_action_tag` default `ingest` tag) by passing guards; (b) the DRY `_call_ollama_prompt` refactor that touches the shipped extraction path is locked by the request-payload regression guard (item 8), which passes today. The N-R1 forward note (action-tag count 5→6) is a clean, low-risk handoff: the two #284 count-tests stay green pre-impl and are explicitly flagged for the impl-worker to bump to 6 — correctly left untouched to preserve the must-pass-pre-impl invariant.

### Q4 — Quality gaps
No blocking gap. Three advisory items below, all carried into impl.

---

## Findings

### ADVISORY

**ADV-1 — Two addendum-item tests assert via substring/`str()` rather than structured payload; impl must not satisfy them trivially.**
- `test_supersede_recorded_in_wikilog_notes` (item 1) accepts `superseded_text in wikilog_str OR "4 GB RAM" in wikilog_str` against `str(properties)`. The `OR "4 GB RAM"` clause is redundant (it's a substring of the full text) and the assertion is against a stringified payload, not the specific `wiki_notes` property. It will pass for any impl that places the old text anywhere in the WikiLog create payload.
- `test_conflict_flag_when_patch_skipped` and several conflict tests assert `"conflicts_flagged" in str(wikilog_payloads[0]["properties"])` rather than parsing the `wiki_notes` value.
- **Impact:** Low. These prove the durable-audit *intent* (the destructive `supersede` and conflict paths leave a record), which is the addendum's actual requirement. The looseness means a misplaced-but-present note would pass, not that a missing note would pass — so the regression-protection direction is correct.
- **Recommended action:** Impl phase — when writing the impl, ensure the superseded text and conflict summary land in the `wiki_notes` property specifically (per D4/§11.4), not an incidental field. No test change required pre-impl.

**ADV-2 — Consent-ordering assertion (AC-R-S1) is guarded by `if extract_calls:`.**
In `test_consent_banner_fires_on_live_path` the strict ordering check (`consent_idx < extract_idx`) only runs *if* extract was called. The unconditional assertion is that consent fired at all. If an impl bug caused extract to be skipped entirely on the non-local path, the ordering half would vacuously pass.
- **Impact:** Low. The consent-was-called assertion is unconditional and is the load-bearing hard-gate check; the canned `extract` is wired to be called in this test's happy path, so in practice the ordering branch executes. The HARD GATE (consent fires) is genuinely asserted.
- **Recommended action:** Impl reviewer — confirm the live-path test actually exercises the ordering branch (extract observed) when verifying impl. Optional pre-impl hardening, not required.

**ADV-3 — Chair's "all 74 failures are ModuleNotFoundError/ImportError/AttributeError" is slightly imprecise (does not change the TDD verdict).**
6 distinct failure sites (≈12 assert hits) are **AssertionError**, all in `test_bootstrap.py` (AC-R19/R20/R21/R22 tag-seeding): `wiki_bootstrap` is importable today (shipped in #284) but does not yet seed the `remember` / `wiki_status` / `wiki_source_type` tags, so these fail on a behavior-absence assertion (`'remember' not in {...}`), not an import error. I verified each is correct behavior-absence, not a test bug.
- **Impact:** None on the gate — this is still the correct test-first state (new behavior absent). Noting it only so the record is accurate: the suite is not purely import-absence; the bootstrap-seeding ACs are assertion-driven by design because the module pre-exists.
- **Recommended action:** None. Informational.

---

## Sign-off

The test phase **adequately de-risks advancing to impl from a quality-gate, acceptance-criteria, and regression-risk perspective.** Every AC-R and every addendum item 1–8 traces to a named, falsifiable, substantive test driving the real `wiki_remember` entry point where the addendum requires it; the four highest-stakes properties (twice-driven convergence, conflict-independence, ambiguity-no-write, sanitize-byte-for-byte) are proven end-to-end, not fixtured; the #284 regression surface is double-guarded and green pre-impl; and the suite is in correct test-first failing state (74 fail / 294 pass, failures all attributable to absent impl behavior).

**QA DIRECTOR: SIGN-OFF — APPROVED to advance to impl.** No veto. No BLOCKING findings.

**Carry into impl (non-gating):**
1. Land the superseded text + conflict summary in the WikiLog `wiki_notes` property specifically (ADV-1).
2. Impl reviewer: confirm the consent-ordering branch is exercised (ADV-2).
3. **N-R1 (mandatory impl-side):** bump `test_bootstrap_action_tags_idempotent` and `test_bootstrap_creates_all_five_action_tags` from 5→6 when adding `"remember"` to `_WIKI_ACTION_TAGS`.
4. **AC-R7/R24 has no CI equivalent** — run `test_live_wiki_remember_end_to_end` (`@pytest.mark.live`) manually before the impl PR; it is the only retrievable-after-reindex coverage.
