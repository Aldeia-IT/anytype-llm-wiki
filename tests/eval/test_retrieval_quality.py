"""AC-EVAL2: live, human-reviewed retrieval eval (Aldeia-IT/aldeia-box#327).

Run read-only against the live index by the coordinator; never in CI (``live`` marker,
deselected under ``-m 'not live'``).

Environment:
  WIKI_EVAL_FIXTURE  path to the frozen fixture (required; unset means skip with a message)
  WIKI_EVAL_RESULTS  optional output path for per-case ranks (kept out of the repo)

The real fixture (space IDs, object IDs, fleet names) is not committed. The template
``fixtures/retrieval_quality_cases.example.json`` shows the schema; the curation script
``scripts/curate_eval_cases.py`` proposes expected IDs for a human to review and freeze.

Entry points (as the consumer calls them): hybrid is ``server.semantic_search(query,
space_id, types, limit=10)``; dense is ``indexer.semantic_search_core`` with the same
arguments, computed live in the same run. Ranks are object ranks (a miss is rank 11).
"""

import json
import os
from pathlib import Path

import pytest

MISS_RANK = 11
TOP_K = 10
TIER_ONE_SCORE = 2.0  # D8: tier_offset for an exact-name match
NAMED_GROUPS = (
    "capoeira-name", "capoeira-diacritic", "capoeira-context", "capoeira-shared",
    "fleet-exact", "fleet-partial",
)
RANK_ONE_SLACK = 2  # bar 1: at least (n - 2) of n at rank 1


def load_frozen_fixture(path):
    """Load the eval fixture; raise ``ValueError`` unless it is marked ``"frozen": true``.

    Args:
        path: path to the fixture JSON.

    Returns:
        The parsed fixture dict (``frozen``, ``cases``).

    Raises:
        ValueError: the fixture is not frozen or a case lacks a required key.
    """
    data = json.loads(Path(path).read_text())
    if data.get("frozen") is not True:
        raise ValueError(
            "eval fixture is not frozen: review the curated proposals, then set "
            '"frozen": true. The fixture is never edited to fit results.'
        )
    for case in data.get("cases", []):
        missing = {"id", "group", "query", "space_id", "types", "expected_ids"} - set(case)
        if missing:
            raise ValueError(f"case {case.get('id')!r} lacks keys {sorted(missing)}")
    return data


def object_ranks(hits):
    """Distinct object ids in output order (first chunk of each object)."""
    seen, ordered = set(), []
    for hit in hits:
        if hit["object_id"] not in seen:
            seen.add(hit["object_id"])
            ordered.append(hit["object_id"])
    return ordered


def first_rank(expected_ids, hits):
    """1-based object rank of the first expected object in ``hits``; ``MISS_RANK`` if none."""
    expected = set(expected_ids)
    for rank, oid in enumerate(object_ranks(hits)[:TOP_K], start=1):
        if oid in expected:
            return rank
    return MISS_RANK


def _shared_ok(case, hits):
    """Bar 2: every expected object's first chunk precedes every non-expected chunk."""
    expected = set(case["expected_ids"])
    ids = [h["object_id"] for h in hits[:TOP_K]]
    if not expected <= set(ids):
        return False
    last_expected_first = max(ids.index(oid) for oid in expected)
    if any(oid not in expected for oid in ids[: last_expected_first + 1]):
        return False
    right = case.get("right_id")
    if right:
        order = [oid for oid in object_ranks(hits) if oid in expected]
        return bool(order) and order[0] == right
    return True


def evaluate(cases, hybrid_search, dense_search):
    """Apply the five pass bars; return ``(failures, per_case)``.

    Args:
        cases: fixture cases.
        hybrid_search: ``f(case) -> list[hit]`` (``server.semantic_search``, limit 10).
        dense_search: ``f(case) -> list[hit]`` (``semantic_search_core``, limit 10).

    Returns:
        ``failures``: human-readable bar violations (empty when every bar holds);
        ``per_case``: ``{case id: {"group", "hybrid_rank", "dense_rank"}}``.
    """
    failures, per_case = [], {}
    by_group: dict[str, list] = {}
    for case in cases:
        hybrid, dense = hybrid_search(case), dense_search(case)
        per_case[case["id"]] = {
            "group": case["group"],
            "hybrid_rank": first_rank(case["expected_ids"], hybrid),
            "dense_rank": first_rank(case["expected_ids"], dense),
        }
        by_group.setdefault(case["group"], []).append((case, hybrid, dense))

    # Bar 1: capoeira name, diacritic and context cases.
    named = [
        per_case[c["id"]]["hybrid_rank"]
        for g in ("capoeira-name", "capoeira-diacritic", "capoeira-context")
        for c, _, _ in by_group.get(g, [])
    ]
    if any(rank > TOP_K for rank in named):
        failures.append(f"bar 1: {sum(r > TOP_K for r in named)} of {len(named)} not in top {TOP_K}")
    if sum(rank == 1 for rank in named) < len(named) - RANK_ONE_SLACK:
        failures.append(f"bar 1: only {sum(r == 1 for r in named)} of {len(named)} at rank 1")

    # Bar 2: shared names.
    for case, hybrid, _ in by_group.get("capoeira-shared", []):
        if not _shared_ok(case, hybrid):
            failures.append(f"bar 2: shared-name case {case['id']} violates the name tier")

    # Bar 3: fleet cases never worse than dense, strictly better in total.
    fleet = by_group.get("fleet-exact", []) + by_group.get("fleet-partial", [])
    for case, _, _ in fleet:
        r = per_case[case["id"]]
        if r["hybrid_rank"] > r["dense_rank"]:
            failures.append(f"bar 3: fleet case {case['id']} ranks worse than dense")
    if fleet and not (
        sum(per_case[c["id"]]["hybrid_rank"] for c, _, _ in fleet)
        < sum(per_case[c["id"]]["dense_rank"] for c, _, _ in fleet)
    ):
        failures.append("bar 3: fleet rank sum is not strictly lower than dense")

    # Bar 4: controls keep dense's top-1 object near the top.
    for case, hybrid, dense in by_group.get("control", []):
        if dense and object_ranks(dense)[0] not in object_ranks(hybrid)[:3]:
            failures.append(f"bar 4: control {case['id']} lost dense top-1 from the first 3")
    for case, hybrid, dense in by_group.get("control-word", []):
        untiered = object_ranks([h for h in hybrid if h["score"] < TIER_ONE_SCORE])
        if dense and object_ranks(dense)[0] not in untiered[:3]:
            failures.append(f"bar 4: control-word {case['id']} lost dense top-1 from the first 3")

    # Bar 5: no named case is worse than dense.
    for case in cases:
        r = per_case[case["id"]]
        if case["group"] in NAMED_GROUPS and r["hybrid_rank"] > r["dense_rank"]:
            failures.append(f"bar 5: {case['id']} is worse than dense")
    return failures, per_case


@pytest.fixture
def frozen_fixture():
    """The frozen fixture: skips when ``WIKI_EVAL_FIXTURE`` is unset, errors when unfrozen."""
    raw = os.environ.get("WIKI_EVAL_FIXTURE")
    if not raw:
        pytest.skip(
            "WIKI_EVAL_FIXTURE is unset: AC-EVAL2 needs the frozen, human-curated fixture "
            "(see tests/eval/fixtures/retrieval_quality_cases.example.json and "
            "scripts/curate_eval_cases.py)"
        )
    return load_frozen_fixture(raw)


@pytest.mark.live
def test_hybrid_name_aware_retrieval_quality(frozen_fixture):
    """AC-EVAL2: the five pass bars hold against dense on the live index (read-only)."""
    from anytype_llm_wiki import indexer, server

    def hybrid(case):
        return server.semantic_search(
            query=case["query"], space_id=case["space_id"], types=case["types"], limit=TOP_K)

    def dense(case):
        return indexer.semantic_search_core(
            query=case["query"], space_id=case["space_id"], types=case["types"], limit=TOP_K)

    failures, per_case = evaluate(frozen_fixture["cases"], hybrid, dense)
    results_path = os.environ.get("WIKI_EVAL_RESULTS")
    if results_path:
        Path(results_path).write_text(json.dumps(per_case, indent=2, ensure_ascii=False))
    assert not failures, "\n".join(failures)


# ---------------------------------------------------------------------------
# Harness self-checks (not live): they pin the loader and the bars, not retrieval.
# ---------------------------------------------------------------------------


def _hit(oid, score=0.5):
    return {"object_id": oid, "score": score}


def test_unfrozen_fixture_is_rejected(tmp_path):
    path = tmp_path / "f.json"
    path.write_text(json.dumps({"frozen": False, "cases": []}))
    with pytest.raises(ValueError, match="not frozen"):
        load_frozen_fixture(path)


def test_example_fixture_is_an_unfrozen_template_with_the_documented_schema():
    path = Path(__file__).parent / "fixtures" / "retrieval_quality_cases.example.json"
    data = json.loads(path.read_text())
    assert data["frozen"] is False
    groups = {c["group"] for c in data["cases"]}
    assert {"capoeira-name", "capoeira-diacritic", "capoeira-context", "capoeira-shared",
            "fleet-exact", "fleet-partial", "control", "control-word"} <= groups
    for case in data["cases"]:
        assert {"id", "group", "query", "space_id", "types", "expected_ids"} <= set(case)
    assert any("right_id" in c for c in data["cases"])
    assert "<" in json.dumps(data)  # placeholders only


def test_bar_three_flags_a_fleet_case_worse_than_dense():
    cases = [{"id": "f1", "group": "fleet-exact", "query": "q", "space_id": "s",
              "types": [], "expected_ids": ["t"]}]
    failures, _ = evaluate(
        cases, lambda c: [_hit("x"), _hit("t")], lambda c: [_hit("t")])
    assert any("bar 3" in f for f in failures)


def test_bars_pass_for_a_clean_run():
    cases = [{"id": "n1", "group": "capoeira-name", "query": "q", "space_id": "s",
              "types": [], "expected_ids": ["t"]}]
    failures, per_case = evaluate(cases, lambda c: [_hit("t")], lambda c: [_hit("x")])
    assert per_case["n1"] == {"group": "capoeira-name", "hybrid_rank": 1, "dense_rank": 11}
    assert failures == []
