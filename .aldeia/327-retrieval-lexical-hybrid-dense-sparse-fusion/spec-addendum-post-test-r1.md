# Spec Addendum — post-test council (R1)

**Source:** [`council-test-r1.md`](council-test-r1.md)
**Date:** 2026-06-26
**Target phase:** implementation
**Status:** Authoritative — the implementation phase MUST honor these items as exit criteria.

The post-test council approved the test phase with **zero BLOCKING** findings. The test-design
items the post-spec council mandated (QA-3, QA-4, CSO-1) were confirmed present and genuinely
exercised. The items below are the council's ADVISORY carries that act as **implementation-phase
exit criteria**. They consolidate (and do not supersede) the still-open items in
[`spec-addendum-post-spec-r1.md`](spec-addendum-post-spec-r1.md); cross-references are given so
the impl lead has a single test-perspective checklist at the impl gate.

## Additional exit criteria for the implementation phase

1. **[QA + CTO] The AC-EVAL live-eval fixture is a non-skippable, reviewed pre-PR gate — not a
   "pytest exits 0" formality.** (Reinforces post-spec addendum item 2.) The fixture
   `tests/eval/fixtures/retrieval_quality_cases.json` is implementer-owned (Step 8, spec §10.2
   BL-6) and is the feature's single CI-unverifiable headline guard. At the impl PR the
   reviewer MUST confirm, as a reviewed artifact:
   - `repro-327`'s `expected_ids` are traceable to the ticket's **2026-06-25 reproduction
     comment** and independently justified — NOT reverse-engineered from BM25 wins.
   - The dense leg genuinely **misses** those ids for organic reasons (proving the reproduction
     is real), i.e. the strict per-case gate `dense_recall < hybrid_recall`
     (`tests/eval/test_retrieval_quality.py:93`, already strict `>`) passes against the live
     stack, not by construction.
   - ≥1 fixture case demonstrates a **strict** hybrid > dense lift (the aggregate `>=` mean
     assertion alone tolerates a no-op tie).
   - `pytest tests/eval/ -m live` is run **green against the live stack** and the result is
     recorded on the PR.

2. **[QA + CSO + CTO] Confirm the still-open post-spec addendum carries land before the impl
   gate closes.** None were exercisable in the test phase; each must be verified at the impl PR:
   - **Item 1 (CTO-1/INFRA-1):** eliminate or explicitly bound the `reembed_object`
     `state.json` write-race (the `_load_state`/`_bump`/`_save_state` cycle runs outside
     `_reindex_lock` and is reachable via `force_reembed_object`). Preferred: perform the bump
     under `_reindex_lock` (skip-or-merge if not acquired).
   - **Item 6 (LEGAL-1):** record `rank-bm25` = **Apache-2.0** in spec §8; keep `uv.lock`
     license metadata intact.
   - **Item 7 (CSO-2):** add the one-line `state.json` cross-process trust-channel note to
     spec §17.

## Rationale

Both items are carries, not new architecture. Item 1 is the highest-value carry: the live-eval
fixture is the only evidence that hybrid beats dense, and it cannot be checked in CI — so its
integrity must be a human-reviewed PR artifact, not an automated exit. Item 2 simply prevents
the three open impl obligations (a real correctness hazard plus two one-line documentation
completions) from being lost in the handoff from the test gate to the impl gate. The
test-design items the post-spec council mandated (QA-3/QA-4/CSO-1) are already satisfied and
require no further action.
