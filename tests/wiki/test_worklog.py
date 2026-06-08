"""Unit tests for the durable per-space subject work-log (wiki/worklog.py).

The work-log is the no-drop / crash-resume substrate that replaced the old fixed
subject cap. These tests exercise it directly (no Anytype, no LLM). The autouse
``_isolate_wiki_worklog_dir`` fixture in conftest points WIKI_WORKLOG_DIR at a
per-test tmp dir, so these never touch real local state.
"""

import os

from anytype_llm_wiki.wiki import worklog

SPACE = "space-worklog-test-001"


def _names(items):
    return [i["name"] for i in items]


def test_begin_records_subjects_and_assigns_ids():
    subjects = [
        {"name": "Alpha", "kind": "entity", "facts": "a"},
        {"name": "Beta", "kind": "concept", "facts": "b"},
    ]
    work_id, enriched = worklog.begin(SPACE, subjects)
    assert work_id
    assert all(s.get("id") for s in enriched), enriched

    pending = worklog.load_pending(SPACE)
    assert _names(pending) == ["Alpha", "Beta"]
    assert all(p["_work_id"] == work_id for p in pending)
    # facts/kind round-trip
    by_name = {p["name"]: p for p in pending}
    assert by_name["Beta"]["kind"] == "concept"
    assert by_name["Alpha"]["facts"] == "a"


def test_mark_done_removes_from_pending():
    work_id, enriched = worklog.begin(
        SPACE, [{"name": "A", "kind": "entity", "facts": ""},
                {"name": "B", "kind": "entity", "facts": ""}]
    )
    worklog.mark_done(SPACE, work_id, enriched[0]["id"])
    pending = worklog.load_pending(SPACE)
    assert _names(pending) == ["B"], pending


def test_clear_tombstones_whole_batch():
    work_id, _ = worklog.begin(
        SPACE, [{"name": "A", "kind": "entity", "facts": ""}]
    )
    worklog.clear(SPACE, work_id)
    assert worklog.load_pending(SPACE) == []


def test_compact_removes_file_only_when_nothing_pending():
    work_id, enriched = worklog.begin(
        SPACE, [{"name": "A", "kind": "entity", "facts": ""}]
    )
    path = worklog.log_path(SPACE)
    assert os.path.exists(path)

    # Still pending → compact is a no-op.
    worklog.compact(SPACE)
    assert os.path.exists(path), "compact must not delete a log with pending work"

    # All done → compact removes the file.
    worklog.mark_done(SPACE, work_id, enriched[0]["id"])
    worklog.compact(SPACE)
    assert not os.path.exists(path), "compact must delete a fully-drained log"


def test_partial_meta_relations_round_trip():
    rels = [{"from": "A", "to": "B", "label": "x"}]
    work_id, _ = worklog.begin(
        SPACE, [{"name": "A", "kind": "entity", "facts": ""}],
        meta={"relations": rels, "source": "agent: t"},
    )
    pending = worklog.load_pending(SPACE)
    assert pending[0]["_meta"]["relations"] == rels
    assert pending[0]["_meta"]["source"] == "agent: t"


def test_torn_trailing_line_is_skipped_not_fatal():
    """A crash mid-append can leave a partial trailing line; replay must skip it
    and still return the durably-written subjects."""
    work_id, enriched = worklog.begin(
        SPACE, [{"name": "Durable", "kind": "entity", "facts": ""}]
    )
    # Simulate a torn write: append a partial/garbage line with no newline.
    with open(worklog.log_path(SPACE), "a", encoding="utf-8") as fh:
        fh.write('{"t":"done","work_id":"' + work_id + '","id":"trunc')  # no closing

    pending = worklog.load_pending(SPACE)
    assert _names(pending) == ["Durable"], (
        f"Torn trailing line must be skipped, leaving the durable subject; got {pending}"
    )


def test_resume_after_restart_returns_only_undone():
    """load_pending re-reads the file from scratch (the 'restart' path): after a
    crash that processed some subjects, only the outstanding ones come back."""
    work_id, enriched = worklog.begin(
        SPACE, [{"name": "Done1", "kind": "entity", "facts": ""},
                {"name": "Done2", "kind": "entity", "facts": ""},
                {"name": "Left", "kind": "entity", "facts": ""}]
    )
    worklog.mark_done(SPACE, work_id, enriched[0]["id"])
    worklog.mark_done(SPACE, work_id, enriched[1]["id"])

    # Fresh read == what a brand-new process would see on resume.
    pending = worklog.load_pending(SPACE)
    assert _names(pending) == ["Left"], pending


def test_load_pending_absent_file_is_empty():
    assert worklog.load_pending("space-never-written") == []
