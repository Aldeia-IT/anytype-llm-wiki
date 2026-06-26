# Implementation Review — #327 Hybrid Dense+Sparse Fusion (Round 1)

**Date:** 2026-06-26 · **Reviewer:** impl lead (synthesis) + agent team (security-reviewer, performance-checker, code-simplifier) · **Branch:** aldeia/327-retrieval-lexical-hybrid-dense-sparse-fusion

**Verdict: APPROVED.** No CRITICAL/MAJOR findings. The implementation is faithful to the
approved spec (§5–§7) and passes the full committed test contract (757 passed, 29 skipped,
2 xfailed; all #327 ACs H1–H14, H-REG1, QA-3, QA-4, CSO-1 green; Tier-2 caller switch green).
Independently re-run by the lead. All MINOR cleanups applied inline.

## Scope reviewed
`git diff 30a4298..HEAD` on `indexer.py`, `server.py`, `wiki/query.py` (+ test retargets,
docs, dep). Reviewers were told the spec is authoritative and v2 (native Qdrant sparse) is
explicitly deferred.

## Security (security-reviewer) — CLEAN
- **Cross-space isolation (CSO-1): PASS.** `_bm25_search`'s `space_id` gate is symmetric with
  the dense path; the only predicate divergence (`if space_id:` vs `space_id is None`) makes BM25
  strictly *more* restrictive on empty-string, never a leak. Post-fusion gate correctly omits a
  space recheck (already enforced pre-fusion). Verified against the `test_bm25_cross_space_exclusion` path.
- **Post-fusion filter gate: PASS.** Applied only to BM25-only chunks; dense chunks correctly
  exempt; date-active drops BM25-only; domain_tags ANY-overlap matches Qdrant MatchAny semantics.
- **state.json trust channel (CSO-2): PASS.** Version stamp is `int(...)`-coerced on read/write,
  used only in an integer equality compare — no eval/interpolation/path derivation. Worst case is
  a redundant rebuild / dense-only fallback. Matches the §17 note.
- **Query handling / logging / degradation: PASS.** Pure whitespace tokenization (no injection
  surface); logs counts/timings only (no chunk text); BM25 try/except degrades to already-filtered
  dense-only; Qdrant outage on the dense path propagates (outside the try).

## Performance (performance-checker) — 0 BLOCKING
- `_ensure_bm25_fresh` per-query cost is one small JSON read with a fast-exit guard — sub-ms at
  current scale, as the spec states (SF-A/SG-α). Confirmed.
- `reembed_object` remains O(1) in corpus size (one lock-guarded state write, no scroll). Confirmed.
- `_run_reindex` adds only an integer bump (no extra scroll/embed). Confirmed.
- `_rrf_fuse` bounded by `fetch_limit`. Confirmed.
- Scalability notes (all LOW, future-scale, already accepted in spec §16/§19): `_bm25_search`
  O(N log N) sort (numpy.argpartition at >10k chunks), index memory at 50k+ chunks, per-query
  state read. No action now.

## Simplicity (code-simplifier) — 4 MINOR, all resolved
| Finding | Resolution |
|---|---|
| `import time` deferred inside `_build_bm25_index` for no benefit | **Fixed** — moved to module-level imports. |
| Dead `or []` in `_passes_inline_filters` (`source_type` already truthy) | **Fixed** — simplified to `not in source_type`. |
| `_rrf_fuse` missing type annotations | **Fixed** — typed params + `-> list[tuple[float, dict]]`. |
| `_build_search_filter` missing return annotation | **Applied then reverted** — a string forward-ref `"Filter \| None"` triggers ruff F821 (the `Filter` type is imported inside the body per the project's intentional deferred-import pattern). Kept the contract in the docstring instead; behavior unchanged. |
| `_dense_search_with_ids` duplicates `semantic_search_core` call structure | **Confirmed clean** (not a finding) — the `_build_search_filter` extraction means both callers share one filter impl; only `_point_id` differs. No drift. |

## Lead inline checks
- **Spec compliance:** every AC maps to a passing test; addendum exit criteria honored —
  item 1 (lock-race) implemented (reembed bump under fresh `_reindex_lock()`, skip-on-contention);
  items 3/4/5 (QA-3/QA-4/CSO-1) tests green; item 6 (LEGAL-1, §8 Apache-2.0) and item 7 (CSO-2,
  §17 trust note) present in spec.md.
- **Behavior-preserving extraction:** AC-H-REG1 (bare → `query_filter is None`) and QA-3 (full
  filter structural equality between `semantic_search_core` and `_dense_search_with_ids`) both pass.
- **Lint:** new #327 code is clean (F821 introduced by a cleanup was reverted). One pre-existing
  `F401 pathlib.Path` remains on main, unrelated to #327 — left out of scope to keep the diff focused.
- **Docs:** technical.md, README (incl. roadmap line), CHANGELOG updated; no tool/API signature change.

## Outstanding (lead Step 8, not a code finding)
- AC-EVAL live eval fixture (`tests/eval/fixtures/retrieval_quality_cases.json`) — lead-owned,
  CI-unverifiable, reviewed PR artifact. Tracked separately; required before PR.
