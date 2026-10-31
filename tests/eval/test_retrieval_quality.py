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
GROUPS = (*NAMED_GROUPS, "control", "control-word")
# The AC-EVAL2 case table (amended by D-327-E (a): capoeira-shared is 10 bare names,
# no "(context)" variants). Exact counts per group; controls are per space.
EXACT_COUNTS = {
    "capoeira-name": 22, "capoeira-diacritic": 4, "capoeira-context": 2,
    "capoeira-shared": 10, "fleet-exact": 10, "fleet-partial": 5, "control-word": 3,
}
BAR_TWO_IGNORED_TYPE = "wiki_source"  # bar 2: pages about the person don't count against it
MIN_CONTROL_PER_SPACE = 5
BAR_ONE_GROUPS = ("capoeira-name", "capoeira-diacritic", "capoeira-context")
BAR_ONE_RANK_ONE_MIN = 26  # bar 1: 28 of 28 in the top 10, at least 26 at rank 1


def load_frozen_fixture(path):
    """Load the eval fixture; raise ``ValueError`` unless it is marked ``"frozen": true``.

    Args:
        path: path to the fixture JSON.

    Returns:
        The parsed fixture dict (``frozen``, ``cases``).

    Raises:
        ValueError: the fixture is not frozen; a case lacks a required key or has an
            unknown ``group``; a named case has no ``expected_ids``; or a shared case
            has fewer than two.
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
        _check_case(case)
    return data


def _check_case(case):
    """Reject a case a bar would otherwise pass vacuously (helper of the loader)."""
    cid, group, expected = case["id"], case["group"], case["expected_ids"]
    if group not in GROUPS:
        raise ValueError(f"case {cid!r} has unknown group {group!r}; known: {list(GROUPS)}")
    if group in NAMED_GROUPS and not expected:
        raise ValueError(f"case {cid!r} has no expected_ids: curate them before freezing")
    if group == "capoeira-shared" and len(set(expected)) < 2:
        raise ValueError(f"shared case {cid!r} needs two or more expected_ids")


def count_failures(cases):
    """Check the case counts of the AC-EVAL2 table; return the violations (empty if none).

    Args:
        cases: fixture cases.

    Returns:
        Human-readable messages, one per group whose count is off, so that a short or
        mislabelled fixture fails the gate instead of passing a bar with zero cases.
    """
    failures = []
    by_group: dict[str, list] = {}
    for case in cases:
        by_group.setdefault(case["group"], []).append(case)
    for group, count in EXACT_COUNTS.items():
        found = len(by_group.get(group, []))
        if found != count:
            failures.append(f"counts: {group} has {found} cases, the spec needs {count}")
    controls: dict[str, int] = {}
    for case in by_group.get("control", []):
        controls[case["space_id"]] = controls.get(case["space_id"], 0) + 1
    for space in sorted({c["space_id"] for c in cases}):
        if controls.get(space, 0) < MIN_CONTROL_PER_SPACE:
            failures.append(
                f"counts: space {space} has {controls.get(space, 0)} control cases, "
                f"the spec needs at least {MIN_CONTROL_PER_SPACE}"
            )
    return failures


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
    """Bar 2: every expected object's first chunk is in the top 10, ahead of every chunk
    of a non-expected object; non-expected ``wiki_source`` chunks are ignored (D-327-E).
    """
    expected = set(case["expected_ids"])
    top = hits[:TOP_K]
    ids = [h["object_id"] for h in top]
    if not expected <= set(ids):
        return False
    last_expected_first = max(ids.index(oid) for oid in expected)
    return not any(
        h["object_id"] not in expected and h.get("type_key") != BAR_TWO_IGNORED_TYPE
        for h in top[: last_expected_first + 1]
    )


def evaluate(cases, hybrid_search, dense_search):
    """Check the case counts, apply the five pass bars; return ``(failures, per_case)``.

    Args:
        cases: fixture cases.
        hybrid_search: ``f(case) -> list[hit]`` (``server.semantic_search``, limit 10).
        dense_search: ``f(case) -> list[hit]`` (``semantic_search_core``, limit 10).

    Returns:
        ``failures``: human-readable bar violations (empty when every bar holds);
        ``per_case``: ``{case id: {"group", "hybrid_rank", "dense_rank"}}``.
    """
    failures, per_case = count_failures(cases), {}
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
        for g in BAR_ONE_GROUPS
        for c, _, _ in by_group.get(g, [])
    ]
    if any(rank > TOP_K for rank in named):
        failures.append(f"bar 1: {sum(r > TOP_K for r in named)} of {len(named)} not in top {TOP_K}")
    if sum(rank == 1 for rank in named) < BAR_ONE_RANK_ONE_MIN:
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


def _hit(oid, score=0.5, type_key="wiki_entity"):
    return {"object_id": oid, "score": score, "type_key": type_key}


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
    assert not any("right_id" in c for c in data["cases"])  # D-327-E: bare names only
    assert "<" in json.dumps(data)  # placeholders only


def _case(cid, group, space, expected, **extra):
    return {"id": cid, "group": group, "query": "q", "space_id": space, "types": [],
            "expected_ids": expected, **extra}


def _full_cases():
    """A fixture with exactly the AC-EVAL2 case table (two spaces: cap and fleet)."""
    cases = []
    for group in BAR_ONE_GROUPS:
        cases += [_case(f"{group}-{i}", group, "cap", ["t"])
                  for i in range(EXACT_COUNTS[group])]
    cases += [_case(f"shared-{i}", "capoeira-shared", "cap", ["t", "u"])
              for i in range(EXACT_COUNTS["capoeira-shared"])]
    for group in ("fleet-exact", "fleet-partial"):
        cases += [_case(f"{group}-{i}", group, "fleet", ["t"])
                  for i in range(EXACT_COUNTS[group])]
    for space in ("cap", "fleet"):
        cases += [_case(f"control-{space}-{i}", "control", space, [])
                  for i in range(MIN_CONTROL_PER_SPACE)]
    cases += [_case(f"word-{i}", "control-word", s, []) for i, s in
              enumerate(("cap", "cap", "fleet"))]
    return cases


def _clean_hybrid(case):
    return [_hit(oid) for oid in (case["expected_ids"] or ["x"])]


def _dense_x(case):
    return [_hit("x")]


def _frozen(tmp_path, cases):
    path = tmp_path / "f.json"
    path.write_text(json.dumps({"frozen": True, "cases": cases}))
    return path


def test_bar_three_flags_a_fleet_case_worse_than_dense():
    def hybrid(case):
        if case["id"] == "fleet-exact-0":
            return [_hit("x"), _hit("t")]
        return _clean_hybrid(case)

    failures, _ = evaluate(_full_cases(), hybrid, lambda c: [_hit("t")])
    assert "bar 3: fleet case fleet-exact-0 ranks worse than dense" in failures


def test_bars_pass_for_a_clean_run():
    failures, per_case = evaluate(_full_cases(), _clean_hybrid, _dense_x)
    assert per_case["capoeira-name-0"] == {
        "group": "capoeira-name", "hybrid_rank": 1, "dense_rank": 11}
    assert failures == []


def test_bar_one_needs_26_named_cases_at_rank_one():
    def hybrid(case):
        if case["id"] in {"capoeira-name-0", "capoeira-name-1", "capoeira-name-2"}:
            return [_hit("y"), _hit("t")]
        return _clean_hybrid(case)

    failures, _ = evaluate(_full_cases(), hybrid, _dense_x)
    assert "bar 1: only 25 of 28 at rank 1" in failures


def test_a_missing_group_fails_the_counts_instead_of_passing_vacuously():
    cases = [c for c in _full_cases() if c["group"] != "fleet-partial"]
    failures, _ = evaluate(cases, _clean_hybrid, _dense_x)
    assert "counts: fleet-partial has 0 cases, the spec needs 5" in failures


def test_too_few_controls_in_a_space_fail_the_counts():
    cases = [c for c in _full_cases() if c["id"] != "control-fleet-0"]
    failures, _ = evaluate(cases, _clean_hybrid, _dense_x)
    assert any(f.startswith("counts: space fleet has 4 control cases") for f in failures)


def test_unknown_group_is_rejected(tmp_path):
    cases = _full_cases()
    cases[0]["group"] = "capoeira_name"
    with pytest.raises(ValueError, match="unknown group 'capoeira_name'"):
        load_frozen_fixture(_frozen(tmp_path, cases))


def test_named_case_without_expected_ids_is_rejected(tmp_path):
    cases = _full_cases()
    cases[0]["expected_ids"] = []
    with pytest.raises(ValueError, match="no expected_ids"):
        load_frozen_fixture(_frozen(tmp_path, cases))


def test_shared_case_with_one_expected_id_is_rejected(tmp_path):
    cases = [c if c["id"] != "shared-0" else {**c, "expected_ids": ["t"]}
             for c in _full_cases()]
    with pytest.raises(ValueError, match="two or more"):
        load_frozen_fixture(_frozen(tmp_path, cases))


def test_full_frozen_fixture_loads(tmp_path):
    assert len(load_frozen_fixture(_frozen(tmp_path, _full_cases()))["cases"]) == 66


def test_bar_two_ignores_a_non_expected_source_page_ahead_of_the_entities():
    case = _case("s", "capoeira-shared", "cap", ["t", "u"])
    page = _hit("page", type_key="wiki_source")
    assert _shared_ok(case, [_hit("t"), page, _hit("u"), _hit("x")])
    assert not _shared_ok(case, [_hit("t"), _hit("x"), _hit("u")])  # another entity
    assert not _shared_ok(case, [_hit("t"), page])  # an expected object is missing


def test_shared_count_is_exactly_ten_bare_names():
    cases = [c for c in _full_cases() if c["id"] != "shared-0"]
    failures, _ = evaluate(cases, _clean_hybrid, _dense_x)
    assert "counts: capoeira-shared has 9 cases, the spec needs 10" in failures
