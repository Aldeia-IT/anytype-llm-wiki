"""scripts/curate_eval_cases.py: read-only proposals for AC-EVAL2 (Aldeia-IT/aldeia-box#327).

The script needs the D12/D13 helpers (``_tokenize``, ``strip_name``) from the indexer,
so these tests are red until the implementation exists. Fake Qdrant only; nothing live.
"""

import importlib.util
import json
from pathlib import Path

import pytest

from anytype_llm_wiki import config
from tests.test_hybrid_search import FakeHybridQdrant, _fillers, _point

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "curate_eval_cases.py"
SPACE = "sp"


class ReadOnlyFake(FakeHybridQdrant):
    """Any Qdrant call other than scroll/query_points is a failure."""

    def __getattr__(self, name):
        raise AssertionError(f"curation script called Qdrant.{name}: it must be read-only")


@pytest.fixture
def script():
    spec = importlib.util.spec_from_file_location("curate_eval_cases", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def wired(monkeypatch, tmp_path):
    from anytype_llm_wiki import indexer

    monkeypatch.setattr(config, "INDEX_STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(config, "INDEX_STATE_DIR", tmp_path)
    monkeypatch.setattr(indexer, "embed_query", lambda q: [0.1] * config.EMBED_DIMS)
    pts = [
        _point("a", "oA", "Mestre Pastinha", "bio", heading="Life"),
        _point("b", "oB", "Pastinha Archive Guide", "notes"),
        _point("c1", "oC1", "Cobra Mansa (FICA)", "bio", heading="Intro"),
        _point("c2", "oC2", "Cobra Mansa", "bio", heading="Bahia"),
        _point("s", "oS", "Pastinha source", "text", type_key="wiki_source"),
    ] + _fillers(4)
    fake = ReadOnlyFake(pts, dense_ids=["b", "a"])
    monkeypatch.setattr(indexer, "_qdrant", lambda: fake)
    return fake


def _write_targets(tmp_path, cases):
    path = tmp_path / "targets.json"
    path.write_text(json.dumps({"cases": cases}))
    return path


def _target(**extra):
    base = {"id": "t1", "group": "capoeira-name", "query": "Pastinha", "space_id": SPACE,
            "types": ["wiki_entity"]}
    base.update(extra)
    return base


def test_proposals_are_labelled_with_source_name_and_type(script, wired, tmp_path):
    out = tmp_path / "out.json"
    assert script.main(["--targets", str(_write_targets(tmp_path, [_target()])),
                        "--output", str(out)]) == 0
    doc = json.loads(out.read_text())
    assert doc["frozen"] is False
    case = doc["cases"][0]
    assert {"id", "group", "query", "space_id", "types", "expected_ids", "proposals",
            "dense_top_ids"} <= set(case)
    by_id = {p["object_id"]: p for p in case["proposals"]}
    assert "key_equality" in by_id["oA"]["sources"]
    assert by_id["oA"]["name"] == "Mestre Pastinha" and by_id["oA"]["type"] == "wiki_entity"
    assert "name_token" in by_id["oB"]["sources"] and "key_equality" not in by_id["oB"]["sources"]
    assert "dense_top20" in by_id["oB"]["sources"]
    assert "name_bm25_top20" in by_id["oA"]["sources"]
    assert "oS" not in by_id  # a wiki_source is outside the case's types
    assert case["expected_ids"] == []  # proposals only: the human decides (AC-EVAL2)
    assert case["dense_top_ids"] == ["oB", "oA"]


def test_shared_name_is_one_bare_case_listing_every_same_name_entity(script, wired, tmp_path):
    out = tmp_path / "out.json"
    targets = [_target(id="cm", group="capoeira-shared", query="Cobra Mansa")]
    script.main(["--targets", str(_write_targets(tmp_path, targets)), "--output", str(out)])
    cases = json.loads(out.read_text())["cases"]
    assert [c["id"] for c in cases] == ["cm"]  # no "(context)" variants (D-327-E)
    case = cases[0]
    assert case["query"] == "Cobra Mansa" and case["expected_ids"] == []
    assert "right_id" not in case and "right_id_proposal" not in case
    assert {p["object_id"] for p in case["proposals"] if "key_equality" in p["sources"]} == {
        "oC1", "oC2"}


def test_each_space_is_scrolled_once_for_many_targets(script, wired, tmp_path):
    out = tmp_path / "out.json"
    targets = [_target(id="t1"), _target(id="t2", query="Cobra Mansa")]
    script.main(["--targets", str(_write_targets(tmp_path, targets)), "--output", str(out)])
    assert len(wired.scroll_calls) == 1
    assert len(json.loads(out.read_text())["cases"]) == 2


def test_scroll_objects_reads_every_page_and_passes_the_offset_back(script, wired):
    wired.page_size = 2
    objects = script.scroll_objects(wired, SPACE)
    assert {"oA", "oB", "oC1", "oC2", "oS"} <= set(objects)
    assert len(objects) == 9  # five named objects and four fillers, over five pages
    assert [c["offset"] for c in wired.scroll_calls] == [
        None, "page-2", "page-4", "page-6", "page-8"]


def test_script_is_read_only_and_prints_nothing_secret(script, wired, monkeypatch,
                                                       tmp_path, capsys):
    monkeypatch.setenv("QDRANT_API_KEY", "s3cr3t-key-xyz")
    monkeypatch.setenv("QDRANT_URL", "http://secret-host.invalid:6333")
    out = tmp_path / "out.json"
    targets_path = _write_targets(tmp_path, [_target()])
    before = sorted(p.name for p in tmp_path.iterdir())
    script.main(["--targets", str(targets_path), "--output", str(out)])
    captured = capsys.readouterr()
    for text in (captured.out, captured.err, out.read_text()):
        assert "s3cr3t-key-xyz" not in text and "secret-host" not in text
    assert "SECRET" not in captured.out
    after = sorted(p.name for p in tmp_path.iterdir())
    assert set(after) - set(before) == {"out.json"}  # no state-file writes, nothing else
    assert not config.INDEX_STATE_FILE.exists()


def test_script_requires_targets_and_output(script):
    with pytest.raises(SystemExit) as exc:
        script.main([])
    assert exc.value.code != 0
