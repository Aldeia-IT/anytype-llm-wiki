# Spec Review R1 — Architecture + Infra/Ops — Ticket #287 (v0.6.0 contradiction detection)

**Reviewer:** spec architecture + infra/ops reviewer
**Date:** 2026-06-05
**Spec:** `.aldeia/287-anytype-llm-wiki-v0-6-0-automated-contradiction-de/spec.md`
**Verified against:** `src/anytype_llm_wiki/wiki/{ingest,extraction,lint,remember,types_schema,wiki_client,query}.py`, `src/anytype_llm_wiki/anytype_client.py`, `tests/wiki/{test_ingest,test_lint}.py`

---

## Severity counts

- **BLOCKING:** 3
- **SHOULD-FIX:** 5
- **SUGGESTION:** 4

---

## BLOCKING

### B1 — `read_client` / `AnytypeReadClient` is NOT in scope in `_run_ingest`; spec assumes it is

**Mandate #1.** The spec (LD3, §3.2 hook flow, §3.3 algorithm steps 1/3, §3.4 signatures) passes `read_client: AnytypeReadClient` to `detect_contradictions` and `_write_contradiction_links` and lists it as "in scope" (research.md:40 lists `space_id, client — in scope` but conspicuously omits `read_client`).

Verified: `_run_ingest` (ingest.py:453-590) has only `client: WikiClient`. There is **no `read_client` and no `AnytypeReadClient` instance anywhere in ingest.py**. Confirmed by:
- ingest.py imports (lines 22-32): no `anytype_client` import.
- `grep AnytypeReadClient(` shows construction only in `anytype_client.py`, `query.py:405`, `lint.py:236` — never in ingest.py.
- `remember.py` (the analogue) does NOT use `AnytypeReadClient`/`get_object` at all (grep returned nothing); its `_existing_text` reads the already-resolved `target` dict's `properties[]`, not a fresh GET.

**Impact:** the spec is unimplementable as written — every `read_client.get_object(...)` call in §3.3/§3.4 references an undefined variable.

**Fix:** The spec MUST specify construction + lifecycle. Either (a) construct `read_client = AnytypeReadClient()` inside `detect_contradictions`/`_write_contradiction_links` and `try/finally: read_client.close()` (mirrors `query.py:405`, `lint.py:236`, and the module wrappers `anytype_client.py:76-81`), and drop `read_client` from the signatures; or (b) construct once in `_run_ingest` (with a `finally: close()`) and thread it through. Note `wiki_ingest` already does `client = WikiClient()` … `finally: client.close()` (ingest.py:394/443-444) — a parallel `AnytypeReadClient` lifecycle is the precedent to follow. Add `import` of `AnytypeReadClient` from `..anytype_client` to ingest.py. File evidence: ingest.py:453-459, anytype_client.py:13/61/76-81, lint.py:236.

### B2 — Prompt rendering mechanism is `.replace()`, not `.format()`; spec's `{candidates}` JSON will break if implemented with `.format()`

**Mandate #2 (most important).** The spec §3.3 describes "template substitution (new_claim, peer list)" and the fallback loader uses `{new_claim}` / `{candidates}` placeholders, but never states the substitution call. Verified: the codebase renders prompts EXCLUSIVELY with `str.replace()`, never `.format()` / f-string:
- `extraction.py:161` — `_load_prompt().replace("{source}", markdown)`
- `extraction.py:240-246` — `consolidate` chains four `.replace("{kind}", ...)` etc.

`_call_ollama_prompt` takes a **pre-rendered** string (extraction.py:99-107, docstring: "no `{source}` substitution") — it does no substitution itself.

**Impact:** `{candidates}` is a JSON array containing `{` and `}` braces. If an implementer reaches for `prompt.format(new_claim=..., candidates=json.dumps(...))` — the natural reading of "template-var substitution" — `str.format` will raise `KeyError`/`ValueError` on the braces inside the candidate facts/JSON. This is exactly the "spec made it unimplementable" gap.

**Fix:** State explicitly that rendering uses `str.replace("{new_claim}", new_claim).replace("{candidates}", json.dumps(candidates))` (mirroring `consolidate` at extraction.py:240-246) and that `.format()` MUST NOT be used. File evidence: extraction.py:161, 240-246.

### B3 — `detect_contradictions` calls `_call_ollama_prompt(ollama_base, prompt)` but `ollama_base` has no defined source

**Mandate #2.** §3.3 step 5 calls `_call_ollama_prompt(ollama_base, prompt)`, but `ollama_base` appears in neither the function signature (§3.3) nor the algorithm's earlier steps. `_call_ollama_prompt` (extraction.py:99) requires a `base` arg; callers derive it as `os.environ.get("WIKI_EXTRACT_ENDPOINT") or _ollama_url()` then `.rstrip("/")` (extraction.py:172-173, consolidate at 236-237; identical helper `query._ollama_base()` at query.py:99-105).

**Impact:** undefined variable — function won't run. Also a wire-contract correctness issue: the §3.8 Ollama rows say the path is `{WIKI_EXTRACT_ENDPOINT}/api/generate`, but if `WIKI_EXTRACT_ENDPOINT` is unset the base is `OLLAMA_URL` (`http://127.0.0.1:11434`) — the spec's wire row should acknowledge the fallback.

**Fix:** Specify `base = (os.environ.get("WIKI_EXTRACT_ENDPOINT") or _ollama_url()).rstrip("/")`, or reuse `query._ollama_base()`. Add `_ollama_url` import or define a local helper. File evidence: extraction.py:172-173, 236-237; query.py:99-105.

---

## SHOULD-FIX

### S1 — §3.3 GET-for-`wiki_relations` is redundant; the resolved `target` already carries it

**Mandate #1/#3.** §3.3 step 1 says "GET obj_id via `read_client.get_object` to read `wiki_relations`." But at the hook point the resolved `target` dict (ingest.py:536) already has `properties[]` including `wiki_relations` and `wiki_contradictions` — search results carry full `properties` (confirmed test_ingest.py:835/841 returns objects with `"properties"`, and remember.py's `_existing_text` relies on exactly this). The redundant GET adds a needless Anytype round-trip and contradicts the Resource-Impact count in §4 ("1 GET to read target's wiki_relations").

**Fix:** Read `wiki_relations` (and the target's prior `wiki_contradictions`) from `target["properties"]` via `_existing_text`-style parsing / `_parse_relation_elements`. Reserve `get_object` for **peers** (whose facts are not in hand) only. Update §3.3 step 1 and the §4 call-count accordingly. File evidence: ingest.py:536, test_ingest.py:835/841, query.py:72.

### S2 — Rollback in §3.4 is correct only if `prior_a_list` is the GET-derived list, not the appended one — spec wording is ambiguous

**Mandate #3.** §3.4 step 1 says "GET obj_id → read existing list → append peer_id (dedup)" then step 5 "revert A by PATCHing back prior A-side list." The A/B model in `_write_bidirectional_relations` (ingest.py:321-351) captures `prior_from = list(linked.get(from_id, []))` BEFORE building `new_from`, and reverts to `prior_from`. The spec says "Track `prior_a_list` before the A-side PATCH" (§3.4 bullet) which is correct, but step 1's phrasing ("append peer_id (dedup)") could lead an implementer to capture the post-append list. The prior list MUST be the **GET result before the append**.

Also: because each peer iteration does its own GET, the dedup is correct across runs (idempotency, §6) — but within a single multi-peer run, two peers patching the SAME obj_id sequentially require the second GET to observe the first PATCH (or accumulate in-memory like `linked`). The spec's "GET each time" approach handles this only if the PATCH is durable before the next GET; otherwise the second GET overwrites the first peer link. Recommend an in-memory accumulator on the A-side (obj_id) mirroring `linked` (ingest.py:316) to avoid lost updates.

**Fix:** State that `prior_a_list = _parse_relation_elements(get_object(...).wiki_contradictions)` captured pre-append; and add a per-run accumulator for obj_id's contradiction list so multiple peers don't clobber each other. File evidence: ingest.py:316/321-351.

### S3 — Empty-source `_create_source` caller (ingest.py:477) is not addressed by the `(id, was_resumed)` change

**Mandate #5.** §3.6 / Impl step 2 says update "all callers … (two sites)". There ARE exactly two callers (verified: ingest.py:477 empty-source branch, ingest.py:510 main path). But §3.6 only shows wiring `was_resumed` for the main path (step 9) + WikiLog notes (step 12). The empty-source branch (lines 474-488) calls `_create_source` at 477 and writes its OWN WikiLog at 481-485 with `notes="empty_source"` — it returns at line 488 before reaching step 12. After the signature change, line 477 becomes `result["source_object_id"] = _create_source(...)` which now returns a tuple and will store a tuple into `source_object_id` unless unpacked.

**Fix:** §3.6 must explicitly unpack at line 477 (`sid, _ = _create_source(...)` or include the resumed note in the empty-source WikiLog too). Otherwise `source_object_id` becomes a `(id, bool)` tuple on the empty-source path — a real bug. File evidence: ingest.py:474-488.

### S4 — §3.5 result-key insertion: `_empty_result` shape differs from spec's implied ordering / completeness

**Mandate #5.** §3.5 adds `"contradictions_detected": 0` to `_empty_result()`. Verified `_empty_result` is ingest.py:62-72 and currently has keys: source_object_id, objects_created, objects_updated, objects_skipped, relations_created, wiki_log_id, warnings, status. The addition is fine, but the spec claims the key is "present in all result dicts (zero on … concept path)". Note `_error_result` (ingest.py:75-80) calls `_empty_result()` then mutates — so it inherits the key automatically (good). Confirm tests that snapshot the full result dict (`test_ingest.py` early-return/empty-source assertions) are updated; §7 only mentions `_create_source` return-type test updates, not result-dict-shape tests.

**Fix:** Add to §7 "Existing test changes": any test asserting exact `_empty_result()` keys must include `contradictions_detected`. File evidence: ingest.py:62-80.

### S5 — `list_tags` in §3.8 wire table is inherited (WikiLog tag), NOT exercised by #287's contradiction code paths — misleading contract

**Mandate #4.** The §3.8 table lists `list_tags` as a contract for #287. Verified: #287's NEW code paths are `detect_contradictions` (get_object + ollama) and `_write_contradiction_links` (get_object + update_object). `list_tags` is only called by `_resolve_wiki_action_tag` (ingest.py:230) and `_domain_taxonomy` (ingest.py:369) — both pre-existing WikiLog/domain paths untouched by #287. Listing it as a #287 contract row (with a "landmine" note) implies the new code calls it, which it does not.

**Fix:** Either drop the `list_tags` row from the #287-specific table, or relabel it "inherited (WikiLog tag resolution) — not called by contradiction code." The landmine itself is real and correctly described (property-scoped `/properties/{pid}/tags`, wiki_client.py:127-134); just scope it correctly. File evidence: wiki_client.py:127-134, ingest.py:230/369.

---

## SUGGESTION

### G1 — §7 existing-test claim is inaccurate: `test_contradiction_check_passive` has no `_PASSIVE_CONTRADICTION_NOTE` assertion to remove

**Mandate (lint).** §7 says rename `test_contradiction_check_passive` and "remove assertion that `report["notes"]` contains `_PASSIVE_CONTRADICTION_NOTE`". Verified the actual test (test_lint.py:893-942) asserts ONLY on findings (object_id firing/not-firing). It never references `_PASSIVE_CONTRADICTION_NOTE` or `report["notes"]`, and its detail-string assertion does not check for "PASSIVE". So the test passes unchanged after the lint edits. The rename + a NEW active-notes assertion (AC-3) is fine, but the "remove assertion" instruction is a no-op.

**Fix:** Correct §7 to: "the existing test needs no removal; add AC-3 `test_contradiction_check_active` asserting `report['notes'] == []` and detail has no 'PASSIVE'." File evidence: test_lint.py:893-942.

### G2 — Line-number drift in §3.7 / §1 (minor)

`_PASSIVE_CONTRADICTION_NOTE` is lint.py:**79-83** (✓ spec). `_empty_report` notes is lint.py:**172** (✓). The passive-suffix finding detail is lint.py:**428-429** — the `"(PASSIVE check — see #287)"` literal is on line **429** (✓ spec). Docstring caveats are at lint.py:**20-22** and **211-212** (spec says 211-214 — slightly off, ends at 212). `if tk == "wiki_entity"` is lint.py:**417** (✓). All edits are real and correctly located; only the 211-214 range is marginally wide.

**Fix:** Tighten the §3.7 docstring range to 211-212. File evidence: lint.py:20-22, 79-83, 172, 211-212, 417, 428-429.

### G3 — Schema-version decision (LD2) is CONFIRMED correct

**Mandate #7.** Verified `WIKI_SCHEMA_VERSION = "0.4.1"` (types_schema.py:27). `wiki_contradictions` exists on `wiki_entity` (types_schema.py:95) and `wiki_concept` (111); `wiki_last_reviewed` on `wiki_entity` only (97), absent from concept (105-113). No type/property definition changes are introduced by #287. `resumed_partial_ingest` is written as a free-text `wiki_notes` value (ingest.py:576 → `_write_wikilog` `{"key": "wiki_notes", "text": notes}` at ingest.py:257), NOT a schema property. **Staying at 0.4.1 is correct.** No action; this is a positive confirmation. File evidence: types_schema.py:27/95/97/111, ingest.py:257/576.

### G4 — Failure-mode / resource bounds are sound; one note on degraded-path purity

**Mandate #6.** The call-count model is bounded: `detect_contradictions` issues ONE batched Ollama call (peer list embedded in prompt — §4 correct), plus N peer GETs where N = `len(wiki_relations)` (O(relations), not O(wiki) — correct, no unbounded loop). `_write_contradiction_links` does 1 GET + 1 PATCH per side per peer. The degraded path is genuinely non-blocking: `detect_contradictions` returns `[]` on any exception (§3.3 step 8) and the hook is AFTER the fact PATCH (ingest.py:538-544), so detection failure cannot lose the fact write — consistent with LD3. One caveat: the spec must ensure the `read_client` GETs inside `detect_contradictions` are themselves wrapped so a peer-GET `httpx.HTTPError` returns `[]` rather than propagating (the §3.3 "return [] on any exception" must cover the GET loop, not just the Ollama call). State this explicitly.

**Fix:** Make §3.3 step 8 say "any exception (peer GET, Ollama call, or JSON parse)". File evidence: ingest.py:538-544, extraction.py:99.

---

## Cross-cutting confirmations (no action)

- Wire verbs/paths all verified against source: `search` = **POST** `/v1/spaces/{sid}/search` (wiki_client.py:113, returns `["data"]`); `update_object` = **PATCH** `/v1/spaces/{sid}/objects/{oid}` (wiki_client.py:81); `get_object` = **GET** `/v1/spaces/{sid}/objects/{oid}?format=md` returning `["object"]` (anytype_client.py:44-52); `list_tags` = property-scoped GET (wiki_client.py:127-134). All §3.8 verb/path cells are correct.
- `_call_ollama_prompt` signature `(base, prompt) -> (dict|None, Response|None)` and deterministic opts `_DETERMINISTIC_OPTS` applied automatically (extraction.py:99-152, 42) — §LD4/step 4 claim is correct.
- JSON parse path: `_parse_json_response` reads `response`/`message.content`, tolerates ```json fences (extraction.py:70-89). The contradiction prompt must use `"format": "json"` semantics — automatically applied by `_call_ollama_prompt` (extraction.py:120/142). Correct.
- `_parse_relation_elements` location query.py:72 (✓ spec). Dual-shape (str | {id}) handling confirmed.
- `_existing_text` at remember.py:629-642 (✓ spec); moving to util.py avoids the real circular import (remember imports from ingest, lint imports from both). LD5 is sound.
- `wiki_last_reviewed` is provably never written by the contradiction path: no PATCH in §3.4 touches it, and the only writers of date props are unrelated. Confirmed (mandate #3) — but tests should assert no PATCH payload contains `wiki_last_reviewed` (AC-1 already does).
