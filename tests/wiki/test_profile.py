"""WIKI_PROFILE per-stage timing is off by default and free when off (#1485)."""

import json

from anytype_llm_wiki.wiki import profile


def test_off_by_default_writes_nothing(monkeypatch, capsys):
    monkeypatch.delenv("WIKI_PROFILE", raising=False)
    with profile.span("stage", n=1) as meta:
        meta["x"] = 2
    profile.event("point", n=1)
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == ""
    assert profile.profile_target() is None


def test_falsy_values_stay_off(monkeypatch, capsys):
    for value in ("", "0", "false", "off", "No"):
        monkeypatch.setenv("WIKI_PROFILE", value)
        with profile.span("stage"):
            pass
    assert capsys.readouterr().err == ""


def test_truthy_writes_json_line_to_stderr(monkeypatch, capsys):
    monkeypatch.setenv("WIKI_PROFILE", "1")
    with profile.span("stage", n=1) as meta:
        meta["x"] = 2
    err = capsys.readouterr().err
    assert err.startswith("[wiki-profile] ")
    record = json.loads(err.removeprefix("[wiki-profile] "))
    assert record["span"] == "stage"
    assert record["n"] == 1 and record["x"] == 2
    assert isinstance(record["seconds"], float)


def test_path_value_appends_to_file(monkeypatch, tmp_path, capsys):
    target = tmp_path / "profile.jsonl"
    monkeypatch.setenv("WIKI_PROFILE", str(target))
    with profile.span("a"):
        pass
    profile.event("b", k=3)
    lines = [json.loads(line) for line in target.read_text().splitlines()]
    assert [r["span"] for r in lines] == ["a", "b"]
    assert lines[1]["seconds"] is None and lines[1]["k"] == 3
    assert capsys.readouterr().err == ""


def test_meta_may_carry_a_name_key(monkeypatch, capsys):
    # ingest passes name=<entity>; the stage name is positional-only so no clash.
    monkeypatch.setenv("WIKI_PROFILE", "1")
    with profile.span("resolve", name="Bimba"):
        pass
    profile.event("e", name="x")
    assert capsys.readouterr().err.count('"name"') == 2
    monkeypatch.delenv("WIKI_PROFILE")
    with profile.span("resolve", name="Bimba"):
        pass


def test_span_reraises_and_still_logs(monkeypatch, capsys):
    monkeypatch.setenv("WIKI_PROFILE", "1")
    try:
        with profile.span("boom"):
            raise ValueError("x")
    except ValueError:
        pass
    else:
        raise AssertionError("span swallowed the exception")
    assert '"span": "boom"' in capsys.readouterr().err


def test_unwritable_path_is_swallowed(monkeypatch, tmp_path):
    monkeypatch.setenv("WIKI_PROFILE", str(tmp_path / "missing-dir" / "p.jsonl"))
    with profile.span("stage"):
        pass


def test_symlink_target_is_not_followed(monkeypatch, tmp_path):
    real = tmp_path / "real.jsonl"
    real.write_text("")
    link = tmp_path / "link.jsonl"
    link.symlink_to(real)
    monkeypatch.setenv("WIKI_PROFILE", str(link))
    with profile.span("stage"):
        pass
    assert real.read_text() == ""
