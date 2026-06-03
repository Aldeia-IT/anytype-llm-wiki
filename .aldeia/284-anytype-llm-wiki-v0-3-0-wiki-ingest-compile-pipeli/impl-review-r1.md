# Implementation Review — v0.3.0 wiki_ingest (Round 1)

**Ticket:** #284 · **Branch:** aldeia/284-anytype-llm-wiki-v0-3-0-wiki-ingest-compile-pipeli
**Reviewers:** Security (agent), Code-quality/correctness (agent), Spec-compliance (agent), Lead inline checks.
**Suite state at review:** `pytest -m "not live"` → 366 passed, 20 skipped, 0 failed; `bandit -r src/` clean; `pip-audit` clean.

## Verdict: NEEDS CHANGES → fix round dispatched

The green non-live suite masks two spec violations the spec-compliance review surfaced (BLOCKING-A/B below). Both are fixable within the spec without breaking the approved non-live contract (the relation fix touches exactly one test — see analysis). Fixing in round 1; re-review in round 2.

## BLOCKING (from spec-compliance review)

### BLOCKING-A — ingest never creates `wiki_concept`; AC#1 structurally unmet (ingest.py:469,485)
Every candidate is created as `type_key="wiki_entity"`. LLM-extracted `concepts` are merged by `_merge_extraction` but created as entities with their definition stuffed into `wiki_facts`; no `wiki_concept`/`wiki_comparison`/`wiki_query` object is ever created, so `wiki_definition`/`wiki_open_questions`/`wiki_dimensions`/`wiki_verdict`/`wiki_question`/`wiki_answer` are never populated by ingest, and AC#1 ("≥1 Entity AND ≥1 Concept") cannot be met. **Fix:** carry a `kind` (entity|concept) on each candidate; heading-derived candidates default to entity; LLM `concepts` → `wiki_concept` with `wiki_definition`. (No non-live test forbids concepts; the mocked ingest tests have no LLM concepts so behavior there is unchanged — the fix manifests on the live AC#1 path.)

### BLOCKING-B — relations created against a non-existent `wiki_relation` type (ingest.py:260-307)
`_create_relation` POSTs `type_key="wiki_relation"`, not in `types_schema.WIKI_TYPES`. Spec §6 step 6 + the verified-live native-backlinks note model relations as bidirectional `wiki_relations`(Entity)/`wiki_related`(Concept) **object-format property** links. Against live Anytype the current approach fails → `relations_created` stays 0, AC#1 bidirectional-relations + the cross-link minimum unmet. The approved AC#13 test (`TestBidirectionalRelationRollback`) encodes the standalone-object model, but it is the ONLY non-live test that issues relation writes (partial-failure/create-side tests yield <2 successful entities → `_derive_relations` produces 0 relations → no relation writes). **Fix:** implement property-based bidirectional relations (PATCH `wiki_relations`/`wiki_related` on both objects; rollback = unset the succeeded side) and rewrite that one test to the property-based mechanism. This aligns impl with the authoritative spec; the test change is documented and flagged for council visibility (it corrects a test that contradicted the spec's relation model).

---

## SHOULD-FIX (address in fix round)

### SF-1 — WikiClient httpx client leak (ingest.py:350)
`wiki_ingest` constructs `client = WikiClient()` but never `.close()`s it; early-return error paths (schema_read_failed, wiki_schema_missing/outdated, invalid_domain_hint) and the normal path all leak the underlying httpx client. `bootstrap.wiki_bootstrap` already wraps in try/finally:close. **Fix:** wrap steps 2–5 in `try: ... finally: client.close()`. (Source: code-quality reviewer; confirmed by lead.)

### SF-2 — Non-SSRF fetch errors fabricate a junk entity (ingest.py:419-424)
The fetch short-circuit only fires for `ssrf_blocked`. `fetch_url` also returns `[DATA ERROR] file_not_found`, `file_read_failed`, `fetch_failed` (fetch.py:181,185,216). These fall through to `_derive_candidates`, hit the headingless fallback, and create a durable `wiki_entity` whose `wiki_facts` is the error string + a Source + a "success" WikiLog. **Fix:** broaden the guard to `if isinstance(markdown,str) and markdown.startswith("[DATA ERROR]"): return _error_result(markdown)`. (Source: code-quality reviewer; confirmed by lead — real bug, no test exercised the file_not_found path through ingest.)

### SF-3 — AC#11 ordering: ollama_model_not_pulled should abort before Source creation (ingest.py:442-458)
Spec AC#11 (§8.1): "Ollama model not pulled → `[CONFIG ERROR] ollama_model_not_pulled` **before Source creation**." Current impl treats the extract() model-not-pulled marker as `extraction_degraded` and proceeds to create the Source. **Fix:** in step 8, if `extracted.get("error","").startswith("[CONFIG ERROR] ollama_model_not_pulled")`, return that CONFIG ERROR before creating the Source. (Won't regress the mocked ingest tests — they return HTTP 201 junk, not 404, so the not-pulled branch never fires there.) (Source: lead inline check.)

## ESCALATED — relation mechanism (spec↔test conflict; gates live AC#1)

### ESC-1 — Relations created as standalone `wiki_relation`-typed objects (ingest.py:260-307)
`_create_relation` POSTs objects with `type_key="wiki_relation"`, a type that is **not** in `types_schema.WIKI_TYPES` (the schema models relations as `wiki_relations`/`wiki_related` **object-format properties** on the Entity/Concept, set on both sides — see spec §"Bidirectional relations" and the master-spec native-backlinks note). Against **live** Anytype, creating an object of an unbootstrapped type fails → every multi-entity ingest would downgrade to `partial` and the live AC#1 gate ("creates ≥1 typed relation") would fail.

**However**, the council-APPROVED AC#13 test (`test_bidi_relation_rollback_on_failure`) encodes the standalone-relation-object model: it returns an id from the first relation-create POST and asserts a **DELETE/PATCH referencing that relation id** on rollback. A property-based relation model (the spec's intent) has no "relation object id" to delete — rollback would be a property-unset PATCH on the entity — and would therefore **fail the approved test**.

This is a genuine inconsistency between the approved spec prose and the approved test contract, predating implementation. The implementation correctly satisfies the approved test (non-live green) but the mechanism will not work against live Anytype.

**Recommendation:** Do NOT silently rewrite the approved AC#13 test in this fix round. Surface to council/Jan at the pre-release live gate (live AC#1/P2/P7 are already deferred there per addendum-post-test-r1 item 9). The council should decide: (a) reconcile to property-based relations + adjust the AC#13 test's rollback assertion, or (b) bootstrap a real `wiki_relation` object type. Tracked in the phase summary + ticket handoff. **Not pipeline-halting** given live gates are deferred by design and non-live suite is green.

---

## SUGGESTIONS (optional; fixer may address the cheap ones)

- S-1 (lead/code-quality): `domain_hint` is validated (AC#10) but never applied to created objects' `wiki_domain_tags`; spec §7.2 calls it "pre-apply". Either wire it onto created objects or drop the "pre-apply" language. No AC requires application.
- S-2 (code-quality): unused `config` import in ingest.py:22 — drop it.
- S-3 (code-quality): PointStruct-building duplicated between `indexer.reindex` and `indexer.reembed_object`; extract a `_embed_and_upsert` helper.
- S-4 (security): `_is_model_not_pulled` over-broad — a 404 mentioning "model" for any reason reads as not-pulled; tighten to `not found`/`pull it first` only.
- S-5 (security): `0.0.0.0` in `_LOCAL_HOSTS` skips the consent banner for `http://0.0.0.0:*` endpoints; harmless (0.0.0.0 routes to localhost) but odd in a "local hosts" set.
- S-6 (lead): `.env.example` now lists `WIKI_UPSERT_THRESHOLD_*` but ingest uses a hard-coded `_UPSERT_THRESHOLD_TITLE = 0.92`; optionally read these from env to match the documented config surface (low priority; no test).

## Clean areas (verified, no findings)
SSRF (resolved-IP categorical, all A/AAAA, IPv4-mapped normalize, per-hop redirect re-check, stream size-cap, bypass-encoding tests); prompt-injection/name-policy + property-value sanitization; credential scrub in startup log and lock payload; consent gate fires on the real entry path before off-machine transmit (HARD GATE 1, with ordering-spy test); per-space lock acquired on entry path (HARD GATE 2, with CI test); AC-L1 (no body/markdown in PATCH; empty-body create); AC-L2 (no type_key filter to search; client-side type filter); empty-body invariant; schema marker Option-a + SF9 single-mechanism guard; wiki_action tags (T1-T5); empty-source shape (AC#8 objects_skipped:[]); partial-status (AC#3); reindex_failed warning (AC#9); patch-decision precheck (AC#15); wiki_schema_outdated (AC-M4); force_reembed_object signature.

## Addendum (post-test-r1) HARD GATE status
1. Consent banner on live path + integration test — **SATISFIED** (TestIngestEntryPathConsentBeforeOffMachine, ordering spy).
2. space_ingest_lock on entry path + CI test — **SATISFIED** (TestIngestEntryPathLock, mocked-boundary).
3. Vacuous-loop guards — create-side guard **ADDED**; update-side guard correctly **OMITTED** as unsatisfiable (the fetch mock returns schema JSON as content → candidate name is the URL → never matches the seeded entity → update path cannot fire; adding `assert update_payloads` would fail the test). Defensible deviation; documented.
4. SSRF resolved-IP + bypass-encoding tests — **SATISFIED** (TestSSRFBypassEncodings: [::1], 0.0.0.0, numeric loopback).
5. Sanitizer placement (chunker) — **SATISFIED** (strip_control_chars in chunker on property values).
6. force_reembed_object(space_id, object_id, obj) — **SATISFIED** (delegates to indexer.reembed_object).
