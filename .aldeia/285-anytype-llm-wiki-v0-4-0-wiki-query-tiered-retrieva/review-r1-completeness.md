# Completeness + Correctness Review — wiki_query v0.4.0 (IMPL R1)

**Verdict: APPROVED WITH CONDITIONS**

**Scope:** `git diff 6975fff HEAD` (3-commit impl). Reviewed the full diff + actual code paths (`wiki/query.py`, `indexer.py`, `server.py`, `cli.py`, `config.py`, `prompts/synthesis.md`, docs, tests).

> Note: this file previously held the *spec-phase* completeness review (NEEDS REVISION, B1–B4). Those four blockers (status rules, `error` field, CI reindex backstop, zero-candidate path) were all resolved in the final spec and are confirmed satisfied by this implementation. This document supersedes it with the impl review.

**Test status:** `514 passed, 25 skipped, 2 xfailed` (full non-live suite, run during review). The 5 query-test skips are respx-0.23.1 route-ordering artifacts re-covered behaviorally in `tests/wiki/test_query_fetch_paths.py` (60 passed there).

## Counts

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| MAJOR | 1 |
| MINOR | 3 |

No correctness defect in the highest-risk areas (N1 relation integrity, Decision 2 filter, tier boundary, file-back gate). The single MAJOR is a QueryResult-contract divergence on the synthesis-error path that the council-approved tests do not pin.

---

## AC → Satisfied/Gap Table

| AC | Topic | Status | Evidence |
|----|-------|--------|----------|
| 1 | Tier 1 < 200 | SATISFIED | query.py:498-499; boundary test |
| 2 | Tier 2 >= 200 | SATISFIED | query.py:499,506 |
| 3 | Boundary 199/200/201 + custom 99/100 | SATISFIED | `count >= threshold` query.py:499; test_query.py:455-459 |
| 4 | Answer + cited deeplink | SATISFIED | query.py:629-639; `_object_deeplink` |
| 5 | Multi-type fix + single-type compat | SATISFIED | `semantic_search_core` nested `Filter(should=...)` in `must`; `embed_query` imported (indexer.py:13); client via `_qdrant()`; server delegates; multi/single tests pass |
| 6 | File-back gate (POST+PATCH, suppress, override, sentinel) | SATISFIED | `_maybe_file_back` query.py:839-945; SF1 gate line 854 |
| 7 | Compounding (B10) | SATISFIED | mocked backstop + README/known-limitations #284 note |
| 8 | Neighborhood cache + dedupe | SATISFIED | `_fetch_cached` per-run cache; SF3 contributing set |
| 9 | QA#25 schema outdated before write | SATISFIED | query.py:464-472 (schema derived from enum, returns before any write) |
| 10 | QA#30 patch-decision before any write/Qdrant | SATISFIED | query.py:421-432 (first, no network) |
| 11 | Content-injection defense + name redaction | SATISFIED | `_build_synthesis_prompt` single `<context>` fence + DATA preamble (synthesis.md); `_safe_object_name`→`[REDACTED]`+`synthesis_name_rejected` |
| 12 | Qdrant-down fallback | SATISFIED | query.py:527-542; at-threshold `[API ERROR] qdrant_unavailable` |
| 13 | filterexpression_fallback > 500 | SATISFIED | query.py:489-496 (also logged to operator stream) |
| 14 | Failure modes / status table | SATISFIED* | anytype-down/partial/not-pulled/ollama-down all mapped; *see MAJOR-1 + MINOR-2 |
| 15 | Zero-candidate (B11) | SATISFIED | query.py:553-563 returns before `synthesize`; synthesis-not-called test passes |
| 16 | Relation integrity (N1/SF4/SF5/SF11) | SATISFIED | see N1 analysis below |
| 17 | Config validators reject 0/neg | SATISFIED | `_positive_int`; six resolvers; test covers SYNTH_MAX_* |
| 18 | SSRF tripwire | SATISFIED | no user URLs fetched; test passes |
| 19 | CLI + server registration, no shadowing | SATISFIED | `wiki-query` in SUBCOMMANDS; `wiki_query` registered; not-shadowed test |
| 20 | Mocked < 5s | SATISFIED | test present; suite runs in ~1s |

---

## Highest-Risk Verification (PASS)

**AC#16 / N1 relation integrity — CORRECT.**
- `_write_bidirectional_relations` is NOT imported or called by `query.py` (query.py imports only `_cmp_versions, _resolve_wiki_action_tag, _write_wikilog` from ingest). No full-overwrite reuse.
- Reciprocal back-reference uses explicit READ-MERGE-WRITE: query.py:924-944 — fresh `_refetch_for_writeback` (NOT the per-run `cache`), `_relation_objects_for_key` (dual-shape parse), `merged = list(dict.fromkeys(prior + [query_id]))` (union, order-stable), then `update_object`.
- `_refetch_for_writeback` query.py:818-836 calls `read_client.get_object` directly — a fresh write-time read, not the cache. Confirmed.
- Forward `wiki_drew_from` (query.py:911-916) is the only plain overwrite, on the freshly-created Query object, targeting `cited_ids` = cached/fetched `object_id`s, never titles. Confirmed; pinned by `test_drew_from_uses_cached_ids_not_titles`.
- N1 merge test (`test_query_fetch_paths.py::TestReciprocalReadMergeWriteReplacement`) exercises a NON-EMPTY prior `['e1','e2']` distinct from the enumeration snapshot — satisfies the post-test addendum item-2 binding condition (merge is not vacuous; no silent re-introduction of the N1 clobber).
- SF4 deleted-cited (404 at write) → drop + `cited_object_gone` + `partial`; if all vanish, skip create — query.py:870-883.

**Decision 2 — CORRECT.** `indexer.semantic_search_core` builds `must=[space_id?, Filter(should=[type conditions])]`; `min_should` not used; client via `_qdrant()`; `embed_query` imported into indexer namespace (addendum C1/item-1 honored). Single-type backward-compat preserved (server tool delegates with unchanged signature).

**Tier selection — CORRECT.** `tier2 = count >= threshold` (inclusive at 200). Boundary tests pin 199/200/201 + custom 99/100.

**Config (addendum item-5) — CORRECT.** Six resolvers (`index_threshold`, `file_back_min_sources`, `file_back_min_words`, `synth_max_input_tokens`, `synth_max_objects`, `synth_max_object_tokens`) + `extract_max_input_tokens`; six `.env.example` vars; `_positive_int` rejects 0/negative.

**Docs/operational (addendum items 3,4 — no test backstop, read directly) — SATISFIED.** README quick-start has bootstrap→ingest→query with explicit `--file-back`; "How it works" covers tiered/threshold rationale, compounding loop, and reindex-latency caveat; `docs/known-limitations.md` §7 reindex entry present; WIKI_EXTRACT_TIMEOUT 600s documented-ceiling decision + `_maybe_log_slow_synthesis` >60s signal (query.py:176-185) with a finite `httpx.Timeout`; `_log_error` + filterexpression_fallback surfaced to operator logger (query.py:496, 696-709); file-back amplifier security note in README + CHANGELOG + module docstring.

---

## Findings

### MAJOR-1 — Synthesis-error return leaves non-empty `answer` and populated `sources_consulted`, diverging from the QueryResult error contract
- **File:** `src/anytype_llm_wiki/wiki/query.py:626, 639, 642-654`
- **Category:** Spec Compliance / Correctness
- **Spec:** spec.md:240 — *"On any error return, `answer` is `""`, `sources_consulted` is `[]`, `filed_back` is `false`."*
- **Issue:** On the synthesis-error path, `result["answer"]` is left as the `[CONFIG ERROR]`/`[API ERROR]` sentinel string (assigned line 626) and `result["sources_consulted"]` is populated (lines 629-639) before the error block returns at line 654. The error block sets `error`, `error_category`, `status=error`, `filed_back=False` but does NOT reset `answer` to `""` or `sources_consulted` to `[]`. A consumer reading the documented QueryResult schema sees a non-empty `answer` (the raw sentinel) and non-empty `sources_consulted` on a `status=error` return — contradicting the contract. The other error returns (patch/schema pre-check, anytype-down, qdrant-down) correctly derive from `_empty_result()` and satisfy the contract; only the synthesis-error path diverges.
- **Why it slipped:** `test_synthesis_model_not_pulled_config_error`, `test_synthesis_ollama_down_api_error`, and `test_file_back_suppressed_on_synthesis_error` assert only `error`/`error_category`/`filed_back is False` — none asserts `answer == ""` or `sources_consulted == []`. Genuine undocumented divergence, not a test failure.
- **Recommendation:** In the synth-error block before `return _log_error(result)`, set `result["answer"] = ""` and `result["sources_consulted"] = []` (the sentinel detail is preserved in `result["error"]`).

### MINOR-1 — Cited object fetched twice during file-back (redundant fresh read)
- **File:** `src/anytype_llm_wiki/wiki/query.py:874 and 928`
- **Category:** Performance / Simplification
- **Issue:** `_maybe_file_back` calls `_refetch_for_writeback` once per cited source in the SF4 drop loop (line 874, for the type) and again per surviving entity/concept in the reciprocal loop (line 928, for prior relations). Each is a fresh `get_object`. For a 3-source file-back, up to ~6 write-time reads where 3 would do. Functionally correct (both intentionally non-cached fresh reads), but the first read already returns the full object including relations.
- **Recommendation:** Carry the object dict from the SF4 loop into `cited_entries` and reuse it for `_relation_objects_for_key`. Non-blocking.

### MINOR-2 — Schema pre-check failure writes no WikiLog, diverging from the spec status table (test-vs-spec tension; test is authoritative)
- **File:** `src/anytype_llm_wiki/wiki/query.py:453-472` (returns via `_log_error`, no WikiLog)
- **Category:** Spec Compliance (documented tension)
- **Issue:** The status table (spec.md:387) says pre-check fail → "WikiLog? yes (if Anytype up)". The patch-decision pre-check fires before any network call, so no-WikiLog is correct there. The schema pre-check fires AFTER `list_objects` succeeds (Anytype IS up), so the table implies a WikiLog should be written — but the code writes none. This matches the council-approved `test_pre_check_schema_outdated_fires_before_write` / `test_pre_check_schema_missing_fires_before_write`, which assert NO POST at all. The code conforms to the authoritative test; the spec table is the stale party.
- **Classification:** MINOR. Per scope instructions, flagged given the test is the authoritative contract and the code matches it. Recommend a one-line spec-table correction (schema pre-check → "no"); no code change.

### MINOR-3 — Unreachable `count < threshold` Qdrant-down branch (self-documented no-op)
- **File:** `src/anytype_llm_wiki/wiki/query.py:528-531`
- **Category:** Dead Code
- **Issue:** Inside `if tier2:`, the except handler checks `if count < threshold:` — but `tier2 == (count >= threshold)`, so this branch never executes (the code comments it as "Unreachable … but keep guard"). This is a defensive no-op, not an added-but-uncalled function, so the MAJOR dead-code rule does not apply. Below-threshold Qdrant-down fallback is handled by never entering Tier 2 (the `if not tier2:` Tier-1 path); the QA-13 `count=199` silent-fallback test passes.
- **Recommendation:** Optional — drop the unreachable branch and unconditionally raise `qdrant_unavailable` inside `if tier2:`. Non-blocking.

---

## Cross-Reference / Wire-Contract Checks (PASS)

- All reused helpers exist with matching signatures: `_resolve_wiki_action_tag` returns `(tag_id, degraded)` (code unpacks correctly), `_write_wikilog` keyword-only (code matches), `_cmp_versions`, `read_patch_decision`, `scrub_credentials`, `strip_control_chars`, `sanitize_name` (returns `None` on reject — code handles), `WIKI_TEXT_PROPERTY_KEYS` (chunker), `_DETERMINISTIC_OPTS`/`_is_model_not_pulled` (extraction).
- `_call_ollama_synthesis` omits `format: json`, reads raw `response`/`message.content`, finite `httpx.Timeout(connect=5, read=extract_timeout(), …)` (never `None`). Sentinel taxonomy verbatim per spec.
- WikiLog written on qdrant-down-at-threshold (query.py:536) and synthesis-error (query.py:648); skipped only when Anytype enumeration fails (query.py:447) — matches SF9 + status table.

## What's Done Well

- N1 relation-clobber avoidance implemented exactly as the R2 correction specified (explicit read-merge-write, fresh write-time read, no `_write_bidirectional_relations` reuse), and the replacement test exercises a real non-empty prior set — the single highest-risk item is correct and non-vacuously tested.
- Decision 2 nested-filter, `_qdrant()` factory, and `embed_query` import all honor the post-test addendum's binding monkeypatch conditions.
- Doc/operational ACs with no test backstop are all materially present and substantive (README, known-limitations §7/§8, CHANGELOG, .env.example, slow-synthesis log, operator-log surfacing, amplifier note).
- Skipped tests are justified (respx version artifact) and re-covered behaviorally in a sibling file; no core AC left uncovered.

## Condition to clear APPROVED WITH CONDITIONS → APPROVED
Resolve MAJOR-1 (reset `answer`/`sources_consulted` on the synthesis-error return to match the documented QueryResult error contract). MINOR-1–3 optional.
