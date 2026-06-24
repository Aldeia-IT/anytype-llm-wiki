# Council Spec Review R1 — QA Director — #325 Contradiction Detection: Extend to Concepts

**Date:** 2026-06-18
**Reviewer:** QA Director (post-spec council, Round 1)
**Phase under review:** SPEC (no code yet — judging Test Plan completeness + AC coverage + regression risk of the test strategy)
**Scope verified against source:** `tests/wiki/test_ingest.py`, `src/anytype_llm_wiki/wiki/ingest.py`, `src/anytype_llm_wiki/wiki/lint.py`, `tests/wiki/test_lint.py`

## Verdict: SIGN-OFF (no BLOCKING). Two ADVISORY items.

The spec's Test Plan is adequate to validate the confined core (CS-1..CS-6, CS-9) and to guard the entity regression. Every load-bearing claim I spot-checked against source is accurate. AC-3 ("tests mirror the entity path") — a first-class acceptance criterion here — is satisfied: AC-C1..C10 cover the meaningful entity behaviors, and the two deliberate omissions are correctly justified. The SF-1 silent-`TypeError` trap is real, correctly diagnosed, and adequately mitigated with a complete and verified stub list. AC-C7's mock shape and the SG-7 envelope foot-gun are specified precisely enough for the test worker. The "fail before implementation" requirement is present for the new tests.

---

## Evidence-based verification (what I confirmed against source)

**Stub list complete (SF-1).** The six monkeypatch stubs cited by the spec exist at exactly the lines claimed and all lack a `kind` parameter:
- `test_ingest.py:1319` `fake_detect_contradictions(new_facts, obj_id, target, space_id, client, read_client)`
- `:1388` `fake_detect_contradictions(...)`
- `:1452` `fake_detect_raises(...)`
- `:1524` `fake_detect_no_contradictions(...)`
- `:1765` `fake_detect_two_peers(...)`
- `:1899` `fake_detect_one_peer(...)`
No seventh stub in `TestContradictionDetection` monkeypatches `detect_contradictions`. The list is exhaustive.

**SF-1 trap mechanism confirmed.** `ingest.py:925` is `except Exception:` and `:926` appends the bare `contradiction_detection_degraded` then sets `peers = []`. A stub raising `TypeError` from the `kind=kind` call is swallowed here — producing degraded-warning + `contradictions_detected == 0`, which silently fails the stubbed assertions. The spec's description of the failure mode is exact.

**CS-9 entity regression is airtight at the assertion level.** `test_detection_degraded` (`:1501`) asserts `"contradiction_detection_degraded" in result.get("warnings", [])` — a substring/membership check on the bare string. CS-9 leaves the entity path emitting that exact bare string and only appends `:concept` on the non-entity path, so this assertion passes unchanged. No entity assertion anywhere keys on the warning being the *sole* element, so the suffix-on-concept-only design does not break any existing entity test.

**AC-C7 / SG-7 mock shape is correct.** The real `detect_contradictions` builds the candidate entry at `ingest.py:567-571` as `{"object_id", "name", "facts": _existing_text(peer_obj, "wiki_facts")}` (CS-5 swaps the key to `_facts_key_for_peer(peer_obj)`). The real-call entity tests confirm the SG-7 distinction: `test_hallucinated_id_filtered:1664` uses `_make_peer_get_object_response(real_peer_id)["object"]` — the **unwrapped** dict — when assigning `mock_read_client.get_object.return_value`. AC-C7/AC-C8 instruct exactly this (unwrapped dict for the client-method mock; full envelope for respx). The asserting surface AC-C7 names — candidate JSON passed to `_call_ollama_prompt` — matches how `test_hallucinated_id_filtered` already monkeypatches `_call_ollama_prompt` (`:1656`). The worker has a working pattern to mirror.

**"Fail before implementation" present.** Spec line 339-341 requires AC-C1, AC-C3..C10 to fail against the current codebase (gate `kind == "entity"`, no `kind` param). Satisfied.

**Follow-up deferral claims accurate.** `lint.py:490` gates `contradiction_unresolved` to `if tk == "wiki_entity":` (comment "SF9", `:487`), severity `critical` (`:500`) — confirming SF-R2-1 (README's "High" is wrong). `test_lint.py:_make_concept` (`:157`) builds neither `wiki_contradictions` nor `wiki_last_reviewed`, unlike `_make_entity` (`:123-140`) — confirming the follow-up's AC-C11 prerequisite. The SG-4 B-side rollback gap is genuinely pre-existing: no B-side rollback test exists in the entity suite.

---

## Mirroring assessment (AC-3 — first-class criterion)

The 9 entity `TestContradictionDetection` tests map to the concept plan as follows:

| Entity test | Concept analogue | Status |
|---|---|---|
| `test_contradiction_bidirectional_write` (1238) | AC-C1 | mirrored |
| `test_no_detection_on_create` (1377) | AC-C3 | mirrored |
| `test_detection_degraded` (1438) | AC-C4 (asserts `:concept` suffix) | mirrored + extended |
| `test_detection_degraded_warning_absent_on_clean_path` (1513) | **none** | gap (ADV-1) |
| `test_anti_injection_preamble_present` (1571) | none — justified (shared prompt, SF-4) | correctly omitted |
| `test_hallucinated_id_filtered` (1620) | **none** | gap (ADV-1) |
| `test_self_reference_skipped` (1688) | AC-C5 | mirrored |
| `test_multiple_peers_contradict` (1747) | AC-C9 | mirrored |
| `test_dedup_no_op` (1881) | AC-C6 | mirrored |

Plus net-new concept-only coverage with no entity equivalent: AC-C7 (real-function `wiki_definition` dispatch), AC-C8 (mixed-kind peer uses peer's facts key), AC-C10 (empty/absent concept definition). These directly exercise the genuinely new behavior (`_facts_key_for_peer`), which is the right place to spend test budget.

The omission of an anti-injection concept variant is correctly justified (the prompt is kind-agnostic; entity coverage suffices). The two unjustified-but-minor gaps are folded into ADV-1 below.

---

## ADVISORY

### ADV-1 — Two entity real-call/contrast tests have no concept analogue; no documented rationale.
**Description:** `test_hallucinated_id_filtered` (the SG-2 security invariant: the LLM cannot inject a link target) and `test_detection_degraded_warning_absent_on_clean_path` (the degraded-vs-clean discriminator) have no concept mirror and, unlike the anti-injection omission, the spec does not explain why. The hallucinated-ID filter (`ingest.py:591-593`) is kind-agnostic and structurally exercised by AC-C1's candidate-set construction, so the risk of a concept-specific regression there is low. The clean-path-warning-absent case matters more now: CS-9 makes the concept warning a *different string* (`contradiction_detection_degraded:concept`), and AC-C4 only asserts the suffix is *present* on the error path — nothing asserts it is *absent* on a clean concept path.
**Impact on reliability:** Low-moderate. A concept clean path that spuriously emits `contradiction_detection_degraded:concept` would go uncaught. The hallucinated-ID gap is low impact (kind-agnostic code, indirectly covered).
**Recommended action:** Either (a) add to AC-C4 a clean-path assertion that no `contradiction_detection_degraded:concept` appears when detection succeeds (cheapest, highest value — directly guards the new CS-9 string), and (b) add a one-line note to the spec that the hallucinated-ID filter is kind-agnostic and intentionally not re-mirrored; or accept the gap with that documented rationale. Not blocking — these are belt-and-suspenders on kind-agnostic code, but the clean-path concept assertion is cheap and closes the only behavior unique to CS-9 that is currently asserted in one direction only.

### ADV-2 — AC-C9 PATCH-count assertion ("4 PATCHes") is a brittle, implementation-coupled check; ensure it is paired with the relation-key intent.
**Description:** AC-C9 mirrors entity `test_multiple_peers_contradict` and asserts `contradictions_detected == 2` plus "4 PATCHes". The spec correctly states the *intent* — guard against reading candidates from the wrong relation key (`wiki_relations` vs `wiki_related`) while writes still land. That intent is the meaningful assertion; a raw PATCH count can pass or fail for incidental reasons (e.g. a future change to dedup or rollback PATCH shaping) without reflecting the candidate-key bug it targets.
**Impact on reliability:** Low. The test is meaningful as specified, but the PATCH count alone is not self-documenting about *what* it protects.
**Recommended action:** The test worker should assert candidates were sourced from `wiki_related` (e.g. that `get_object`/prompt candidates correspond to the `wiki_related` peer ids), not only the bidirectional PATCH count, so the test fails for the right reason. The spec's docstring intent should carry into the assertion, not just the comment.

---

## On the specific questions posed

1. **Do AC-C1..C10 fully mirror the entity suite?** Substantially yes. 6 of 9 entity tests mirrored, 1 correctly omitted (shared prompt), 2 net-new concept-only tests added for the genuinely new dispatch logic, plus an empty-definition edge case. The only un-rationalized omissions are folded into ADV-1 and are low-risk (kind-agnostic code).

2. **Is the regression argument airtight?** Yes, at the level that matters. The `**kwargs` stub touch-up + bare-entity-warning (CS-9) is sufficient: the stub list is complete (6/6 verified), and the one entity assertion that touches the warning (`test_detection_degraded:1501`) is a membership check that the bare string still satisfies. The two real-call unit tests (`:1620`, `:1688`) genuinely need no change — verified they pass `detect_contradictions` positionally with no `kind`, which the keyword-only `kind="entity"` default accommodates.

3. **Is the SF-1 trap mitigation adequate and clearly flagged?** Yes. It is flagged three times (CS-6 inline warning at spec:153-156, a dedicated Test Plan subsection at :258-262, and the regression table). The mechanism (`except Exception` at `ingest.py:925` swallows the `TypeError`) is correctly described, and the fix (one-line `**kwargs` per stub) is unambiguous with a complete line-anchored list. This is the spec's strongest section.

4. **Is AC-C7 / SG-7 precise enough?** Yes. The asserting surface (candidate JSON to `_call_ollama_prompt`), the mock shape (unwrapped dict, mirror `test_hallucinated_id_filtered`), and the dual assertion (definition present AND `wiki_facts` absent) are all specified and match the real code path at `ingest.py:567-571`. Low risk of the worker getting the mock shape wrong.

5. **Do new tests fail before implementation?** Required explicitly (spec:339-341) for AC-C1, AC-C3..C10. Satisfied.

6. **Are the deferrals (SG-4 B-side rollback) justified?** Yes. The B-side rollback gap is genuinely pre-existing — the entity suite has no such test, `_write_contradiction_links` is kind-agnostic and locked (untouched by #325), so a concept B-side rollback test would assert behavior #325 does not alter. Deferring it to the SG-1 follow-up leaves no *new* regression risk; it is pre-existing debt, correctly labeled as a known coverage gap rather than a #325 requirement. Acceptable.

---

## Bottom line

**SIGN-OFF on the spec's Test Plan for the confined core.** The test strategy will validate the feature and guard the entity regression. AC-3 is met. The single highest-risk item (the silent-`TypeError` stub trap) is correctly diagnosed, completely enumerated, and adequately mitigated. ADV-1 (add a clean-path "no `:concept` warning" assertion to AC-C4) is the one improvement I'd want the test worker to pick up — it is cheap and closes the only CS-9-introduced behavior currently asserted in one direction only. Neither advisory blocks advancement.

**Note to CPO/chair:** the literal ticket ACs are fully covered by the core; the lint-surfacing follow-up is correctly out of scope (the BL-R2-1 bootstrap gap is verified — re-bootstrap cannot provision `wiki_concept.wiki_last_reviewed` on an existing space). If Jan folds surfacing back into #325 at Decide, AC-C11 and the new bootstrap-ensure-properties capability re-enter scope and would need their own QA pass (including verification of the unconfirmed Anytype property-link API).
