"""Live aggregate recall/MRR eval for hybrid retrieval (#327).

This test is gated with @pytest.mark.live and is DESELECTED under
    -m 'not live'
so it does NOT run in CI or during normal unit test collection.

The fixture file (tests/eval/fixtures/retrieval_quality_cases.json) is
OWNED by the implementer (Step 8 in the spec) and must NOT be created by
the test writer. The test will fail at collection time with a clear
FileNotFoundError when the fixture does not exist — which is the expected
failure mode until the implementer creates it.

Per spec §10.3 (AC-EVAL): imports of hybrid_search_core/semantic_search_core
are inside the test function body so -m 'not live' collection stays clean
even before the implementation exists.
"""

import json
import statistics
from pathlib import Path

import pytest

FIXTURE_FILE = Path(__file__).parent / "fixtures" / "retrieval_quality_cases.json"


def _recall_at_k(expected, results, k=5):
    top = {r["object_id"] for r in results[:k]}
    return len(set(expected) & top) / len(expected) if expected else 0.0


def _mrr_at_k(expected, results, k=5):
    es = set(expected)
    for rank, r in enumerate(results[:k], start=1):
        if r["object_id"] in es:
            return 1.0 / rank
    return 0.0


@pytest.mark.live
def test_hybrid_recall_aggregate():
    """AC-EVAL: Aggregate Recall@5 and MRR@5 (hybrid >= dense) AND repro-327 strictly improves.

    This is a live test requiring a running Anytype/Qdrant/Ollama stack.
    Run with: uv run python -m pytest tests/eval/ -m live -v

    The fixture file must contain >=5 cases including a 'repro-327' case
    (owned by the implementer, Step 8 in the spec).

    Assertions:
    - AGGREGATE: mean Recall@5 and MRR@5 each require hybrid >= dense (tolerates ties)
    - REPRO-327 PER-CASE: requires hybrid > dense STRICTLY (dense_recall < hybrid_recall)
      A no-op hybrid returning the same results as dense would produce hr==dr and FAIL here.
      Per addendum item 2 (CPO-1/QA-1/QA-2), this case must prove the feature's lift is real.
    """
    from anytype_llm_wiki.indexer import hybrid_search_core, semantic_search_core

    cases = json.loads(FIXTURE_FILE.read_text())
    assert len(cases) >= 5, "fixture must have >=5 cases for statistical validity"

    d_rec, h_rec, d_mrr, h_mrr, report = [], [], [], [], []
    repro = {}

    for c in cases:
        q, exp = c["query"], c["expected_ids"]
        kw = {"limit": 5}
        if c.get("space_id"):
            kw["space_id"] = c["space_id"]
        if c.get("types"):
            kw["types"] = c["types"]
        dense = semantic_search_core(query=q, **kw)
        hybrid = hybrid_search_core(query=q, **kw)
        dr, hr = _recall_at_k(exp, dense), _recall_at_k(exp, hybrid)
        dm, hm = _mrr_at_k(exp, dense), _mrr_at_k(exp, hybrid)
        d_rec.append(dr)
        h_rec.append(hr)
        d_mrr.append(dm)
        h_mrr.append(hm)
        report.append(
            f"  {q!r}: d_recall={dr:.2f} h_recall={hr:.2f} "
            f"d_mrr={dm:.2f} h_mrr={hm:.2f}"
        )
        if c.get("id") == "repro-327":
            repro = {"dr": dr, "hr": hr}

    rpt = "\n".join(report)
    assert statistics.mean(h_rec) >= statistics.mean(d_rec), (
        f"Recall@5 regressed\n{rpt}"
    )
    assert statistics.mean(h_mrr) >= statistics.mean(d_mrr), (
        f"MRR@5 regressed\n{rpt}"
    )
    assert repro and repro["hr"] > repro["dr"], (
        f"repro-327: hybrid recall must strictly exceed dense recall "
        f"(dense_recall < hybrid_recall required — a no-op tie is a failure)\n{rpt}"
    )
