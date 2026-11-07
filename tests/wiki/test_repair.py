"""Chain-relation repair: ``wiki/repair.py`` and the ``repair-chain-relations`` CLI.

T18 (dry run: no writes, three kinds, ``untagged`` list, ``select.name`` read, a confirmed
untagged ``remember ...`` log is ``mixed``) and T19 (write mode: exit 2 / 3 / 1, confirmed
ids in the digest, link-backed ids kept, fsynced backup before the first PATCH, file and
symlink refused, lock busy, partial) for Aldeia-IT/aldeia-box#1486 (AC4, AC13).
Anytype is the ``FakeWiki`` respx fake; dry-run tests use ``read_only=True`` and assert zero
writes. The result dicts' key names are not fixed by the spec beyond ``digest``,
``untagged`` and the plan items, so the helpers below find the kind and the items by value.
"""

import json
import os
import re
import stat

import pytest
import respx

from anytype_llm_wiki.wiki import cli, repair
from anytype_llm_wiki.wiki.util import space_ingest_lock

from .fakes import ANYTYPE_BASE, SPACE, FakeWiki, prop_value

E1, E2, E3, C1, Q1 = "ent-1", "ent-2", "ent-3", "con-1", "qry-1"
KINDS = ("ingest-only", "mixed", "unknown")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
SPENT = "f" * 64


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("ANYTYPE_API_KEY", "test-key")
    monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
    monkeypatch.setenv("ANYTYPE_API_VERSION", "2025-11-08")
    monkeypatch.setenv("WIKI_LOCK_DIR", str(tmp_path / "locks"))


# -- builders and result readers -------------------------------------------


def _sel(key, name):
    return {"key": key, "select": {"name": name}}


def _log(oid, name, action=None):
    props = [_sel("wiki_action", action)] if action else []
    return {"id": oid, "name": name, "type": {"key": "wiki_log"}, "properties": props}


def _source(oid, name, source_type=None):
    props = [_sel("wiki_source_type", source_type)] if source_type else []
    return {"id": oid, "name": name, "type": {"key": "wiki_source"}, "properties": props}


def _entity(oid, name, rels=()):
    return {
        "id": oid,
        "name": name,
        "type": {"key": "wiki_entity"},
        "properties": [{"key": "wiki_relations", "objects": list(rels)}],
    }


def _kind(result):
    """The first classification string found anywhere in a result dict."""
    if isinstance(result, str):
        return result if result in KINDS else None
    if isinstance(result, dict):
        for value in result.values():
            found = _kind(value)
            if found:
                return found
    if isinstance(result, list):
        for value in result:
            found = _kind(value)
            if found:
                return found
    return None


def _deep(result, key):
    if isinstance(result, dict):
        if key in result:
            return result[key]
        for value in result.values():
            found = _deep(value, key)
            if found is not None:
                return found
    return None


def _items(plan):
    """The plan items: dicts carrying ``object_id`` and ``clear``, wherever they sit."""
    out = []

    def walk(node):
        if isinstance(node, dict):
            if "object_id" in node and "clear" in node:
                out.append(node)
            else:
                for v in node.values():
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(plan)
    return out


def _item(plan, object_id):
    return next((i for i in _items(plan) if i["object_id"] == object_id), None)


def _ids(entries):
    return [e["id"] if isinstance(e, dict) else e for e in entries]


def _world(
    fake: FakeWiki,
    *,
    ingest_log=True,
    remember_log=False,
    agent_source=False,
    untagged_sources=(),
    untagged_logs=(),
    link=None,
):
    """A space with entities e1..e3, a concept, a query object and chain relations.

    e1 -> [e2, e3, qry-1]; e2 -> [e1, ghost]; e3 -> [e1]; con-1 -> [e2]. ``link`` is
    ``"fwd"`` (e1 -[x]-> e3) or ``"rev"`` (e3 -[x]-> e1): the pair e1/e3 is link-backed.
    """
    fake.seed("wiki_entity", "Bimba", _entity(E1, "", [E2, E3, Q1])["properties"], E1)
    fake.seed(
        "wiki_entity", "Pastinha",
        [{"key": "wiki_relations", "objects": [E1, "ghost"]}], E2,
    )
    fake.seed("wiki_entity", "Traira", [{"key": "wiki_relations", "objects": [E1]}], E3)
    fake.seed("wiki_concept", "Regional", [{"key": "wiki_related", "objects": [E2]}], C1)
    fake.seed("wiki_query", "What is Regional?", None, Q1)
    if ingest_log:
        fake.seed("wiki_log", "ingest https://x", [_sel("wiki_action", "ingest")], "log-1")
    if remember_log:
        fake.seed("wiki_log", "remember note", [_sel("wiki_action", "remember")], "log-2")
    fake.seed("wiki_source", "Page", [_sel("wiki_source_type", "document")], "src-1")
    if agent_source:
        fake.seed("wiki_source", "Agent note", [_sel("wiki_source_type", "agent")], "src-2")
    for sid in untagged_sources:
        fake.seed("wiki_source", f"Old {sid}", None, sid)
    for lid in untagged_logs:
        fake.seed("wiki_log", f"ingest old {lid}", None, lid)
    if link:
        a, b = (E1, E3) if link == "fwd" else (E3, E1)
        fake.seed(
            "wiki_link",
            "link x",
            [
                {"key": "wiki_link_from", "objects": [a]},
                {"key": "wiki_link_to", "objects": [b]},
                {"key": "wiki_link_label", "text": "student of"},
                {"key": "wiki_link_sources", "objects": ["src-1"]},
            ],
            "lnk-1",
        )


def _fake(**kw):
    world = {k: kw.pop(k) for k in list(kw) if k not in ("read_only",)}
    fake = FakeWiki(serve_objects=True, read_only=kw.get("read_only", False))
    fake.install()
    _world(fake, **world)
    return fake


def _main(argv):
    try:
        return cli.main(argv)
    except SystemExit as exc:
        return exc.code


def _cli(*args):
    return _main(["repair-chain-relations", "--space-id", SPACE, *args])


def _no_writes(fake):
    assert fake.blocked == [] and fake.patch_attempts == [] and fake.created == []


def _write_args(digest, backup, *extra):
    return ["--clear-ingest-only", "--expect-digest", digest, "--backup", str(backup), *extra]


def _live_digest(capsys, *extra):
    capsys.readouterr()
    assert _cli("--json", *extra) == 0
    return _deep(json.loads(capsys.readouterr().out), "digest")


# -- classify_space (T18) --------------------------------------------------


class TestClassifySpace:
    def test_ingest_log_and_document_source_is_ingest_only(self):
        objs = [_log("l1", "ingest x", "ingest"), _source("s1", "Page", "document")]
        out = repair.classify_space(objs)
        assert _kind(out) == "ingest-only"
        assert _deep(out, "untagged") == []

    def test_empty_space_is_unknown(self):
        assert _kind(repair.classify_space([])) == "unknown"

    def test_space_with_no_ingest_or_remember_log_is_unknown(self):
        assert _kind(repair.classify_space([_source("s1", "Page", "document")])) == "unknown"

    def test_other_objects_are_ignored(self):
        objs = [_log("l1", "ingest x", "ingest"), _entity("e1", "A")]
        assert _kind(repair.classify_space(objs)) == "ingest-only"

    @pytest.mark.parametrize("source_type", ["agent", "conversation"])
    def test_agent_or_conversation_source_is_mixed(self, source_type):
        objs = [_log("l1", "ingest x", "ingest"), _source("s1", "Note", source_type)]
        assert _kind(repair.classify_space(objs)) == "mixed"

    def test_remember_log_is_mixed(self):
        objs = [_log("l1", "ingest x", "ingest"), _log("l2", "remember n", "remember")]
        assert _kind(repair.classify_space(objs)) == "mixed"

    def test_only_a_remember_log_is_mixed_not_unknown(self):
        assert _kind(repair.classify_space([_log("l2", "remember n", "remember")])) == "mixed"

    def test_other_actions_do_not_make_a_space_mixed(self):
        objs = [_log("l1", "ingest x", "ingest"), _log("l3", "lint run", "lint")]
        assert _kind(repair.classify_space(objs)) == "ingest-only"

    def test_the_action_is_read_from_select_name(self):
        objs = [
            {
                "id": "l1", "name": "ingest x", "type": {"key": "wiki_log"},
                "properties": [{"key": "wiki_action", "select": {"id": "tag-9", "name": "remember"}}],
            }
        ]
        assert _kind(repair.classify_space(objs)) == "mixed"

    def test_a_text_property_does_not_count_as_the_action_tag(self):
        objs = [
            {
                "id": "l1", "name": "ingest x", "type": {"key": "wiki_log"},
                "properties": [{"key": "wiki_action", "text": "ingest"}],
            }
        ]
        out = repair.classify_space(objs)
        assert _kind(out) == "unknown"
        assert [u["id"] for u in _deep(out, "untagged")] == ["l1"]

    def test_untagged_source_makes_the_space_unknown_and_is_listed(self):
        objs = [_log("l1", "ingest x", "ingest"), _source("old-1", "Old page")]
        out = repair.classify_space(objs)
        assert _kind(out) == "unknown"
        (entry,) = _deep(out, "untagged")
        assert entry["id"] == "old-1" and entry["name"] == "Old page"
        assert entry["type"] == "wiki_source"

    def test_untagged_log_makes_the_space_unknown_and_is_listed(self):
        objs = [_log("l1", "ingest x", "ingest"), _log("old-l", "ingest older")]
        out = repair.classify_space(objs)
        assert _kind(out) == "unknown"
        (entry,) = _deep(out, "untagged")
        assert entry["id"] == "old-l" and entry["type"] == "wiki_log"

    def test_confirmed_untagged_ids_count_as_ingest_evidence(self):
        objs = [_log("l1", "ingest x", "ingest"), _source("old-1", "Old page")]
        out = repair.classify_space(objs, confirmed_untagged=frozenset({"old-1"}))
        assert _kind(out) == "ingest-only"

    def test_confirmed_untagged_ids_alone_are_not_ingest_log_evidence(self):
        objs = [_source("old-1", "Old page")]
        out = repair.classify_space(objs, confirmed_untagged=frozenset({"old-1"}))
        assert _kind(out) == "unknown"

    def test_one_unconfirmed_untagged_object_keeps_the_space_unknown(self):
        objs = [
            _log("l1", "ingest x", "ingest"),
            _source("old-1", "Old page"),
            _source("old-2", "Older page"),
        ]
        out = repair.classify_space(objs, confirmed_untagged=frozenset({"old-1"}))
        assert _kind(out) == "unknown"
        assert [u["id"] for u in _deep(out, "untagged")] == ["old-2"]

    def test_confirmed_untagged_remember_log_is_mixed(self):
        objs = [_log("l1", "ingest x", "ingest"), _log("old-r", "remember an old note")]
        out = repair.classify_space(objs, confirmed_untagged=frozenset({"old-r"}))
        assert _kind(out) == "mixed"

    def test_a_remember_named_log_tagged_ingest_is_mixed(self):
        objs = [_log("l1", "remember old note", "ingest")]
        assert _kind(repair.classify_space(objs)) == "mixed"

    def test_untagged_remember_log_stays_untagged_until_confirmed(self):
        objs = [_log("l1", "ingest x", "ingest"), _log("old-r", "remember an old note")]
        out = repair.classify_space(objs)
        assert "old-r" in [u["id"] for u in _deep(out, "untagged")]
        assert _kind(out) in ("unknown", "mixed")


# -- plan_chain_repair (T18, T19: link-backed ids) -------------------------


class TestPlanChainRepair:
    @respx.mock
    def test_dry_run_plan_reads_only(self):
        fake = _fake(read_only=True)
        plan = repair.plan_chain_repair(SPACE)
        assert _kind(plan) == "ingest-only"
        assert HEX64.match(plan["digest"])
        _no_writes(fake)

    @respx.mock
    def test_plan_item_shape(self):
        _fake(link="fwd", read_only=True)
        plan = repair.plan_chain_repair(SPACE)
        e1 = _item(plan, E1)
        assert e1["key"] == "wiki_relations" and e1["name"] == "Bimba"
        assert _ids(e1["clear"]) == [E2]
        assert e1["clear"][0]["name"] == "Pastinha"
        assert list(e1["keep"]) == [E3, Q1]

    @respx.mock
    def test_concept_uses_wiki_related(self):
        _fake(read_only=True)
        c1 = _item(repair.plan_chain_repair(SPACE), C1)
        assert c1["key"] == "wiki_related" and _ids(c1["clear"]) == [E2]

    @respx.mock
    @pytest.mark.parametrize("direction", ["fwd", "rev"])
    def test_a_link_in_either_direction_keeps_the_pair(self, direction):
        _fake(link=direction, read_only=True)
        plan = repair.plan_chain_repair(SPACE)
        assert E3 in _item(plan, E1)["keep"]
        e3 = _item(plan, E3)
        assert e3 is None or (_ids(e3["clear"]) == [] and E1 in e3["keep"])

    @respx.mock
    def test_without_a_link_the_pair_is_cleared_on_both_sides(self):
        _fake(read_only=True)
        plan = repair.plan_chain_repair(SPACE)
        assert _ids(_item(plan, E1)["clear"]) == [E2, E3]
        assert _ids(_item(plan, E3)["clear"]) == [E1]

    @respx.mock
    def test_ids_that_are_not_entities_or_concepts_are_kept(self):
        _fake(read_only=True)
        plan = repair.plan_chain_repair(SPACE)
        assert Q1 in _item(plan, E1)["keep"]
        assert "ghost" in _item(plan, E2)["keep"]

    @respx.mock
    def test_digest_is_stable_and_follows_the_plan(self):
        fake = _fake(read_only=True)
        first = repair.plan_chain_repair(SPACE)["digest"]
        assert repair.plan_chain_repair(SPACE)["digest"] == first
        fake.objects[E2]["properties"] = [{"key": "wiki_relations", "objects": [E1, E3]}]
        assert repair.plan_chain_repair(SPACE)["digest"] != first

    @respx.mock
    def test_digest_ignores_kept_ids(self):
        fake = _fake(read_only=True)
        first = repair.plan_chain_repair(SPACE)["digest"]
        fake.objects[E2]["properties"] = [{"key": "wiki_relations", "objects": [E1, "ghost", "g2"]}]
        assert repair.plan_chain_repair(SPACE)["digest"] == first

    @respx.mock
    def test_digest_holds_the_kind(self):
        fake = _fake(read_only=True)
        first = repair.plan_chain_repair(SPACE)["digest"]
        fake.seed("wiki_log", "remember n", [_sel("wiki_action", "remember")], "log-9")
        plan = repair.plan_chain_repair(SPACE)
        assert _kind(plan) == "mixed" and plan["digest"] != first

    @respx.mock
    def test_confirmed_ids_are_part_of_the_digest(self):
        fake = _fake(untagged_sources=["old-1", "old-2"], read_only=True)
        a = repair.plan_chain_repair(SPACE, confirmed_untagged=frozenset({"old-1", "old-2"}))
        b = repair.plan_chain_repair(SPACE, confirmed_untagged=frozenset({"old-1"}))
        assert HEX64.match(a["digest"]) and a["digest"] != b["digest"]
        assert repair.plan_chain_repair(SPACE, confirmed_untagged=frozenset({"old-2", "old-1"}))[
            "digest"
        ] == a["digest"]
        _no_writes(fake)

    @respx.mock
    def test_three_kinds_from_the_wire(self):
        _fake(untagged_sources=["old-1"], read_only=True)
        assert _kind(repair.plan_chain_repair(SPACE)) == "unknown"
        confirmed = frozenset({"old-1"})
        assert _kind(repair.plan_chain_repair(SPACE, confirmed_untagged=confirmed)) == "ingest-only"

    @respx.mock
    def test_untagged_list_in_the_plan(self):
        _fake(untagged_sources=["old-1"], untagged_logs=["old-l"], read_only=True)
        plan = repair.plan_chain_repair(SPACE)
        assert sorted(u["id"] for u in _deep(plan, "untagged")) == ["old-1", "old-l"]


# -- the CLI: dry run and argparse (T18, T19) ------------------------------


class TestCliParsing:
    @pytest.mark.parametrize("digest", ["a" * 63, "a" * 65, "A" * 64, "g" * 64, ""])
    def test_digest_must_be_64_lowercase_hex(self, digest, tmp_path):
        assert _cli(*_write_args(digest, tmp_path / "b.json")) == 2

    def test_both_modes_is_an_argparse_error(self, tmp_path):
        assert _cli("--dry-run", *_write_args(SPENT, tmp_path / "b.json")) == 2

    def test_write_mode_needs_a_digest(self, tmp_path):
        assert _cli("--clear-ingest-only", "--backup", str(tmp_path / "b.json")) == 2

    def test_write_mode_needs_a_backup(self):
        assert _cli("--clear-ingest-only", "--expect-digest", SPENT) == 2


class TestCliDryRun:
    @respx.mock
    @pytest.mark.parametrize("flags", [[], ["--dry-run"]])
    def test_default_and_explicit_dry_run_write_nothing(self, flags, capsys):
        fake = _fake(read_only=True)
        assert _cli("--json", *flags) == 0
        out = json.loads(capsys.readouterr().out)
        assert _kind(out) == "ingest-only" and HEX64.match(_deep(out, "digest"))
        assert {i["object_id"] for i in _items(out)} >= {E1, E2, C1}
        _no_writes(fake)

    @respx.mock
    def test_plain_output_names_every_cleared_id(self, capsys):
        fake = _fake(read_only=True)
        assert _cli() == 0
        text = capsys.readouterr().out
        assert E1 in text and E2 in text and _deep(repair.plan_chain_repair(SPACE), "digest") in text
        _no_writes(fake)

    @respx.mock
    @pytest.mark.parametrize(
        ("world", "kind"),
        [({}, "ingest-only"), ({"remember_log": True}, "mixed"), ({"ingest_log": False}, "unknown")],
    )
    def test_dry_run_reports_each_kind_with_exit_0(self, world, kind, capsys):
        fake = _fake(read_only=True, **world)
        assert _cli("--json") == 0
        assert _kind(json.loads(capsys.readouterr().out)) == kind
        _no_writes(fake)

    @respx.mock
    def test_dry_run_lists_untagged_objects(self, capsys):
        fake = _fake(untagged_sources=["old-1"], read_only=True)
        assert _cli("--json") == 0
        out = json.loads(capsys.readouterr().out)
        assert _kind(out) == "unknown"
        assert [u["id"] for u in _deep(out, "untagged")] == ["old-1"]
        _no_writes(fake)

    @respx.mock
    def test_exact_confirm_list_makes_the_dry_run_ingest_only(self, tmp_path, capsys):
        fake = _fake(untagged_sources=["old-1", "old-2"], read_only=True)
        confirm = tmp_path / "confirm.json"
        confirm.write_text(json.dumps(["old-2", "old-1"]))
        assert _cli("--json", "--confirm-untagged", str(confirm)) == 0
        assert _kind(json.loads(capsys.readouterr().out)) == "ingest-only"
        _no_writes(fake)

    @respx.mock
    def test_confirmed_untagged_remember_log_is_mixed(self, tmp_path, capsys):
        fake = _fake(read_only=True)
        fake.seed("wiki_log", "remember an old note", None, "old-r")
        confirm = tmp_path / "confirm.json"
        confirm.write_text(json.dumps(["old-r"]))
        assert _cli("--json", "--confirm-untagged", str(confirm)) == 0
        assert _kind(json.loads(capsys.readouterr().out)) == "mixed"
        _no_writes(fake)

    @respx.mock
    @pytest.mark.parametrize(
        "ids", [["old-1"], ["old-1", "old-2", "zzz"], [], ["zzz"]], ids=["short", "foreign", "empty", "wrong"]
    )
    @pytest.mark.parametrize("mode", ["dry", "write"])
    def test_confirm_list_must_equal_the_untagged_ids(self, ids, mode, tmp_path):
        fake = _fake(untagged_sources=["old-1", "old-2"], read_only=(mode == "dry"))
        confirm = tmp_path / "confirm.json"
        confirm.write_text(json.dumps(ids))
        extra = ["--confirm-untagged", str(confirm)]
        if mode == "write":
            extra = _write_args(SPENT, tmp_path / "b.json", *extra)
        assert _cli(*extra) == 2
        assert fake.patch_attempts == [] and not (tmp_path / "b.json").exists()


# -- the CLI: write mode (T19, AC4, AC13) ----------------------------------


class TestCliWriteMode:
    @respx.mock
    def test_write_clears_the_planned_ids_and_keeps_the_rest(self, tmp_path, capsys):
        fake = _fake(link="fwd")
        digest = _live_digest(capsys)
        assert _cli(*_write_args(digest, tmp_path / "b.json")) == 0
        assert prop_value(fake.objects[E1], "wiki_relations") == [E3, Q1]
        assert prop_value(fake.objects[E2], "wiki_relations") == ["ghost"]
        assert prop_value(fake.objects[E3], "wiki_relations") == [E1]
        assert prop_value(fake.objects[C1], "wiki_related") == []

    @respx.mock
    @pytest.mark.parametrize("direction", ["fwd", "rev"])
    def test_link_backed_ids_are_never_cleared(self, direction, tmp_path, capsys):
        fake = _fake(link=direction)
        digest = _live_digest(capsys)
        assert _cli(*_write_args(digest, tmp_path / "b.json")) == 0
        assert E3 in prop_value(fake.objects[E1], "wiki_relations")
        assert E1 in prop_value(fake.objects[E3], "wiki_relations")
        sent = [p for _, p in fake.patch_attempts]
        for payload in sent:
            for prop in payload["properties"]:
                assert prop["key"] in ("wiki_relations", "wiki_related")

    @respx.mock
    def test_only_relation_properties_of_entities_and_concepts_are_patched(self, tmp_path, capsys):
        fake = _fake()
        digest = _live_digest(capsys)
        assert _cli(*_write_args(digest, tmp_path / "b.json")) == 0
        assert {oid for oid, _ in fake.patch_attempts} <= {E1, E2, E3, C1}
        assert fake.created == []

    @respx.mock
    @pytest.mark.parametrize("world", [{"remember_log": True}, {"ingest_log": False}, {"agent_source": True}])
    def test_mixed_or_unknown_space_is_refused_with_exit_2(self, world, tmp_path):
        fake = _fake(**world)
        backup = tmp_path / "b.json"
        assert _cli(*_write_args(SPENT, backup)) == 2
        assert fake.patch_attempts == [] and not backup.exists()

    @respx.mock
    def test_unconfirmed_untagged_sources_are_refused(self, tmp_path):
        fake = _fake(untagged_sources=["old-1"])
        assert _cli(*_write_args(SPENT, tmp_path / "b.json")) == 2
        assert fake.patch_attempts == []

    @respx.mock
    def test_digest_mismatch_exits_3_prints_the_live_digest_and_writes_nothing(
        self, tmp_path, capsys
    ):
        fake = _fake()
        live = _live_digest(capsys)
        backup = tmp_path / "b.json"
        assert _cli(*_write_args(SPENT, backup)) == 3
        shown = capsys.readouterr()
        assert live in shown.out + shown.err
        assert fake.patch_attempts == [] and not backup.exists()

    @respx.mock
    def test_digest_from_before_a_change_is_a_mismatch(self, tmp_path, capsys):
        fake = _fake()
        stale = _live_digest(capsys)
        fake.objects[E2]["properties"] = [{"key": "wiki_relations", "objects": [E1, E3]}]
        assert _cli(*_write_args(stale, tmp_path / "b.json")) == 3
        assert fake.patch_attempts == []

    @respx.mock
    def test_confirmed_untagged_space_can_be_written_with_its_digest(self, tmp_path, capsys):
        fake = _fake(untagged_sources=["old-1"])
        confirm = tmp_path / "confirm.json"
        confirm.write_text(json.dumps(["old-1"]))
        digest = _live_digest(capsys, "--confirm-untagged", str(confirm))
        # The digest without the list is the refusal digest of an unknown space.
        assert _cli(*_write_args(digest, tmp_path / "b.json", "--confirm-untagged", str(confirm))) == 0
        assert prop_value(fake.objects[E2], "wiki_relations") == ["ghost"]

    @respx.mock
    def test_confirmed_digest_does_not_open_the_unconfirmed_write(self, tmp_path, capsys):
        fake = _fake(untagged_sources=["old-1"])
        confirm = tmp_path / "confirm.json"
        confirm.write_text(json.dumps(["old-1"]))
        digest = _live_digest(capsys, "--confirm-untagged", str(confirm))
        assert _cli(*_write_args(digest, tmp_path / "b.json")) == 2
        assert fake.patch_attempts == []


class TestBackup:
    @respx.mock
    def test_backup_holds_the_prior_ids_and_is_private(self, tmp_path, capsys):
        _fake(link="fwd")
        backup = tmp_path / "b.json"
        digest = _live_digest(capsys)
        assert _cli(*_write_args(digest, backup)) == 0
        data = json.loads(backup.read_text())
        assert data["space_id"] == SPACE and data["digest"] == digest and data["written_at"]
        prior = {(o["object_id"], o["key"]): list(o["prior_ids"]) for o in data["objects"]}
        assert prior[(E1, "wiki_relations")] == [E2, E3, Q1]
        assert prior[(E2, "wiki_relations")] == [E1, "ghost"]
        assert prior[(C1, "wiki_related")] == [E2]
        assert stat.S_IMODE(os.stat(backup).st_mode) == 0o600

    @respx.mock
    def test_backup_is_fsynced_before_the_first_patch(self, tmp_path, capsys, monkeypatch):
        fake = FakeWiki(serve_objects=True)
        events: list[str] = []
        real_patch, real_fsync = fake._patch, os.fsync
        backup = tmp_path / "b.json"

        def spy_patch(request):
            events.append("patch")
            events.append("backup-complete" if _complete(backup) else "backup-missing")
            return real_patch(request)

        def spy_fsync(fd):
            events.append("fsync")
            return real_fsync(fd)

        fake._patch = spy_patch
        fake.install()
        _world(fake)
        digest = _live_digest(capsys)
        events.clear()
        monkeypatch.setattr(os, "fsync", spy_fsync)
        assert _cli(*_write_args(digest, backup)) == 0
        assert "fsync" in events and "patch" in events
        assert events.index("fsync") < events.index("patch")
        assert "backup-missing" not in events

    @respx.mock
    def test_existing_backup_file_is_refused_and_untouched(self, tmp_path, capsys):
        fake = _fake()
        digest = _live_digest(capsys)
        backup = tmp_path / "b.json"
        backup.write_text("precious")
        assert _cli(*_write_args(digest, backup)) in (1, 2)
        assert backup.read_text() == "precious" and fake.patch_attempts == []

    @respx.mock
    def test_symlink_backup_is_refused_and_its_target_untouched(self, tmp_path, capsys):
        fake = _fake()
        digest = _live_digest(capsys)
        target = tmp_path / "target.json"
        target.write_text("precious")
        link = tmp_path / "b.json"
        link.symlink_to(target)
        assert _cli(*_write_args(digest, link)) in (1, 2)
        assert target.read_text() == "precious" and fake.patch_attempts == []

    @respx.mock
    def test_dangling_symlink_backup_is_refused_and_creates_nothing(self, tmp_path, capsys):
        fake = _fake()
        digest = _live_digest(capsys)
        target = tmp_path / "missing.json"
        link = tmp_path / "b.json"
        link.symlink_to(target)
        assert _cli(*_write_args(digest, link)) in (1, 2)
        assert not target.exists() and fake.patch_attempts == []

    @respx.mock
    def test_unwritable_backup_location_exits_1_with_no_patch(self, tmp_path, capsys):
        fake = _fake()
        digest = _live_digest(capsys)
        assert _cli(*_write_args(digest, tmp_path / "no-such-dir" / "b.json")) == 1
        assert fake.patch_attempts == []


def _complete(path) -> bool:
    try:
        return bool(json.loads(path.read_text()).get("objects"))
    except (OSError, ValueError):
        return False


class TestLockAndPartial:
    @respx.mock
    def test_busy_lock_exits_1_and_writes_nothing(self, tmp_path, capsys):
        fake = _fake()
        digest = _live_digest(capsys)
        backup = tmp_path / "b.json"
        with space_ingest_lock(SPACE, "another writer"):
            assert _cli(*_write_args(digest, backup)) == 1
        assert fake.patch_attempts == [] and not backup.exists()

    @respx.mock
    def test_dry_run_does_not_need_the_lock(self):
        fake = _fake(read_only=True)
        with space_ingest_lock(SPACE, "another writer"):
            assert _cli("--json") == 0
        _no_writes(fake)

    @respx.mock
    def test_the_lock_is_released_after_a_write(self, tmp_path, capsys):
        _fake()
        digest = _live_digest(capsys)
        assert _cli(*_write_args(digest, tmp_path / "b.json")) == 0
        with space_ingest_lock(SPACE, "next writer"):
            pass

    @respx.mock
    def test_a_failed_patch_gives_partial_and_exit_1(self, tmp_path, capsys):
        fake = _fake()
        digest = _live_digest(capsys)
        fake.fail("PATCH", object_id=E2)
        backup = tmp_path / "b.json"
        assert _cli("--json", *_write_args(digest, backup)) == 1
        assert backup.exists()
        assert prop_value(fake.objects[E1], "wiki_relations") == [Q1]

    @respx.mock
    def test_partial_result_names_status_partial(self, tmp_path, capsys):
        fake = _fake()
        digest = _live_digest(capsys)
        fake.fail("PATCH", object_id=E2)
        capsys.readouterr()
        _cli("--json", *_write_args(digest, tmp_path / "b.json"))
        assert '"partial"' in capsys.readouterr().out


class TestApplyChainRepair:
    """The API behind write mode."""

    @respx.mock
    def test_apply_with_the_live_digest_clears_and_backs_up(self, tmp_path):
        fake = _fake(link="rev")
        digest = repair.plan_chain_repair(SPACE)["digest"]
        backup = tmp_path / "b.json"
        result = repair.apply_chain_repair(SPACE, expect_digest=digest, backup_path=str(backup))
        assert result.get("status") != "partial"
        assert backup.exists()
        assert prop_value(fake.objects[E2], "wiki_relations") == ["ghost"]
        assert E1 in prop_value(fake.objects[E3], "wiki_relations")

    @respx.mock
    def test_apply_with_a_wrong_digest_writes_nothing(self, tmp_path):
        fake = _fake()
        backup = tmp_path / "b.json"
        outcome = None
        try:
            outcome = repair.apply_chain_repair(SPACE, expect_digest=SPENT, backup_path=str(backup))
        except NotImplementedError:
            raise
        except Exception as exc:  # noqa: BLE001 - a refusal may raise or return
            outcome = exc
        assert outcome is not None
        assert fake.patch_attempts == [] and not backup.exists()
