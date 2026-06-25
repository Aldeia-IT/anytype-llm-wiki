# Spec Review R2 — Lexical/Hybrid Dense+Sparse Fusion (#327)

**Date:** 2026-06-25
**Reviewer:** spec-architecture-reviewer (re-review) + lead consolidation
**Spec:** `.aldeia/327-retrieval-lexical-hybrid-dense-sparse-fusion/spec.md`

## Verdict: APPROVED WITH CONDITIONS (conditions applied inline → spec is APPROVED)

The R2 re-review verified — against the real code — that all seven R1 BLOCKING findings are genuinely resolved in the design, not merely described as resolved:

- **BL-1** Fusion key: both lists key on the shared Qdrant `_point_id` end-to-end; AC-H2b exercises the real keying (monkeypatching only `_qdrant`/`embed_query`, no hand-set keys). ✓
- **BL-2** Filter gate: `_bm25_search` surfaces `source_type`/`domain_tags`; gate reads real values; AC-H6b pins survive/drop. ✓
- **BL-3** Score: output `score` is the RRF score on the fused path, cosine on fallback; AC-H12 proves raw BM25 magnitude can't displace a dual/dense chunk. ✓
- **BL-4/BL-5** Lifecycle: cross-process `bm25_corpus_version` stamp + lazy `_ensure_bm25_fresh` bridges the cron→server boundary; `_build_search_filter` extraction preserves AC-H-REG1. ✓
- **BL-6/BL-7** Eval/harness: tests runnable (no nonexistent fixture); ownership + completion gate concrete. ✓

§18a resolution-table spot-checks (BL-1, BL-3, SF-1, SF-5) matched the spec body — no overclaiming.

No new BLOCKING. The reviewer raised 3 SHOULD-FIX + 2 SUGGESTION, all documentation/test-robustness refinements with zero architectural risk. Per the lead's judgment these were applied inline (no further fixer/re-review cycle warranted):

| ID | Finding | Applied fix |
|---|---|---|
| SF-A | Staleness-stamp skew window in `_ensure_bm25_fresh` | §6.3 now states the monotonic-eventual-consistency / at-most-one-extra-rebuild guarantee; recall never wrong, next bump heals a one-version skew. |
| SF-B | Hybrid may return < `limit` under aggressive filtering | §6.7 documents it as an accepted recall-coverage trade (dense filter-passing hits always present). |
| SF-C | reembed bump test depends on chunk production | Added `assert fake.upserted_points` to `test_reembed_bumps_corpus_version`. |
| SG-α | state read scales with state size | Noted in §6.3; future sidecar split referenced (§19). |
| SG-β | AC-H2b loose `< 0.1` score proxy | Tightened to pin dual-retriever RRF value `≈ 2/61` + strict descending order. |

## Verified-good (preserved)
rank-bm25 choice + v2 deferral; `semantic_search_core` byte-identical invariant via `_build_search_filter` extraction (AC-H-REG1 guard); Qdrant-error propagation boundary (dense call outside the BM25 try/except → `query.py:682` `qdrant_unavailable`); SF-3 transient-empty-scroll handling; aggregate eval metric + per-case `repro-327` assertion.

## Outcome
All findings across R1 and R2 resolved (zero open BLOCKING/SHOULD-FIX). Spec is ready for the Decide gate. Two Open Decisions remain for Jan (OD-327-A v1-vs-v2 architecture; OD-327-B lazy+stamp vs eager — both with a clear lead recommendation of the v1/lazy path).
