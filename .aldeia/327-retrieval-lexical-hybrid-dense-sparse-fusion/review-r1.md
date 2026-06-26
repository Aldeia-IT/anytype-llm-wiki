# Spec Review R1 — Lexical/Hybrid Dense+Sparse Fusion (#327)

**Date:** 2026-06-25
**Reviewers:** spec-architecture-reviewer, completeness-reviewer, infra-reviewer + lead consolidation/inline checks
**Spec:** `.aldeia/327-retrieval-lexical-hybrid-dense-sparse-fusion/spec.md`

## Verdict: NEEDS REVISION

Five BLOCKING findings, including a fundamental architecture flaw: the BM25 index lifecycle (module-level state rebuilt only by `_run_reindex`/`reembed_object`) cannot work in the real deployment, because the launchd cron runs `reindex()` in a **separate process** from the long-running stdio MCP server — so the server's index is never refreshed by the cron and (with no lazy build) stays inert after restart. Separately, the RRF fusion never actually fuses (incompatible keys between the two lists), and the filter gate silently drops all BM25 recall under `source_type`/`domain_tags` filters. The feature as specified would deliver little of its intended value while appearing to pass its unit tests.

Lead-verified load-bearing claims:
- `src/anytype_llm_wiki/server.py:346` — `mcp.run(transport="stdio")` (long-lived single process). ✓
- Cron sample `docs/samples/com.aldeia.anytype-llm-wiki-reindex.plist` runs `reindex()` in a throwaway interpreter — separate process from the server. ✓ (D1)
- `src/anytype_llm_wiki/wiki/query.py:1009` — Tier-2 sorts candidates by `c["score"]` descending, so a heterogeneous `score` corrupts the object-cap survival ranking. ✓ (A1/S1)
- `semantic_search_core` (`indexer.py:151-161`) returns only `object_name, object_id, type, heading, text, score` — no `_chunk_id`, no `source_type`, no `domain_tags`, and discards the Qdrant `point.id`. ✓ (B1, B2)

---

## BLOCKING

### BL-1 — RRF fusion key is incompatible between the two lists; fusion never combines the same chunk (arch B1 / completeness M2)
`_bm25_search` keys results on the real Qdrant point id (`str(point.id)` = `uuid5(NAMESPACE_URL, "{object_id}:{i}:{heading}")`), while `hybrid_search_core` keys dense results on a synthetic `f"{object_id}:{heading}:{i}"` where `i` is the *result-list position*. These key spaces can never collide, so a chunk found by BOTH retrievers is stored under two buckets and never gets its reciprocal ranks summed — RRF degenerates to interleaved concatenation and the same chunk can occupy two of the `limit` slots. AC-H2 passes only because it hand-feeds matching `_chunk_id` to both lists, which the real path can never produce. `semantic_search_core` cannot supply the point id today (it reads `r.payload`, discards `r.id`).
**Fix:** Give both lists a single, deterministic, payload-derivable chunk identity carried through the real path. Preferred: have the dense retrieval expose the Qdrant `point.id` (e.g. an internal dense fetch that adds an internal `_point_id`), and key both lists on it. Do NOT use `object_id:heading:position`. Add an end-to-end fusion test (monkeypatch only `_qdrant`/`embed_query`) asserting a dual-retriever chunk outranks single-retriever chunks and appears exactly once.

### BL-2 — Filter gate reads keys the result dicts never populate; all BM25-only recall is silently dropped under `source_type`/`domain_tags` (arch B2 / completeness M1 / infra F2)
`_passes_inline_filters` reads `r.get("source_type")` and `r.get("domain_tags")`, but neither `semantic_search_core` nor `_bm25_search` puts those keys in their result dicts (the data IS in `_BM25Index.payloads`, just not surfaced). Result: when a `source_type` or `domain_tags` filter is active, every BM25-only chunk evaluates as non-matching and is dropped — total loss of the lexical signal exactly in the filtered queries #336 was built for. `wiki_query` Tier-2 reaches the `domain_tags` branch (it threads `domain_tags`), so this is live, not theoretical.
**Fix:** Populate `source_type` and `domain_tags` in `_bm25_search`'s result dict from `idx.payloads[i]`, and have the gate read real values. Add ACs: a BM25-only chunk with matching `domain_tags` survives; with non-matching tag is dropped.

### BL-3 — `score` field is heterogeneous (cosine vs raw BM25); corrupts the Tier-2 object-cap ranking (arch S1 / completeness A1,C1 — escalated to BLOCKING by lead)
After fusion each dict keeps its *original* score: dense chunks carry cosine `[0,1]`, BM25-only chunks carry raw BM25 (often >1). The RRF score that determined order is discarded. `wiki_query` Tier-2 copies `score` into `candidate_entries` and **sorts/caps by it** (`query.py:1008-1009`), so a BM25-only chunk with raw score 2.0 outranks a dense chunk with cosine 0.8 even when RRF ranked the dense chunk higher — the cap can drop the better seed. Escalated to BLOCKING because it silently degrades the production `wiki_query` ranking, not just a cosmetic field.
**Fix:** Return the RRF score from `_rrf_fuse` and set it as the output `score` on every fused dict, so list order and `score` agree and are comparable across signals. Document the cosine→RRF semantics change in §5.1. Add a test with mixed-origin chunks asserting consistent ordering.

### BL-4 — Cron-triggered BM25 rebuild never reaches the server process; index goes stale/inert (infra D1)
`_bm25_index` is per-process module state, rebuilt only inside `_run_reindex`/`reembed_object`. The launchd cron runs `reindex()` in a separate short-lived interpreter; the long-running stdio server's index is never touched. §17's "cron keeps the index fresh" is false. New objects indexed by the cron are dense-retrievable but invisible to BM25 — silent, undetectable recall degradation.
**Fix (couples with BL-5):** Adopt lazy build on first `hybrid_search_core` call when the index is `None`, plus a cheap **cross-process staleness signal** (e.g. a `bm25_corpus_version`/point-count stamp written to `state.json` on every upsert path; rebuild when it changes). This requires revisiting the §3 D3 "eager, no-lazy" decision.

### BL-5 — Cold-start leaves hybrid retrieval inactive indefinitely after a server restart (infra D2)
With no lazy build, after a restart `_bm25_index` stays `None` until an *in-process* reindex/reembed fires. A query-only session (reindex handled by cron) never activates hybrid retrieval — it silently serves dense-only forever while reporting success. Same root cause as BL-4; fixed by the same lazy-build + staleness-stamp change. The §3 D3 anti-lazy rationale ("first query absorbs latency") is weak: §15 estimates build <100ms vs the ~100-500ms embed already on the path.

### BL-6 — `tests/eval/` fixture does not exist and its ownership is unresolved; AC-EVAL is unrunnable (completeness M3)
`tests/eval/fixtures/retrieval_quality_cases.json` and the eval dir do not exist; Open Question #3 leaves curation ownership unanswered. Without it, the ticket's core goal ("keyword-precise queries recall the right Objects") has no runnable validation.
**Fix:** Assign ownership: the implementer creates the fixture in Step 8 with ≥2 verified keyword-precise cases (incl. the #327 reproduction case) before PR. Replace OQ#3 with a concrete completion gate (`uv run python -m pytest tests/eval/ -m live` exits 0). See also BL-7 for the test harness.

### BL-7 — `anytype_enum_fixture` referenced by AC-H10 does not exist (completeness M4)
AC-H10 depends on a pytest fixture defined nowhere in the suite; the test cannot run as written.
**Fix:** Either define `anytype_enum_fixture` in `tests/wiki/conftest.py` (providing the AnytypeReadClient/WikiClient/schema-marker mocks), or rewrite AC-H10 to use the existing `@respx.mock` + `_tier2_list_resp()` pattern from `test_query.py`. Show complete runnable test code.

---

## SHOULD-FIX

- **SF-1 (arch S3 / infra R1):** `reembed_object` gains a full-corpus scroll+rebuild, silently converting its documented O(1) contract (`indexer.py:346`) into O(corpus) on the `wiki_ingest`/`wiki_remember` hot path. Update the docstring AND decide: with the BL-4/BL-5 lazy+staleness redesign, the eager rebuild here can likely be dropped in favor of staleness-stamp invalidation. Resolve OD-327-B in light of the redesign.
- **SF-2 (infra F1):** BM25 build ordering in `_run_reindex` is placed *before* `_save_state`; an exception there aborts after upserts but before state/schema-marker write, re-triggering the forced full backfill every run. Move `_build_bm25_index` to AFTER `_save_state`, and wrap it in try/except at BOTH call sites so a build failure never aborts the upsert/state-write it follows.
- **SF-3 (arch S5):** `_build_bm25_index` nulls a previously-good index on a transient empty scroll (AC-H8 locks this in). Only replace the index when the new corpus is non-empty; leave the prior index intact on empty (log a warning). Distinguish genuinely-empty from transient-empty.
- **SF-4 (arch S4 / completeness M5):** AC-H11's "review and update Tier-2 monkeypatches" is undefined scope. Enumerate exact sites (`grep -n "setattr.*semantic_search_core" tests/wiki/test_query.py tests/wiki/test_query_fetch_paths.py` — ~11 + ~8 sites). Explicitly state `wiki_lint` keeps `semantic_search_core` (out of scope) to prevent over-eager find/replace.
- **SF-5 (completeness A4/C4):** D5 prose ("date filter excludes BM25-only chunks") contradicts §7.3 ("dates not checked inline" → date-only filtered queries let BM25-only chunks through). Resolve the contradiction, make D5/§6.5/§7.3 consistent, and add an AC pinning the chosen date-filter behavior for BM25-only chunks.
- **SF-6 (completeness A2):** The "run AC-EVAL before implementing hybrid" baseline procedure is infeasible (the test imports `hybrid_search_core`, which doesn't exist pre-impl; and calling `hybrid_search_core` already uses BM25, so it isn't a dense baseline). Rewrite: capture the dense baseline via `semantic_search_core` between Steps 4 and 6.
- **SF-7 (completeness A3/C2):** The eval calls both functions with no `types`/`space_id`, not the production `wiki_query` path (which passes `types`). Add `types`/`space_id` to fixture cases and pass them; assert the reproduction case improves individually (not only in aggregate); raise the minimum fixture size (≥5) for statistical validity.
- **SF-8 (completeness C3):** AC-H6 pre-sets `_chunk_id` on the dense list, bypassing the real proxy-assignment path. Revise so the dense input has no `_chunk_id`, forcing the real keying logic and exercising the `_chunk_id not in dense_chunk_ids → _passes_inline_filters` branch. (Resolves alongside BL-1's new keying.)
- **SF-9 (completeness M6):** Steps 1 and 3 have a real runtime dependency (AC-H1 imports `rank_bm25`); they are not parallel. State that Step 1 (`uv add`/`uv lock`) must precede any test importing `rank_bm25`, and that `uv.lock` is a required artifact.
- **SF-10 (infra M1):** All BM25 failure paths are silent; with BL-4/BL-5 the *expected* steady state is silent dense-only. Add a one-line INFO log on successful build (`bm25_index_built chunks=N ms=M`) and a WARN on each fallback (`bm25_fallback: <reason>`), distinguishing "index None" from "BM25 raised". Optionally surface index state (built/None, chunk count) for a health check.

## SUGGESTIONS

- **SG-1 (infra R2):** §15 memory estimate ("<1 MB") understates the full-payload retention in `_BM25Index` (≈2 copies of every chunk text). Re-estimate; store only the fields actually used (`object_id, object_name, type_key, heading, text[:500], space_id, source_type, domain_tags`) rather than the whole payload.
- **SG-2 (arch G3 / completeness E2):** `text.lower().split()` won't split underscore identifiers (`wiki_entity`); include at least one underscore-identifier case in the eval fixture so the D4 deferral is data-driven.
- **SG-3 (arch G1):** Avoid mutating dense result dicts in place to attach the fusion key; use a side map keyed by index/`id()`.
- **SG-4 (completeness E1/E5):** Specify behavior for empty `query` and `limit<=0` (delegate to `semantic_search_core` / guard `if limit<=0: return []`); add a smoke test.
- **SG-5 (infra D3):** State `_build_bm25_index` logs at most one line/build and stays within the existing 10 MB log rotation; never log chunk texts.
- **SG-6 (completeness E3/E4):** Document the missing-`space_id` and delete-between-rebuilds consistency behavior in §6.2/§17.
- **SG-7 (completeness X-ref):** `FakeQdrantClientWithSearch.scroll` mock should match the real keyword-arg call shape; note it explicitly.

---

## What Aligns Well (preserve in the revision)
- `rank-bm25` dependency choice (numpy-only, 8.6 kB) is well-justified vs FastEmbed/onnxruntime; v2 native-Qdrant path correctly deferred with verified mechanics.
- `semantic_search_core` no-filter invariant + #336 OD-B preservation (D1) is clean and verified (AC-H-REG1 stays valid).
- Qdrant-error propagation vs BM25 swallow boundary (D8) matches existing `query.py:682` behavior.
- Aggregate (not per-query) eval metric is a genuine improvement over the research's brittle per-query assertion.
- `_rrf_fuse` edge-case tests (both-empty, one-empty, k=60) are solid.

---

## Required Outcome for R2
All BLOCKING resolved. The BM25 index lifecycle (BL-4/BL-5) needs a genuine redesign — lazy build + cross-process staleness stamp — not a prose patch; D3, OD-327-B, §15, §17 and the relevant ACs must be rewritten consistently. The fusion key (BL-1), filter-gate keys (BL-2), and score semantics (BL-3) must be fixed in the design with end-to-end (not hand-keyed) tests. Eval/test feasibility (BL-6/BL-7) resolved with runnable harness and explicit fixture ownership. Address SHOULD-FIX items or document a concrete rationale for any deferral.
