# Spec Addendum — post-spec council (R1)

**Source:** [`council-spec-r1.md`](council-spec-r1.md)
**Date:** 2026-06-25
**Target phase:** implementation (test + impl)
**Status:** Authoritative — the implementation phase MUST honor these items as spec requirements.

The post-spec council approved the spec with **zero BLOCKING** findings. The items below are
the council's ADVISORY findings that impose additional acceptance/exit criteria on the
implementation. They are carried forward here (rather than left only in the meeting summary)
because the next lead reads spec addenda during Task Intake and treats them as authoritative.

## Additional acceptance criteria for the implementation phase

1. **[CTO-1 / INFRA-1] Eliminate or document the `reembed_object` `state.json` write race.**
   The new `_load_state`/`_bump_bm25_corpus_version`/`_save_state` cycle in `reembed_object`
   (§6.2) runs outside `_reindex_lock` and is reached via `force_reembed_object`
   (`wiki/ingest.py:66`), creating a lost-update race with the cron `_run_reindex`. The impl
   MUST either (a) perform the version bump under `_reindex_lock` (skip-or-merge the bump if
   the lock is not acquired), or (b) move the bump into a minimal lock-guarded helper. If
   neither is done, §6.2 MUST be updated to explicitly acknowledge the race and bound its
   worst case (a lost bump is self-healing; a clobbered `_payload_schema_version`/per-space
   map is not — so option (a)/(b) is strongly preferred).

2. **[CPO-1 / QA-1 / QA-2] The Step-8 live-eval fixture is a reviewed gate, and assertions
   must prove lift, not non-regression.**
   - `repro-327`'s `expected_ids` MUST be traceable to the ticket's 2026-06-25 reproduction
     comment (independently justified, not reverse-engineered from BM25 wins).
   - At least one fixture case MUST demonstrate a **strict** `hybrid > dense` delta (the
     aggregate `mean_hybrid >= mean_dense` `>=` assertion alone permits a no-op tie).
   - The `repro-327` per-case assertion MUST show dense actually misses and hybrid recovers
     (i.e. `dense_recall < hybrid_recall`, not `>=`), proving the reproduction is real.
   - Fixture curation is a reviewed artifact at the impl PR, not merely "pytest exits 0".

3. **[QA-3] Add a dense filter-equality AC under a *populated* filter set.** AC-H-REG1 covers
   only the bare (`query_filter is None`) invariant. Add a test asserting `_dense_search_with_ids`
   (or the extracted `_build_search_filter`) constructs a `query_filter` structurally identical
   to `semantic_search_core`'s for a fully-populated case (types + space_id + source_type +
   domain_tags), guarding the #336 OD-B / #323 nested-filter contract on the dense leg of hybrid.

4. **[QA-4] Drive at least one filter-gate AC through the real build path.** Most fusion/filter
   ACs (H3–H6b, H12, H14) hand-feed `_point_id` — the false-confidence pattern the council's
   memory (`0447e373`) flags. Extend ≥1 filter-gate AC (H6b is the best candidate) to drive
   through the real `_build_bm25_index` + `_bm25_search` path, monkeypatching only
   `_qdrant`/`embed_query` (as AC-H2b already does), so a real keying/field-surfacing
   regression cannot pass while production fails.

5. **[CSO-1] Add an explicit cross-`space_id` BM25-only exclusion test.** Cross-space isolation
   for BM25-only chunks rests solely on the in-memory `idx.space_ids[i] == space_id` check in
   `_bm25_search` — a new enforcement path parallel to Qdrant's filter. Add a test asserting a
   BM25-only chunk from a different `space_id` is never admitted, so the two paths cannot drift.

6. **[LEGAL-1] Record the dependency license in §8.** Add one line to §8 noting `rank-bm25` is
   **Apache-2.0** (verified: PyPI; permissive, no copyleft). Keep license metadata intact in
   `uv.lock`; no bespoke attribution file is required (internal, non-distributed tool).

7. **[CSO-2] Note the `state.json` cross-process trust channel in §17.** Add one line stating
   `state.json` is a same-trust-domain local file whose worst-case tampering effect is a
   redundant index rebuild or dense-only fallback — not a security event (no code execution,
   no data exposure, no cross-space leakage).

## Rationale

Items 1 and 2 are the council's two convergent findings — each independently surfaced by two
members — and are the highest-value carries: the lock race is a correctness hazard neither
internal review caught, and the eval-fixture integrity is the load-bearing, CI-unverifiable
guard for the feature's entire reason to exist. Items 3–5 close test-design gaps where the
existing ACs either cover only the trivial path (3), rely on hand-fed keys the council's own
memory flags as false-confidence-prone (4), or leave a new security-relevant enforcement path
untested (5). Items 6–7 are one-line documentation completions for dependency-license hygiene
and security-section completeness. None changes the approved v1 architecture; all are
refinements the implementation must fold in. The minor, already-documented, accepted trades
(hot-path `_load_state`, SF-B short results, cold-start warm-up) are recorded in the meeting
summary and need no new acceptance criterion.
