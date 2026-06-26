# Council Meeting — Post-spec (Round 1)

**Date:** 2026-06-25
**Ticket:** #327 — Retrieval: Lexical/Hybrid Dense+Sparse Fusion (epic #140, split from #323)
**Phase reviewed:** spec
**Client:** anytype-llm-wiki

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator |
| Chief Security Officer | Yes | new third-party dependency + cross-process state trust channel |
| Legal Counsel | Yes | OSS license of new `rank-bm25` dependency |
| Chief Product Officer | Yes | minimum roster |
| QA Director | Yes | 18 acceptance criteria + live eval methodology |
| Chief Technology Officer | Yes | minimum roster |
| Infrastructure Lead | Yes | Qdrant/cron/BM25 index lifecycle across process boundary |
| Client Advocate | No | internal fleet-memory tool; no external client engagement |

## Context Presented

The spec adds a lexical/sparse (BM25) retrieval signal fused with the existing dense
(bge-m3 cosine) ranking via application-level Reciprocal Rank Fusion (RRF, k=60). Dense
retrieval underperforms on name/keyword-precise queries — exact lexical matches are
invisible to pure cosine similarity. The reproduction case (`"contradiction detection
capability and its limitations"`) is a real, verified miss on the live stack.

**Locked v1 architecture:** app-level `rank-bm25` (numpy-only, 8.6 kB — FastEmbed/onnxruntime
rejected on supply-chain grounds) + application-level RRF. A new `hybrid_search_core` wraps
the **unchanged** `semantic_search_core` (preserving the #336 OD-B no-filter invariant) and
is called by both `server.py:semantic_search` and `query.py` Tier-2. A new
`_dense_search_with_ids` exposes the Qdrant `point.id` so both ranked lists key on the same
chunk identity. A cross-process `bm25_corpus_version` stamp in `state.json` + lazy
`_ensure_bm25_fresh` build bridges the launchd-cron-vs-stdio-server process boundary. Native
Qdrant sparse + `FusionQuery` deferred to v2. 18 acceptance criteria, each with a runnable
fail-before-impl test; a `@pytest.mark.live` aggregate Recall@5/MRR@5 eval gates the
keyword-precision improvement.

The spec reached the council via a rigorous internal review trail: R1 = NEEDS REVISION
(7 BLOCKING incl. a fundamental cross-process index-lifecycle flaw, non-fusing RRF keys, a
silently-dropping filter gate, and heterogeneous score corruption of the Tier-2 cap); fix;
R2 = APPROVED WITH CONDITIONS (conditions applied inline).

## Discussion

**Architecture soundness (CTO, Infra Lead).** The CTO spot-verified the load-bearing claims
against the real source: point.id construction (`indexer.py:304-308`, `:362-366`), the
`semantic_search_core` result-dict omissions (`:151-161`), the Tier-2 candidate sort
(`query.py:1009`), the cron/server process boundary (`server.py:346` + the reindex plist),
and the call sites. The locked v1 design (RRF over two `_point_id`-keyed lists, lazy build +
version stamp) is correct and codebase-aligned; the dense path is preserved as a safe
fallback. The Infra Lead independently confirmed the lazy-build + cross-process stamp
genuinely bridges the cron/server boundary in both steady state and cold start.

**Convergent finding — `reembed_object` state-write race.** The CTO and Infra Lead
*independently* identified that the spec's new `_load_state`/`_bump`/`_save_state` cycle in
`reembed_object` (§6.2) runs **outside** `_reindex_lock` (which wraps only `_run_reindex`),
reached via `force_reembed_object` (`wiki/ingest.py:66`). A concurrent cron reindex and an
interactive reembed can lose a version bump (low impact, self-healing per SF-A) — but, more
seriously, could clobber `_payload_schema_version`/per-space state if the unlocked write
lands over a concurrent reindex write. Neither R1 nor R2 caught this; it only surfaces when
tracing `force_reembed_object`'s lock coverage. Consolidated as ADVISORY 1.

**Convergent finding — eval-fixture integrity.** The CPO and QA Director *independently*
flagged that the implementer-owned ≥5-case live-eval fixture is the **only** guard for the
headline feature and is not CI-verifiable. QA noted the aggregate and per-case assertions use
`>=`, so a fixture that merely *ties* dense passes green, and most fusion/filter ACs use the
hand-fed-key pattern the council's own memory (`0447e373`) warns gives false confidence.
Consolidated as ADVISORY 2 (and 4).

**Security & legal (CSO, Legal).** CSO: the local-first / no-egress posture is fully
preserved; `rank-bm25` is the cleanest part of the deliverable (numpy-only, zero net-new
packages, pinned `<1.0.0`); attack surface is minimal (no eval/deserialization/shell; input
is the operator's own queries over the operator's own corpus). Residual items are
documentation/coverage refinements. Legal verified `rank-bm25` is **Apache-2.0** (permissive,
no copyleft; attribution obligation inert for an internal non-distributed tool) and confirmed
no data/privacy obligation is created.

**Scope discipline (CPO, CTO).** Both explicitly considered and declined a split. This is a
single tightly-coupled increment — BM25 index, RRF fuse, two call-site switches, and eval are
not independently shippable. The v1/v2 boundary is already the correct decomposition and v2
is properly deferred to its own future ticket.

## Findings

### BLOCKING
None.

### ADVISORY
1. **[CTO + Infra] `reembed_object` gains an unlocked `state.json` write → lost-update race
   with the cron `_run_reindex`.** `_reindex_lock` wraps only `_run_reindex` (`indexer.py:242`);
   `reembed_object` (`:342`, reached via `force_reembed_object` at `wiki/ingest.py:66`) takes
   no lock. Worst case low for the BM25 bump (self-healing, SF-A), but a write landing over a
   concurrent reindex could clobber `_payload_schema_version`/per-space state — broader
   correctness. **Impl must** wrap the new bump under `_reindex_lock` (skip-or-merge if not
   acquired) or, at minimum, acknowledge the race in §6.2.
2. **[CPO + QA] Eval-fixture integrity — the headline feature's only guard is
   implementer-owned and not CI-verifiable.** Aggregate and `repro-327` assertions use `>=`,
   so a fixture that merely ties dense passes. Make Step-8 fixture curation a **reviewed
   gate**: `repro-327` `expected_ids` traceable to the ticket's 2026-06-25 comment (not
   implementer-chosen); ≥1 case must show **strict** hybrid > dense lift; `repro-327` must
   show dense actually misses (`dr < hr`), proving the reproduction is real, not asserted into
   triviality.
3. **[QA] No AC pins dense filter-equality under a *populated* filter set.** AC-H-REG1 checks
   only the bare (`query_filter is None`) path. A refactor of shared filter construction
   (`_build_search_filter` / `_dense_search_with_ids`) could silently diverge from
   `semantic_search_core` under types+space_id+source_type+domain_tags and break the
   #336 OD-B / #323 nested-filter contract on the dense leg. Add a filter-structural-equality
   AC for a fully-populated case.
4. **[QA] Most fusion/filter ACs hand-feed `_point_id` (false-confidence pattern).** AC-H2b is
   the only test driving real keying; H3–H6b/H12/H14 monkeypatch `_bm25_search`/
   `_dense_search_with_ids` with hand-set ids. Drive ≥1 filter-gate AC (H6b) through the real
   `_build_bm25_index` + `_bm25_search` path (monkeypatch only `_qdrant`/`embed_query`).
5. **[CSO] Cross-`space_id` isolation for BM25-only chunks rests on a single new in-memory
   check.** `idx.space_ids[i] == space_id` in `_bm25_search` is the sole barrier (a new
   enforcement path parallel to Qdrant's filter). Add an explicit cross-`space_id` BM25-only
   exclusion test so the two paths cannot drift.
6. **[Legal] §8 omits the dependency license.** Record `rank-bm25` = **Apache-2.0** (verified)
   in §8 at impl. Keep license metadata intact in `uv.lock`; no bespoke attribution file
   needed (internal, non-distributed).
7. **[CSO] §17 omits the `state.json` cross-process trust channel.** Add one line noting it is
   a same-trust-domain local file whose worst-case tampering effect is a redundant rebuild or
   dense-only fallback — not a security event.
8. **[CTO/QA/Infra] Hot-path `_load_state()` on every hybrid query + documented coverage
   gaps.** `_read_bm25_corpus_version` parses full `state.json` per query (sub-ms today, scales
   with state size — track the §19 sidecar split as a real follow-up, not a footnote). Minor,
   documented, accepted: SF-B (hybrid may return < `limit` under aggressive filtering — add a
   boundary test if cheap) and first-query-after-restart dense-only warm-up (<100 ms,
   self-healing).

## Decomposition

None. Both the CPO and the CTO explicitly evaluated a SPLIT RECOMMENDATION and declined.
The ticket is a single, tightly-coupled increment (one retrieval path; BM25 index, RRF fuse,
two call-site switches, and the live eval are not independently shippable user value). The
v1/v2 boundary is already the correct decomposition, and v2 (native Qdrant sparse +
`FusionQuery`) is correctly carved into its own future ticket (§19). Splitting v1 further
would create half-features with no standalone value or a dead-code intermediate state.

## Resolutions

- The architecture-soundness, codebase-alignment, and reviewer-diligence concerns implicit in
  the brief were resolved in discussion: the CTO confirmed R1/R2 did their job genuinely
  (every BLOCKING cited a verified file:line; the redesign was real, not prose-patched), and
  the R2 inline-applied conditions (SF-A..SG-β) are low-risk documentation/test-robustness
  refinements that did not warrant a re-review.
- No member's finding was withdrawn; all ADVISORY items above are carried into the
  implementation phase via the spec addendum (`spec-addendum-post-spec-r1.md`).

## Recommendation

**Recommended target:** decide
**Confidence:** high
**Rationale:** The spec is **APPROVED** — zero BLOCKING across all six members, and the
internal R1→R2 trail credibly resolved three masked correctness bugs plus a fundamental
cross-process lifecycle flaw. The two remaining items are genuine **strategic** Open Decisions
the spec explicitly reserves for Jan — OD-327-A (accept app-level BM25 as v1 vs go straight to
native-Qdrant v2; lead recommends v1) and OD-327-B (lazy-build + version stamp vs eager
rebuild; lead recommends lazy, the only design that bridges the cron process boundary). These
are leadership architecture choices, not council gatekeeping, so the ticket routes to Decide
for ratification before Implement. All eight ADVISORY findings are non-blocking and have been
written into an authoritative spec addendum that the implementation lead will honor.
**Dissent:** None.
