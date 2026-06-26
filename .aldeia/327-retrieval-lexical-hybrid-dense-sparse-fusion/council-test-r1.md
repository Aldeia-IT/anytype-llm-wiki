# Council Meeting — Post-test (Round 1)

**Date:** 2026-06-26
**Ticket:** #327 — Retrieval: Lexical/Hybrid Dense+Sparse Fusion (epic #140, split from #323)
**Phase reviewed:** test
**Client:** anytype-llm-wiki

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator |
| QA Director | Yes | minimum roster — AC↔test coverage, assertion strength, gate integrity |
| Chief Technology Officer | Yes | chair decision — addendum imposed test-design criteria (QA-3/QA-4/CSO-1); reviewer-diligence lens |
| Chief Security Officer | Yes | chair decision — CSO-1 cross-space exclusion is a security-mandated test; confirm not trivially-green |
| Legal Counsel | No | license/compliance carries (rank-bm25 Apache-2.0) are impl-phase doc obligations, not test-gate |
| Chief Product Officer | No | no product-strategy surface at the test gate; scope already settled post-spec |
| Infrastructure Lead | No | no operational surface exercised by the test suite; lock-race is an impl-phase correctness concern |
| Client Advocate | No | internal fleet-memory tool; no external client engagement |

## Context Presented

The test phase produced failing tests, ahead of implementation, for the approved hybrid
dense+sparse (BM25 + RRF, k=60) retrieval spec. A new `hybrid_search_core` will fuse the
**unchanged** `semantic_search_core` dense leg with a `rank-bm25` sparse leg via
application-level Reciprocal Rank Fusion; a `_dense_search_with_ids` surfaces Qdrant
`point.id` so both ranked lists key on the same chunk identity, and a cross-process
`bm25_corpus_version` stamp in `state.json` + lazy `_ensure_bm25_fresh` bridges the
launchd-cron-vs-stdio-server boundary.

The suite covers all 18 acceptance criteria (AC-H1..AC-H-REG1, AC-EVAL) plus the three
test-design items the **post-spec** council carried into this phase via
`spec-addendum-post-spec-r1.md`: QA-3 (dense filter-equality under a populated filter set),
QA-4 (drive ≥1 filter-gate AC through the real `_build_bm25_index` + `_bm25_search` path),
and CSO-1 (explicit cross-`space_id` BM25-only exclusion). The internal review trail was
R1 = NEEDS CHANGES (1 BLOCKING: repro-327 per-case eval used `>=`, letting a no-op tie pass;
1 SHOULD-FIX: the QA-4 drop test was trivially green — the drop-candidate shared no query
tokens, scored 0 in BM25, and was dropped by the `score <= 0` break before ever reaching the
filter gate) → fix → R2 = APPROVED. Red gate verified at **48 failed, 103 passed, 10 skipped,
2 deselected** under `-m 'not live'`.

## Discussion

**Reviewer diligence — genuinely verified, not rubber-stamped (CTO, QA).** The CTO and QA
Director each independently re-derived the two non-obvious load-bearing claims rather than
trusting the R2 prose. The CTO **installed rank-bm25 in a throwaway venv and executed the
exact QA-4 corpus** against the query `"machine learning"`: `obj_fin` ("machine financial
analysis") scores **0.0958 > 0**, because the over-common term "machine" appears in all three
docs → negative raw IDF → floored to `epsilon * average_idf` (positive). The QA Director
reproduced the same arithmetic. This confirms the R1 fix is real: `obj_fin` now clears the
`if score <= 0: break` guard, reaches `_passes_inline_filters`, and is dropped **only** by the
`domain_tags` mismatch — so a deleted filter gate would now fail the test. (Note: R2's
hand-computed ~0.051 was numerically slightly off the true 0.0958, but the sign and
conclusion were exactly right.) Both confirmed the strict repro-327 gate (`>` at
`tests/eval/test_retrieval_quality.py:93`) is applied at the per-case assertion while the
aggregate means correctly stay `>=`.

**Codebase alignment (CTO).** Retargeting of the Tier-2 monkeypatch sites from
`semantic_search_core` → `hybrid_search_core` is complete and **not over-applied**:
direct-call sites (importability test, TestNestedFilter, TestCrossTierDateFilterEquivalence,
`wiki/lint.py:616`) are correctly preserved, and the AC-H11 routing guard
(`test_wiki_query_tier2_calls_hybrid`) precisely patches `semantic_search_core` to *raise*
while asserting `hybrid_search_core` is called. The `FakeQdrantClientWithSearch.scroll()`
signature matches the spec §11.1 call shape and returns the terminating `(results, None)`
tuple. The unchanged `semantic_search_core` (`indexer.py:71`) genuinely returns id-less dicts,
confirming the rationale for the separate `_dense_search_with_ids`.

**Security-mandated test is genuine (CSO).** CSO-1 (`test_bm25_cross_space_exclusion`,
`tests/test_indexer.py:1865`) does **not** repeat the QA-4 trivially-green defect: both the
sp_A target and the sp_B excluded chunk carry the identical query text "contradiction
detection", so both score >0 in BM25 and clear the zero-score guard — meaning the sole reason
the sp_B chunk is absent is the new in-memory `idx.space_ids[i] == space_id` enforcement.
Remove that check and the test fails. No new attack surface from the test design (local,
in-process, no egress, no untrusted deserialization; query strings flow through
`.lower().split()` only).

**AC-EVAL gate framing (QA, CTO).** The live aggregate Recall@5/MRR@5 eval is
`@pytest.mark.live`, deselected under `-m 'not live'`, and its fixture
(`tests/eval/fixtures/retrieval_quality_cases.json`) is deliberately **not** created in this
phase — it is implementer-owned at Step 8 (spec §10.2 BL-6). The council agreed this is the
correct boundary (the fixture needs live Anytype/Qdrant/Ollama object IDs that exist only at
impl time), but flagged that this makes the feature's single headline guard **CI-unverifiable**
and therefore an impl-phase reviewed-artifact obligation, not a "pytest exits 0" formality.

## Findings

### BLOCKING
None.

### ADVISORY
1. **[QA + CTO] The AC-EVAL live-eval fixture is the feature's only headline guard and is
   CI-unverifiable.** It is correctly deferred to the implementer (Step 8), but its integrity
   (repro-327 `expected_ids` traceable to the ticket's 2026-06-25 reproduction comment and
   *independently justified*, not reverse-engineered from BM25 wins; ≥1 case showing **strict**
   hybrid > dense lift; the dense leg genuinely missing for organic reasons) cannot be checked
   by the test phase. This restates and reinforces post-spec addendum item 2 — surfaced so it
   is treated as a **non-skippable, reviewed pre-PR gate** at the impl council, not lost.
2. **[QA + CSO + CTO] The post-spec addendum's remaining impl-phase carries remain open and
   must be confirmed at the impl gate.** Item 1 (the `reembed_object` `state.json` write-race
   outside `_reindex_lock`, reached via `force_reembed_object` — a correctness hazard with no
   test-phase obligation here); item 6 (record `rank-bm25` = Apache-2.0 in spec §8); item 7
   (note the `state.json` cross-process trust channel in spec §17). All correctly deferred,
   none lost; flagged for the impl-phase review to verify each lands.
3. **[QA] SF-B short-result trade (§6.7 — hybrid may return < `limit` under aggressive
   filtering) is documented and accepted but has no dedicated unit test.** Not a correctness
   bug and not mandated; a pinning test would be cheap insurance if a caller is later
   surprised. Acceptable as-is.
4. **[QA] QA-3 asserts structural equality, not byte-identity.** `test_dense_search_with_ids_
   filter_equals_semantic_search_core` compares must-list length + per-condition values across
   the four populated filter dimensions — the right level (survives benign reordering), but it
   would not catch a divergence in a condition type the test does not enumerate. Sufficient for
   the #336 OD-B / #323 nested-filter contract; noting the boundary only.

## Decomposition

None. The CTO explicitly evaluated a SPLIT RECOMMENDATION and declined, concurring with the
post-spec council's decision: the dense-id surfacing, BM25 build/search, RRF fusion, and
cross-process version stamp are a single tightly-coupled retrieval increment with one shared
test surface (`indexer.py` + the `query.py` call-site switch). The test suite is already
organized by AC and reviews cleanly as one unit; splitting would fragment the fusion contract
across PRs with no risk reduction. No new grounds for a split surfaced at the test gate.

## Resolutions

- The two R1 findings (1 BLOCKING, 1 SHOULD-FIX) were genuinely resolved in one fix cycle and
  independently re-verified by two members at this council — the strict repro-327 gate and the
  real-path QA-4 drop both hold. The R1 SUGGESTION (stale `semantic_search_core` comments) was
  applied with no `setattr` target disturbed.
- No member's finding was withdrawn. All four ADVISORY items above are non-blocking; items 1
  and 2 are carried into the implementation phase via a post-test spec addendum
  (`spec-addendum-post-test-r1.md`) and reference the still-open post-spec addendum items.

## Recommendation

**Recommended target:** impl
**Confidence:** high
**Rationale:** Unanimous sign-off, zero BLOCKING across all three members, with the two
non-obvious load-bearing claims (repro-327 strict lift; QA-4 real-path drop via the rank-bm25
epsilon IDF floor) independently re-derived — the CTO by executing the actual library against
the actual corpus. All 18 ACs plus the three council-mandated addendum tests (QA-3, QA-4,
CSO-1) are present and substantive, the red gate is clean (every one of the 48 failures is a
pure absent-#327-symbol failure; the regression guard AC-H-REG1 is correctly green), and the
implementer-owned AC-EVAL fixture boundary is correctly scoped with its strict-lift assertion
intact. The remaining advisories are impl-phase carries, properly documented, not test-gate
defects. The phase is ready to advance to implementation; the watcher applies the autonomy
policy on top of this recommendation.
**Dissent:** None.
