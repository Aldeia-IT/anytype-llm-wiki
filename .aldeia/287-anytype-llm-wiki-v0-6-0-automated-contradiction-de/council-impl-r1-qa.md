# Council Review — Impl R1 — QA Director (#287)

**Phase:** POST-IMPL final delivery gate (GOVERNANCE-level)
**Ticket:** anytype-llm-wiki v0.6.0 — Automated Cross-Object Contradiction Detection
**Reviewer:** QA Director (independent; no Mem0 read/write)
**Date:** 2026-06-06

## Verdict

**SIGN-OFF (advance to PR)** — with two ADVISORY items carried forward as documented pre-tag gates and one ADVISORY test-quality note. Zero BLOCKING.

The CI-runnable quality scope is complete, traceable, and the negative/absence assertions I was asked to scrutinize are non-vacuous (verified by my own fault injection, except one caveat below). The two residual risks (platform assumption, live smoke) are environmental, not implementation gaps, and are honestly documented for the release runbook rather than silently claimed done — which is the correct disposition for a headless delivery gate.

## BLOCKING findings

None.

## ADVISORY findings

### ADV-1 — Platform-assumption gate (CTO-ADV-1) is GREEN-IN-CI but UNVERIFIED against real Anytype; must remain a hard pre-tag gate
**Description.** The no-target-GET design (spec §3.3 step 1, §3.4 step 1, §4) depends on POST `/v1/spaces/{sid}/search` returning *hydrated* `properties[].objects` arrays for `wiki_relations` / `wiki_contradictions`. No existing reader in the codebase reads `prop.get("objects")` off a *search* response — every proven reader operates on a `get_object` result. I confirmed the AC-1 fixture (`_make_objects_shaped_search_response`, test_ingest.py:1205) proves only the *parsing* contract; it carries the required honesty comment (addendum item 5b, lines 1213-1221) explicitly stating it does NOT validate real-search hydration.
**Impact on reliability.** If the assumption is wrong, `_relation_ids(target, "wiki_relations")` yields an empty candidate set → `detect_contradictions` silently returns `[]` → the feature ships green-in-CI and dead-in-prod (no contradiction ever fires). This is the highest residual risk in the ticket and is the exact silent-no-op failure class R2 previously caught (wrong-helper bug), relocated to an untested response shape.
**Recommended action.** Keep this as a binding pre-tag verification gate in the release runbook. Fix is cheap and pre-identified: if real search does not hydrate objects-format arrays, add a single target `get_object` (+1 call, mirroring the peer-read pattern) and correct §4's "NO target GET" claim. Acceptable to defer to runbook (not block PR) because it requires live Anytype and the fallback is designed-in. The impl-worker stored this as a durable caution (memory `8f597af8`), which is appropriate.

### ADV-2 — AC-8/AC-9 live smoke + SLO are skip-gated, never executed in this delivery
**Description.** AC-8 (two conflicting sources → bidirectional `wiki_contradictions` + High lint finding) and AC-9 (wall-clock SLO observation) are `@pytest.mark.live`. I confirmed both collect cleanly (`test_contradiction_smoke`, `test_ingest_slo_observation`) with zero collection errors, but they are deselected headless (need `ANYTYPE_SPACE_ID` + real Ollama).
**Impact on reliability.** The end-to-end live contradiction path and the E1 SLO budget have no executed evidence in this gate. Note AC-9 is informational-only by spec (§4, DI-2) — not a release-blocking AC — so this is genuinely an observation, not a hard gate. AC-8 is the one true end-to-end proof and overlaps with ADV-1 (both need the live runbook run).
**Recommended action.** Carry AC-8/AC-9 in the same pre-tag runbook as ADV-1. Acceptable to defer; do not block PR.

### ADV-3 — AC-12 self-reference test: first disjunct is vacuously satisfied; the result-side assertion is the real (and adequate) guard
**Description.** The compound assertion `assert not mock_read_client.get_object.called or all(obj_id not in str(c) ...)` (test_ingest.py:1769) was the spec-flagged vacuity risk. I verified by reading the impl: the self-filter happens at candidate-build time (`candidates = [pid for ... if pid != obj_id]`, ingest.py:411), so for this test the candidate list is empty and the peer-GET loop never runs — making `get_object.called == False` *unconditionally*. The first disjunct is therefore satisfied because NO get_object happens at all, not specifically because a self-GET was skipped. My fault injection (removing the self-filter) flipped the test red, but for an incidental reason (`TypeError: MagicMock not JSON serializable` when the un-filtered self is fed to `json.dumps`), before the assertion at 1769 was even reached.
**Impact on reliability.** Low. The SECOND assertion (`obj_id not in result_ids`, line 1778) IS meaningfully protective, and the underlying invariant is double-defended: self is excluded from `candidate_set`, so even an LLM echo of `obj_id` is dropped by the SG-2 hallucinated-id filter (ingest.py:448). The self-reference protection is real and well-architected; only the *first clause* of the AC-12 assertion is non-load-bearing.
**Recommended action.** No blocker. Optional future hardening: tighten AC-12 so the first clause asserts on a non-empty candidate set that *includes a legitimate peer plus* the self-id, proving the self-id specifically is skipped while a real peer is fetched. Not required for this PR.

## Rationale

I independently verified, not merely accepted, the quality claims:

- **Headline suite reproduced:** I ran `pytest -m "not live" -q` myself → **572 passed, 25 skipped, 8 deselected, 2 xfailed** — byte-for-byte matching the lead's report. Zero failures. All target contradiction tests (9 in `TestContradictionDetection`, 3 lint, doctor 25) pass.

- **Test-first workflow confirmed legitimate:** the impl diff `81b54d3..HEAD` contains source + docs + one fixture line, and **no test code** — because the AC-1..AC-14 tests landed earlier in the test phase (`c6fc8a7`, before baseline). This is correct red-before-green sequencing, not missing coverage.

- **Negative-assertion non-vacuity (addendum post-test item 5 — my verification point):**
  - **AC-5 (degraded warning present):** PROVEN non-vacuous. I suppressed the warning append and `test_detection_degraded` flipped red while the contrast test `test_detection_degraded_warning_absent_on_clean_path` stayed green — exactly the polarity pair required. The faulted result also showed a real update path drove the hook.
  - **AC-5 contrast (warning absent):** non-vacuous by construction — its partner test proves the same fixture shape CAN raise the warning.
  - **AC-2 (detect not called on create):** structurally sound — search returns empty `data` forcing the create branch; the fake recorder would populate if detection fired. Contingent on the create path being genuinely reached.
  - **AC-12 (self-ref):** result-side assertion adequate; first clause vacuous — see ADV-3.

- **Disclosure-presence gate (addendum item 5a / post-test item 1 — my verification point):** `tests/wiki/test_docs_disclosure.py::TestReadmeDetectionScopeDisclosure` exists and passes (3 tests), asserting linked-entities-only + entity-only scope copy and the removal of the "passive until v0.6.0" section — so the replacement operator disclosure cannot silently regress. Separately, the widened peer-fact egress disclosure is regression-gated through the verbatim fixture `readme_privacy_notice_verbatim.md` (now carrying "also receives the `wiki_facts` of already-linked peer entities"), pinned byte-for-byte by `test_readme_contains_verbatim_privacy_notice`. Both disclosure obligations have CI regression gates.

- **PASSIVE caveat fully removed:** `grep` finds no `_PASSIVE_CONTRADICTION_NOTE` / "PASSIVE check" / "passive until v0.6.0" in `src/`; the only matches are in the disclosure test asserting their absence. Lint is genuinely active (AC-3/AC-4 green).

- **Regression risk:** zero regressions (572 green incl. the reader-move blast radius: `test_remember`, `test_query`, `test_lint` all pass via the `util.py` move + `query.py` re-export). The `_create_source` tuple-unpack (BL-6) and the `_call_ollama_prompt` bare-import (post-test item 3) — both pre-identified test-coupling landmines — are handled; AC-11/AC-12 monkeypatch `ingest._call_ollama_prompt` successfully, proving the import lands module-locally.

- **Traceability:** every AC-1..AC-14 maps to a named, passing test; AC-7 (doctor exit 0) green; AC-8/AC-9 collected-and-deferred (ADV-2). No tests were modified or skipped during impl beyond the spec-mandated `test_contradiction_check_passive` → `test_contradiction_check_active` rename and the receipt-note removal (both spec §7 / BL-4 directed).

The quality gates required for advancing to PR are met. The two deferred items are environmental pre-tag gates, correctly documented and not implementation defects. I sign off.

---
**VERDICT: SIGN-OFF (advance to PR).** BLOCKING: 0. ADVISORY: 3. The CI-runnable scope is complete, traceable, and the spec-flagged negative assertions are non-vacuous (AC-5 fault-injection-proven; AC-12 has a vacuous first clause but an adequate result-side guard); the platform-assumption and live-smoke gaps are environmental and correctly deferred to a documented pre-tag runbook.
