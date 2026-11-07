"""Review round 1 fixes for repair and its CLI (Aldeia-IT/aldeia-box#1486): L3, L4, L5, N8, N9."""

import json
import os
import stat

import respx

from anytype_llm_wiki.wiki import cli, repair
from anytype_llm_wiki.wiki.wiki_client import WikiClient

from .fakes import SPACE
from .test_repair import (  # noqa: F401  (the autouse environment fixture comes along)
    E1,
    E2,
    E3,
    _cli,
    _env,
    _fake,
    _item,
    _log,
)


class TestPrintedPlanEscapesNames:
    """L3: a control character in an object name cannot hide or spoof a plan line."""

    def test_printable_escapes_controls_and_keeps_letters(self):
        assert cli._printable("Mestre João\x1b[2K\rclear:") == "Mestre João\\x1b[2K\\rclear:"
        assert cli._printable("a\u202eb") == "a\\u202eb"

    @respx.mock
    def test_dry_run_output_has_no_raw_escape_or_carriage_return(self, capsys):
        fake = _fake(read_only=True)
        fake.objects[E2]["name"] = "Pastinha\x1b[2K\rclear:     forged"
        assert _cli() == 0
        out = capsys.readouterr().out
        assert "\x1b" not in out and "\r" not in out
        assert "Pastinha\\x1b[2K\\rclear:" in out


class TestRepairRobustness:
    @respx.mock
    def test_a_builtin_connection_error_on_a_patch_is_partial_not_error(self, monkeypatch, tmp_path):
        _fake()
        plan = repair.plan_chain_repair(SPACE)

        def boom(self, *a, **kw):
            raise ConnectionError("reset by peer")

        monkeypatch.setattr(WikiClient, "update_object", boom)
        result = repair.apply_chain_repair(
            SPACE, expect_digest=plan["digest"], backup_path=str(tmp_path / "b.json")
        )
        assert result["status"] == "partial", result
        assert any("repair_failed" in w for w in result["warnings"])

    @respx.mock
    def test_the_backup_directory_is_fsynced_after_the_file(self, monkeypatch, tmp_path):
        _fake()
        plan = repair.plan_chain_repair(SPACE)
        synced = []
        real_fsync = os.fsync

        def spy_fsync(fd):
            synced.append("dir" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file")
            return real_fsync(fd)

        monkeypatch.setattr(os, "fsync", spy_fsync)
        result = repair.apply_chain_repair(
            SPACE, expect_digest=plan["digest"], backup_path=str(tmp_path / "b.json")
        )
        assert result["status"] == "ok", result
        assert synced[-2:] == ["file", "dir"], synced

    def test_a_non_string_log_name_does_not_crash_classification(self):
        bad = _log("log-x", "ignored", "ingest")
        bad["name"] = 12345
        assert repair.classify_space([bad])["kind"] == "ingest-only"


class TestMalformedLinkProtectsItsPair:
    """L5: a wiki_link with one from-id and one to-id keeps the pair, label or not."""

    @respx.mock
    def test_link_with_an_empty_label_keeps_the_index_ids(self):
        fake = _fake(link="fwd", read_only=True)
        fake.objects["lnk-1"]["properties"] = [
            p for p in fake.objects["lnk-1"]["properties"] if p["key"] != "wiki_link_label"
        ]
        plan = repair.plan_chain_repair(SPACE)
        assert E3 in _item(plan, E1)["keep"]
        assert _item(plan, E3)["clear"] == [] and E1 in _item(plan, E3)["keep"]

    @respx.mock
    def test_link_with_two_to_ids_protects_nothing(self):
        fake = _fake(link="fwd", read_only=True)
        for p in fake.objects["lnk-1"]["properties"]:
            if p["key"] == "wiki_link_to":
                p["objects"] = [E3, E2]
        plan = repair.plan_chain_repair(SPACE)
        assert [c["id"] for c in _item(plan, E3)["clear"]] == [E1]


class TestConfirmListChecks:
    @respx.mock
    def test_dry_run_with_a_confirm_list_lists_the_space_once(self, tmp_path, monkeypatch, capsys):
        _fake(untagged_sources=["old-1"], read_only=True)
        confirm = tmp_path / "c.json"
        confirm.write_text(json.dumps(["old-1"]))
        calls = []
        real = WikiClient.list_objects
        monkeypatch.setattr(
            WikiClient, "list_objects", lambda self, *a, **kw: calls.append(1) or real(self, *a, **kw)
        )
        assert _cli("--confirm-untagged", str(confirm)) == 0
        assert len(calls) == 1

    @respx.mock
    def test_dry_run_refuses_a_confirm_list_that_is_not_exact(self, tmp_path, capsys):
        _fake(untagged_sources=["old-1"], read_only=True)
        confirm = tmp_path / "c.json"
        confirm.write_text(json.dumps(["old-1", "nope"]))
        assert _cli("--confirm-untagged", str(confirm)) == 2
        assert "must equal the untagged ids" in capsys.readouterr().err

    @respx.mock
    def test_mixed_space_with_untagged_objects_refuses_as_kind(self, tmp_path, capsys):
        _fake(remember_log=True, untagged_sources=["old-1"])
        try:
            repair.apply_chain_repair(
                SPACE, expect_digest="f" * 64, backup_path=str(tmp_path / "b.json")
            )
        except repair.RepairRefusedError as refused:
            assert refused.reason == "kind"
        else:  # pragma: no cover
            raise AssertionError("expected a refusal")
