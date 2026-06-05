# Spec Review R1 — anytype-llm-wiki v0.6.0 contradiction detection (#287)

**Date:** 2026-06-05
**Reviewers:** completeness, architecture+infra, security (agent team) + lead consolidation & spot-checks
**Spec:** `.aldeia/287-.../spec.md` (442 lines, 9 ACs)
**Verdict:** **NEEDS REVISION** — 7 BLOCKING, 6 SHOULD-FIX, 3 SUGGESTION.

The spec's structure, altitude, scope boundary (#289→#287), wire-contract pinning, and
fold-in dispositions are sound. The blocking issues are **implementability gaps and
internal incoherences**, not an altitude/decomposition problem. A single focused fix
round should close them. Two of the blockers (BL-1, BL-2) were independently flagged by
both technical reviewers and confirmed by lead spot-check against the code — high confidence.

---

## BLOCKING

### BL-1 — `read_client` is threaded everywhere but never exists in `_run_ingest`
Both reviewers; lead-confirmed. `_run_ingest` (ingest.py:453) holds only a `WikiClient`.
`WikiClient` has **no `get_object`** (methods: create/update_object, search, list_objects,
list_properties, list_tags — wiki_client.py:53-136). The read-plane is `AnytypeReadClient`
(`..anytype_client`), constructed as `AnytypeReadClient()` in lint.py:236 and query.py:405
with a `try/finally: read_client.close()` pattern.
**Fix:** Construct an `AnytypeReadClient()` once in `_run_ingest` (mirror query.py:405,
with `finally` close), add the import, and thread it to `detect_contradictions` /
`_write_contradiction_links`. Update §3.2 flowchart (it drops `read_client` from the call),
§3.3/§3.4 signatures, and §8 step 7 to construct + close it.

### BL-2 — Prompt rendering must be `str.replace()`, not `.format()`
Both reviewers; lead-confirmed (extraction.py:161, 240-246 use `.replace()` exclusively).
The spec's "template-var substitution" of a `{candidates}` JSON blob would raise under
`.format()` because the JSON contains `{`/`}`. **Fix:** §3.3 must mandate `str.replace()`
with explicit sentinel tokens (e.g. `{{NEW_CLAIM}}` / `{{CANDIDATES}}` chosen to not
collide with JSON braces) and state the rendering call mirrors extraction.py:240-246.

### BL-3 — Source of the *target's* existing facts/relations is incoherent (§3.2 vs §3.3)
Completeness B-3. §3.2 reads existing facts from the in-memory `target` dict
(`_existing_text`), §3.3 step 1 does a fresh GET on `obj_id` for `wiki_relations`. They
contradict, and the redundant GET undermines LD5's rationale. Lead-confirmed: `resolve_entity`
returns `target` = the search-result object (ingest.py:184-200), which carries `properties`
(remember.py's `_existing_text` already relies on this). **Fix:** Use the in-memory `target`
dict for BOTH the target's `wiki_facts` and its `wiki_relations` (no GET on the target).
Reserve `read_client.get_object` for **peer** objects only (read peer `wiki_facts` for the
prompt, and peer `wiki_contradictions` before the B-side merge). Update §3.3 algorithm and
the wire-table `get_object` note to say "peer reads only".

### BL-4 — §7 names the wrong test for the passive-note removal
Completeness B-4. The passive-note assertion the impl must update is **not**
`test_contradiction_check_passive`; the real receipt assertion is in
`test_lint.py` (~`test_wikilog_receipt_written_on_clean_run`, lines ~1782-1788). Misnaming
will lead the implementer to ship a broken suite. **Fix:** The spec must instruct the impl
to `grep -rn "_PASSIVE_CONTRADICTION_NOTE\|PASSIVE check" tests/` and update **every**
asserting site (the #172 SF-18 "fix every occurrence" rule), and name the correct test(s)
in §7. Re-verify exact names/lines during the fix.

### BL-5 — AC-8/AC-9 reference a non-existent `tests/wiki/test_live.py`
Lead-seeded, completeness-confirmed. The repo has no `test_live.py`; live tests use
`@pytest.mark.live` inside existing files (test_ingest.py, test_lint.py, test_remember.py,
test_query.py). **Fix:** Relocate AC-8/AC-9 to live-marked tests in existing files
(e.g. `tests/wiki/test_ingest.py::test_contradiction_smoke` with `@pytest.mark.live`).

### BL-6 — `_create_source` tuple change breaks the empty-source call site
Architecture S3. Changing `_create_source` to return `(id, was_resumed)` breaks callers
that expect a bare value. Reviewers cite two sites; one (empty-source early path, ~ingest.py:477)
is not unpacked in the spec. **Fix:** §3.6/§8 step 2 must update **both** call sites; the
fix worker must `grep -n "_create_source(" src/` and unpack the tuple at every site.

### BL-7 — `ollama_base` is undefined in `detect_contradictions`
Architecture B3. The function calls `_call_ollama_prompt(ollama_base, ...)` but never
derives `ollama_base`. Real callers use `WIKI_EXTRACT_ENDPOINT or _ollama_url()`
(extraction.py). **Fix:** §3.3 must show the derivation explicitly.

---

## SHOULD-FIX

### SF-1 — `contradiction_detection_degraded` warning is read by AC-5 but never written
Completeness + architecture. §3.3 swallows errors and returns `[]`, so "no contradictions"
and "detection failed" are indistinguishable and AC-5 is untestable. **Fix:** Wrap the
detection call in the hook (caller); on exception append `"contradiction_detection_degraded"`
to `result["warnings"]`. Either let `detect_contradictions` raise on hard failure (caller
catches) or have it return a sentinel — pick one and make AC-5 assert the warning is present.

### SF-2 — `contradictions_detected` increment is ambiguous (`len(peer_ids)` vs `links_written`)
§3.5 says `len(peer_ids)`; §3.4 returns deduped `links_written`. **Fix:** Increment by the
actual deduped `links_written` returned by `_write_contradiction_links`; make §3.4/§3.5 agree.

### SF-3 — Redundant target GET (folds into BL-3)
Drop the target GET; use `target`. (Listed separately for traceability.)

### SF-4 — `list_tags` row in the wire table is misleading
Architecture S5. `list_tags` is inherited WikiLog/tag-resolution code, not a #287
contradiction path. **Fix:** Mark it "inherited — not new to #287" or drop it, so the test
phase does not over-mock. Keep the landmine note as a general caution if retained.

### SF-5 — Anti-injection preamble must cover the fallback prompt; §5 claim is inaccurate
Security SF1. `{new_claim}`/`{candidates}` carry attacker-influenced LLM-summarized source
text (sanitize_property_value strips only control/bidi chars — util.py:82), so the
anti-injection preamble is load-bearing. **Fix:** Require the preamble in BOTH
`prompts/contradiction.md` AND the `_load_contradiction_prompt()` OSError fallback; add a
preamble-presence test; correct §5's "system-controlled … not raw external content" wording.

### SF-6 — Remote-extraction disclosure understated
Security SF2. When `WIKI_EXTRACT_ENDPOINT` is remote, detection now also ships **peer
objects'** `wiki_facts` (content from other prior sources) off-machine — a broader data class
than #284's single-source extraction. **Fix:** §5 must state this accurately; document the
consent decision (existing gate covers the egress mechanism, but the disclosure scope widens).

---

## SUGGESTION

- **SG-1** Scrub `{exc}` in the `contradiction_rollback` note to exception type / short
  message, not a raw httpx response body (security).
- **SG-2** Make the hallucinated-ID candidate-set filter (§3.3 step 7) an explicit security
  invariant with a negative test (peer id not in candidate set is dropped).
- **SG-3** Add explicit edge-case ACs/tests: self-reference guard (`peer_id != obj_id`),
  multiple peers contradicting one new fact, and peer already present in `wiki_contradictions`
  (dedup no-op). Completeness flagged these as uncovered.

---

## Positive confirmations (lead spot-check)
- Wire verbs/paths in §3.8 are correct: `search`=POST, `get_object`=GET `?format=md`,
  `update_object`=PATCH, `list_tags` property-scoped. (Verified vs wiki_client.py.)
- LD2 (stay at schema 0.4.1) is correct — no type/property definition changes;
  `resumed_partial_ingest` is a `wiki_notes` string value.
- `_existing_text` is at remember.py:629 with a single importer — safe to move to util.py (LD5).
- `_call_ollama_prompt(base,...)`@extraction.py:99 and `_parse_relation_elements`@query.py:72 confirmed.
- Scope boundary #289→#287, Hermes policy quote, and entity-only rationale are accurate.
