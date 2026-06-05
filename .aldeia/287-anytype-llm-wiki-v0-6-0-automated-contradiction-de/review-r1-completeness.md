# Spec Review R1 — Completeness, Ambiguity, Testability (#287 v0.6.0)

**Reviewer:** spec completeness reviewer
**Date:** 2026-06-05
**Spec:** `.aldeia/287-anytype-llm-wiki-v0-6-0-automated-contradiction-de/spec.md`
**Mandate:** completeness, ambiguity, testability ONLY (not design/architecture quality).

## Summary

- **BLOCKING:** 4
- **SHOULD-FIX:** 7
- **SUGGESTION:** 5

**Top issue (BLOCKING-1):** The spec invents a non-existent test file `tests/wiki/test_live.py` for AC-8/AC-9. This repo has no such file — live tests live in existing test files behind `@pytest.mark.live` (e.g. `test_ingest.py:1097`, `test_remember.py:2980`, `test_query.py:2774`, `test_lint.py:1955`). As written, AC-8/AC-9 point implementers at a path that does not exist and breaks the repo's live-test convention.

---

## BLOCKING

### BLOCKING-1 — AC-8/AC-9 reference a non-existent `tests/wiki/test_live.py`
**Where:** §7 AC-8/AC-9 (spec lines 368-369); §8 step 10 (line 404).
**Finding:** `tests/wiki/test_live.py` does not exist. Verified: `ls tests/wiki/` shows no `test_live.py`. Live tests in this repo use `@pytest.mark.live` *inside existing test files* — e.g. `tests/wiki/test_ingest.py:1097`, `tests/wiki/test_remember.py:2980`, `tests/wiki/test_query.py:2774`, `tests/wiki/test_lint.py:1955`. The spec invents both the file and the convention.
**Fix:** Re-target AC-8 (`test_contradiction_smoke`) to `tests/wiki/test_ingest.py` (alongside the existing `@pytest.mark.live` ingest tests) and AC-9 (`test_ingest_slo_observation`) likewise. Remove all references to `tests/wiki/test_live.py` in §7 and §8 step 10.

### BLOCKING-2 — `read_client` (AnytypeReadClient) is required by the new functions but never sourced
**Where:** §3.3 signature (lines 125-137), §3.4 signature (lines 177-183), §3.2 flowchart node I (line 112), §8 step 7 (line 398).
**Finding:** `detect_contradictions(..., read_client)` and `_write_contradiction_links(..., read_client)` both require an `AnytypeReadClient`. That class exists (`src/anytype_llm_wiki/anytype_client.py:13`, `get_object` at :44) — but `ingest.py` never imports it and `_run_ingest` only receives a `WikiClient` (`ingest.py:453-458`; client created at `ingest.py:394`, threaded at :437-438). There is no `read_client` in scope at the hook point. The spec never says where it comes from (who constructs it, who closes it, whether `_run_ingest`'s signature changes). Worse, the §3.2 flowchart node I calls `detect_contradictions` with only `new_facts + obj_id + client` — it drops `read_client` entirely, contradicting the §3.3 signature.
**Fix:** Specify construction/lifecycle: e.g. construct one `AnytypeReadClient()` inside `_run_ingest` (mirroring `lint.py:234-236` and `query.py:405`), thread it to both new functions, and `close()` it in a `finally`. Update the §3.2 flowchart node I to pass `read_client`. Update §8 step 7 to include the read-client wiring.

### BLOCKING-3 — Hook-point data source is inconsistent: `_existing_text(target,...)` vs. fresh GET
**Where:** §3.2 node H (line 110: "`_existing_text` from target"); research.md:46-51; §3.3 algorithm (lines 140-142: GET obj_id via `read_client.get_object` to read `wiki_relations`).
**Finding:** The flowchart says the hook reads existing facts from the in-memory `target` dict (via `_existing_text`), but `detect_contradictions` independently GETs `obj_id` to read `wiki_relations`. The `target` dict comes from `resolve_entity` (`ingest.py:534-536`), whose `properties[]` may NOT contain `wiki_relations` (it is the search/resolve result, not a full `?format=md` GET). Meanwhile `_existing_text` is moved to `util.py` (LD5) specifically so the hook can read existing facts — but `detect_contradictions` is passed `new_facts`, not `existing_text`, and re-GETs the object anyway. So: is `_existing_text` actually used at the hook, or is it dead weight? The two sections describe two different data flows for the same step.
**Fix:** Pick one. Either (a) the hook computes `existing_text` from `target` and passes it in (then `detect_contradictions` does not need to GET obj_id for facts, only for relations), or (b) `detect_contradictions` does all reads via `read_client` and `_existing_text` is NOT needed at the ingest hook at all — in which case LD5's justification ("`ingest.py` needs the same helper") collapses and the move is unmotivated. Resolve and make §3.2/§3.3/research agree.

### BLOCKING-4 — §7 mis-identifies the existing test that must change (passive-note assertion)
**Where:** §7 "Existing test changes required" (line 373); §7 AC-3 (line 363).
**Finding:** The spec says: "`test_lint.py::TestContradictionCheck::test_contradiction_check_passive` — remove assertion that `report['notes']` contains `_PASSIVE_CONTRADICTION_NOTE`". Verified: `test_contradiction_check_passive` (test_lint.py:897) contains NO such assertion — it only asserts findings fire/don't fire (lines 936-941). The actual passive-note assertion lives in a DIFFERENT test: `TestStatusLifecycle::test_wikilog_receipt_written_on_clean_run` at `test_lint.py:1782-1788` (`assert any("passive until v0.6.0" in str(n) for n in notes)`). Removing `_PASSIVE_CONTRADICTION_NOTE` from `_empty_report` (the spec's §3.7 change) will break THAT test, which the spec never mentions. The implementer following §7 will edit the wrong test and ship a broken suite.
**Fix:** Correct §7 to name `TestStatusLifecycle::test_wikilog_receipt_written_on_clean_run` (test_lint.py:1740, assertion at :1782-1788) as the test requiring change (the `"passive until v0.6.0"` notes assertion must be inverted to assert the note is absent). Keep `test_contradiction_check_passive` rename-to-active as a separate, correctly-scoped change.

---

## SHOULD-FIX

### SHOULD-FIX-1 — `contradiction_detection_degraded` warning is never written by any pseudocode
**Where:** §3.2 node J (line 112), §3.5, §6, AC-5 (line 365); the warning string.
**Finding:** Every section states that on LLM/Qdrant failure the result gets a `contradiction_detection_degraded` warning. But `detect_contradictions` (§3.3) "Returns `[]` on any error" and swallows the exception internally (step 8, line 147). If it returns `[]` indistinguishably for "no contradictions" vs "error", the *caller* cannot know to emit the degraded warning. The warning is READ by AC-5 but never WRITTEN by any specified code path — declared-but-unwritten.
**Fix:** Either have `detect_contradictions` return a sentinel/raise on error (and the hook catches it to append the warning), or have the hook wrap the call in try/except and append `contradiction_detection_degraded` on exception. AC-5's monkeypatch raises `httpx.ConnectError`, which implies the hook (not the function) must catch — so §3.3 "Returns [] on any error" directly contradicts AC-5's test design. Reconcile.

### SHOULD-FIX-2 — `_call_ollama_prompt` is called with `ollama_base` but the function param is `base` and no base is in scope
**Where:** §3.3 algorithm step 5 (line 144): `_call_ollama_prompt(ollama_base, prompt)`.
**Finding:** Verified `_call_ollama_prompt(base, prompt)` at `extraction.py:99-101`. `extract`/`consolidate` compute base via `os.environ.get("WIKI_EXTRACT_ENDPOINT") or _ollama_url()` then `.rstrip("/")` (extraction.py:172-173, 236-237). The spec names a variable `ollama_base` that is never defined inside `detect_contradictions` (no such param, no derivation shown).
**Fix:** Specify that `detect_contradictions` computes `base` the same way as `consolidate` (env-or-`_ollama_url`, rstrip), or imports a shared helper. Rename `ollama_base` → `base` for consistency.

### SHOULD-FIX-3 — AC-1 "self-reference" / dedup-against-self edge case unaddressed
**Where:** §3.3 step 7 (filter to candidate set), §3.4, AC-1.
**Finding:** No section handles the case where the LLM returns `obj_id` itself as a contradicting peer (self-reference), or where a peer id equals `obj_id`. `_write_contradiction_links` would then write `obj_id` into its own `wiki_contradictions` and attempt a B-side PATCH to itself. Also undefined: a peer already present in `obj_id`'s `wiki_contradictions` (the dedup path is mentioned for idempotency in §6 line 347, but not whether a *fully-deduped* peer counts toward `contradictions_detected += N` — see SHOULD-FIX-4).
**Fix:** Add an explicit filter in §3.3 step 7: drop `obj_id` from the returned peer set. State self-reference handling in §3.4.

### SHOULD-FIX-4 — `contradictions_detected` increment semantics are ambiguous (dedup vs raw N)
**Where:** §3.5 (line 214: "Incremented by `len(peer_ids)`"); §3.2 node M (line 117: "`contradictions_detected += N`"); §3.4 returns `(links_written, rollback_notes)` (line 194).
**Finding:** §3.5 says increment by `len(peer_ids)` (the input), but §3.4 returns `links_written` (which, after dedup of already-present peers, may be < `len(peer_ids)`). On idempotent re-ingest (§6 line 347, "dedup no-op"), `len(peer_ids)` would be non-zero but `links_written` zero. Which value increments `contradictions_detected`? The flowchart, §3.5, and §3.4 disagree.
**Fix:** Use `links_written` (the deduped count) consistently and make §3.5/§3.2/§3.4 agree. Clarify AC-1 / idempotency expectation accordingly.

### SHOULD-FIX-5 — "multiple peers contradicting one new fact" not covered by any AC
**Where:** §7 AC map; §3.3 returns `list[dict]`; §3.4 takes `peer_ids: list[str]`.
**Finding:** The signatures support N peers, but no AC exercises N>1 (AC-1 is a single peer). The A/B rollback loop over multiple peers (partial success: peer 1 OK, peer 2 B-side fails) is a real edge with `status=partial` semantics, and is untested.
**Fix:** Add an AC (or extend AC-1) covering ≥2 peers, including one mid-loop B-side failure → `status=partial`, prior successful links retained, rollback note for the failed peer only.

### SHOULD-FIX-6 — "peer GET fails mid-loop" path declared in §6 but not tested and not in flowchart
**Where:** §6 (line 343: "Peer GET fails → that peer skipped"); §3.2 flowchart; §7.
**Finding:** §6 states a peer-GET-failure behavior, but §3.4's pseudocode (steps 1-5) does not show a try/except around the peer GET, the §3.2 flowchart has no node for it, and no AC covers it. Declared-in-prose-only behavior.
**Fix:** Add the skip-on-peer-GET-failure handling to §3.4 pseudocode and add a test row (or fold into the AC from SHOULD-FIX-5).

### SHOULD-FIX-7 — §3.7 lint-edit line citations are incomplete/off; an inline comment and a docstring line are missed
**Where:** §3.7 (lines 250-253).
**Finding:** Verified against lint.py:
- `_PASSIVE_CONTRADICTION_NOTE` is at lines **79-83** (spec ✓), but the comment block introducing it spans **76-78** and is not called out for removal.
- `_empty_report` notes at line **172** (spec ✓).
- finding detail at line **429** (spec ✓).
- Docstrings: spec says "lines 20-22 and 211-214"; actual passive references are at line **20** (module docstring), line **212** (`wiki_lint` docstring: "PASSIVE until v0.6.0/#287"), and an inline comment at line **416** ("contradiction_unresolved (High) — PASSIVE; wiki_entity only"). The spec misses line 78 (comment), line 416 (inline comment), and is off on 211-214 vs the actual 212.
**Fix:** List all five surfaces explicitly: docstring line 20, comment 76-78, constant 79-83, `_empty_report` 172, docstring 212, inline comment 416, finding detail 429. (Note: line numbers are pre-edit; instruct implementer to grep `PASSIVE` to catch all — `grep -n "PASSIVE\|passive until" lint.py` returns 20, 78, 79, 172, 212, 416, 429.)

---

## SUGGESTION

### SUGGESTION-1 — `was_resumed` write-path on the empty-source branch is unspecified
**Where:** §3.6 (lines 232-244); §8 step 2 ("two sites: the result assignment and the empty-source early-return path").
**Finding:** Verified `_create_source` has two call sites: `ingest.py:477` (empty-source early return, which writes WikiLog with `notes="empty_source"`) and `ingest.py:510` (main path). §3.6 only shows the main-path unpacking (`source_id, was_resumed = ...`) and the step-12 notes assembly. The empty-source path at :477-484 also calls `_create_source` and writes its own WikiLog with `notes="empty_source"` — the spec does not say whether `resumed_partial_ingest` should be appended there too. §8 step 2 correctly flags both sites for the return-type change, but §3.6 silently drops the empty-source notes question.
**Fix:** State explicitly whether the empty-source WikiLog notes should also carry `resumed_partial_ingest` when `was_resumed` (likely yes, for AC-6 completeness), or document the intentional omission.

### SUGGESTION-2 — `get_object` returns the unwrapped object dict, not `{"object": {...}}`
**Where:** research.md:160-162 ("Response: `{"object": {..., "properties": [...]}}`"); §3.3/§3.4 use the result directly.
**Finding:** `AnytypeReadClient.get_object` returns `resp.json()["object"]` (anytype_client.py:52) — already unwrapped. The research's response note is at the HTTP-envelope level (fine for the respx mock), but a reader could mistakenly index `["object"]` again in `_existing_text`/relation parsing. The spec prose passes the result straight into `_parse_relation_elements(prop.get("objects"))` which is correct (unwrapped), so no bug — but worth a one-line clarification to prevent double-unwrap.
**Fix:** Add a note in §3.3: "`get_object` returns the unwrapped object dict (properties[] at top level)."

### SUGGESTION-3 — `_existing_text` move: confirm no third importer breaks
**Where:** LD5 (lines 68-70), §3.1, §8 step 1.
**Finding:** Verified `_existing_text` is defined at `remember.py:629` and used only at `remember.py:450`. No other module imports it (`grep -rn "_existing_text" src/ tests/` shows only remember.py def + use). Moving to `util.py` and re-importing in `remember.py` is safe. (This confirms the spec's claim — no objection.) Note: `test_remember.py` and `test_util.py` exist; the move should add/relocate any direct unit test.
**Fix:** None required for safety; optionally add a `test_util.py` case for the relocated helper.

### SUGGESTION-4 — AC-2 phrasing ("create branch → no contradiction check") under-specifies the concept path
**Where:** AC-2 (line 362); §3.5 (line 214: "zero on ... concept path").
**Finding:** `contradictions_detected: 0` must hold on three skip paths (create, degraded, concept-on-update per LD1). AC-2 only tests the create path. The concept-on-update skip (entity-only guard, §3.2 node G) — where an entity-type guard prevents detection on a `wiki_concept` update — has no test row, despite being a distinct branch.
**Fix:** Add a test (or AC-2 sub-case) asserting a concept *update* skips detection and yields `contradictions_detected: 0`.

### SUGGESTION-5 — `prior_a_list` / rollback-notes variables are internally consistent (no defect) — confirm naming in impl
**Where:** §3.4 (lines 191-202).
**Finding:** Checked the declared variables: `prior_a_list` (written before A-side PATCH, read on B-side failure to revert) — both written and read ✓. `rollback_notes` returned and consumed by the hook into `result["warnings"]` (§3.4 line 204) ✓. `links_written` returned and read by §3.5 (modulo SHOULD-FIX-4) ✓. `was_resumed` written by `_create_source`, read in step 12 ✓. No declared-but-unused variable found in this set. The A/B pattern mirrors `_write_bidirectional_relations` (verified at ingest.py:296-351; `_patch_relation` at :287-293).
**Fix:** None — recorded as a clean check.

---

## Cross-cutting confirmations (verified against code)

- `_existing_text` at `remember.py:629` — confirmed; only importer is remember.py itself (safe to move). ✓
- `_create_source` returns `str | None` (`ingest.py:615`), TWO call sites (`:477`, `:510`) — spec's "two sites" is correct. ✓
- `tests/wiki/test_live.py` — **does NOT exist**; convention is `@pytest.mark.live` in existing files. ✗ (BLOCKING-1)
- `_parse_relation_elements` at `query.py:72` — confirmed. ✓
- `AnytypeReadClient` / `get_object` at `anytype_client.py:13/44` — exists, but not wired into ingest.py. (BLOCKING-2)
- `_call_ollama_prompt(base, prompt)` at `extraction.py:99` — param is `base`, not `ollama_base`. (SHOULD-FIX-2)
- lint passive surfaces via `grep -n PASSIVE lint.py`: 20, 78, 79, 172, 212, 416, 429. (SHOULD-FIX-7)
- passive-note test assertion at `test_lint.py:1782-1788` in `test_wikilog_receipt_written_on_clean_run`, NOT in `test_contradiction_check_passive`. (BLOCKING-4)

## AC ↔ Test coverage gaps (testability)

- Every AC-1..AC-9 has a test row in §7. ✓ (mapping is 1:1)
- No test row lacks an AC. ✓
- BUT: AC-8/AC-9 rows point at a non-existent file (BLOCKING-1); AC-5's mock design (raise) contradicts §3.3's "returns []" (SHOULD-FIX-1); the concept-on-update skip and the N>1 / mid-loop-failure / peer-GET-fail edges have no AC (SHOULD-FIX-5, -6, SUGGESTION-4).
- AC-7 (doctor) and AC-9 (SLO print) are non-functional/informational; acceptable per E1/DI-2 but AC-9 cannot fail meaningfully — flagged as "informational only" in the spec itself (acceptable).
