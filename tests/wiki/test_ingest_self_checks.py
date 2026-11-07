"""Self-conflicts and duplicates judged in the batched check (Aldeia-IT/aldeia-box#1486).

T26 (a page contradicting an earlier source: marker, needs-review, both kept, one
call), T27 (a judged duplicate tags the earlier unit; a hallucinated id nothing;
PATCH failures) and T29 (peer conflicts and the single-check fallback unchanged).
Anytype is the ``FakeWiki`` respx fake; extraction and the model call are stubbed.
"""

import socket

import pytest
import respx

from .fakes import ANYTYPE_BASE, SPACE, FakeWiki, prop_value

PAGE = "https://lalaue.example/page-two"
BIMBA, PASTINHA = "Mestre Bimba", "Mestre Pastinha"
ENT_B, ENT_P = "ent-b", "ent-p"
OLD_B = "Bimba founded Regional in 1932."
OLD_P = "Pastinha ran an academy."


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("ANYTYPE_API_KEY", "test-key")
    monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
    monkeypatch.setenv("ANYTYPE_API_VERSION", "2025-11-08")
    monkeypatch.setenv("WIKI_AUTO_REINDEX", "false")
    monkeypatch.setenv("WIKI_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.delenv("WIKI_EXTRACT_ENDPOINT", raising=False)
    from anytype_llm_wiki.wiki import fetch as fetch_mod
    from anytype_llm_wiki.wiki import ingest

    monkeypatch.setattr(
        fetch_mod.socket,
        "getaddrinfo",
        lambda host, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    monkeypatch.setattr(
        ingest, "_resolve_select_tag", lambda client, space, key, name: ("tag-review", False)
    )


class _Model:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.prompts: list[str] = []

    def __call__(self, base, prompt):
        self.prompts.append(prompt)
        return (self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]), None


def _model(monkeypatch, *answers) -> _Model:
    from anytype_llm_wiki.wiki import ingest

    fake = _Model(*answers)
    monkeypatch.setattr(ingest, "_call_ollama_prompt", fake)
    return fake


def _space() -> FakeWiki:
    from anytype_llm_wiki.wiki.types_schema import WIKI_SCHEMA_VERSION

    fake = FakeWiki(serve_objects=True, search_with_properties=True)
    fake.install()
    fake.seed(
        "wiki_log", "bootstrap", [{"key": "wiki_schema_version", "text": WIKI_SCHEMA_VERSION}],
        "log-schema-001",
    )
    fake.seed("wiki_entity", BIMBA, [{"key": "wiki_facts", "text": OLD_B}], ENT_B)
    fake.seed("wiki_entity", PASTINHA, [{"key": "wiki_facts", "text": OLD_P}], ENT_P)
    return fake


def _extract(monkeypatch, bimba: str, pastinha: str = "Pastinha taught Angola.") -> None:
    from anytype_llm_wiki.wiki import ingest

    result = {
        "entities": [
            {"name": BIMBA, "description": bimba},
            {"name": PASTINHA, "description": pastinha},
        ],
        "concepts": [],
    }
    monkeypatch.setattr(ingest, "extract", lambda **kw: result)


def _ingest():
    from anytype_llm_wiki.wiki.ingest import wiki_ingest

    return wiki_ingest(source=PAGE, space_id=SPACE)


def _batch(*entries):
    return {"results": [dict(check_id=cid, **body) for cid, body in entries]}


def _facts_patches(fake: FakeWiki, obj_id: str) -> list[dict]:
    return [
        p for p in fake.patches_of(obj_id)
        if any(q.get("key") == "wiki_facts" for q in p.get("properties", []))
    ]


class TestSelfConflict:
    """T26 / AC3: the page contradicts an earlier source of the same object."""

    @respx.mock
    def test_marker_needs_review_both_versions_kept_one_call(self, monkeypatch):
        fake = _space()
        _extract(monkeypatch, "Bimba founded Regional in 1937.")
        model = _model(monkeypatch, _batch(
            ("check_1", {"contradictions": [
                {"object_id": f"{ENT_B}#s0", "reason": "1932 vs 1937"}], "duplicates": []}),
            ("check_2", {"contradictions": [], "duplicates": []}),
        ))
        result = _ingest()
        assert result["status"] == "ok", result
        assert result["self_conflicts_flagged"] == 1
        text = prop_value(fake.objects[ENT_B], "wiki_facts")
        assert OLD_B in text and "Bimba founded Regional in 1937." in text
        sections = text.split("## Source: ")[1:]
        assert sections[0].splitlines()[1] == OLD_B, "the legacy section stays first"
        assert sections[-1].rstrip().endswith(
            "> [CONFLICT with unattributed (before per-source facts): 1932 vs 1937]"
        )
        flag = [
            p for p in fake.patches_of(ENT_B)
            if {"key": "wiki_status", "select": "tag-review"} in p.get("properties", [])
        ]
        assert len(flag) == 1
        assert len(model.prompts) == 1, "the self-check adds no model call"
        assert prop_value(fake.objects[ENT_P], "wiki_facts").count("> [CONFLICT") == 0

    @respx.mock
    def test_marker_patch_failure_still_flags_needs_review(self, monkeypatch):
        fake = _space()
        _extract(monkeypatch, "Bimba founded Regional in 1937.")
        _model(monkeypatch, _batch(
            ("check_1", {"contradictions": [
                {"object_id": f"{ENT_B}#s0", "reason": "1932 vs 1937"}], "duplicates": []}),
            ("check_2", {"contradictions": [], "duplicates": []}),
        ))
        # The marker PATCH is the second facts PATCH of Bimba (the merge is the first).
        fake.fail("PATCH", object_id=ENT_B, nth=2)
        result = _ingest()
        assert result["status"] == "partial", result
        assert "conflict_marker_write_failed" in result["warnings"]
        text = prop_value(fake.objects[ENT_B], "wiki_facts")
        assert "> [CONFLICT" not in text and OLD_B in text
        assert any(
            {"key": "wiki_status", "select": "tag-review"} in p.get("properties", [])
            for _oid, p in fake.patch_attempts
        )


class TestJudgedDuplicate:
    """T27: a judged duplicate tags the earlier unit; the new unit stays."""

    @respx.mock
    def test_duplicate_tags_the_earlier_unit_and_keeps_the_new_one(self, monkeypatch):
        fake = _space()
        _extract(monkeypatch, "Bimba founded Regional in 1932 (Salvador).")
        _model(monkeypatch, _batch(
            ("check_1", {"contradictions": [], "duplicates": [
                {"object_id": f"{ENT_B}#s0", "earlier": OLD_B,
                 "new": "Bimba founded Regional in 1932 (Salvador)."}]}),
            ("check_2", {"contradictions": []}),
        ))
        result = _ingest()
        assert result["status"] == "ok", result
        assert result["duplicates_tagged"] == 1
        label = "https://lalaue.example/page-two"
        text = prop_value(fake.objects[ENT_B], "wiki_facts")
        assert f"{OLD_B} [also: {label}]" in text
        assert "Bimba founded Regional in 1932 (Salvador)." in text
        assert "> [CONFLICT" not in text

    @respx.mock
    def test_hallucinated_section_id_tags_nothing(self, monkeypatch):
        fake = _space()
        _extract(monkeypatch, "Bimba founded Regional in 1932 (Salvador).")
        _model(monkeypatch, _batch(
            ("check_1", {"contradictions": [], "duplicates": [
                {"object_id": f"{ENT_B}#s9", "earlier": OLD_B,
                 "new": "Bimba founded Regional in 1932 (Salvador)."}]}),
            ("check_2", {"contradictions": []}),
        ))
        result = _ingest()
        assert result["duplicates_tagged"] == 0
        assert "[also:" not in prop_value(fake.objects[ENT_B], "wiki_facts")

    @respx.mock
    def test_tag_patch_failure_warns_and_keeps_the_text(self, monkeypatch):
        fake = _space()
        _extract(monkeypatch, "Bimba founded Regional in 1932 (Salvador).")
        _model(monkeypatch, _batch(
            ("check_1", {"contradictions": [], "duplicates": [
                {"object_id": f"{ENT_B}#s0", "earlier": OLD_B,
                 "new": "Bimba founded Regional in 1932 (Salvador)."}]}),
            ("check_2", {"contradictions": []}),
        ))
        fake.fail("PATCH", object_id=ENT_B, nth=2)
        result = _ingest()
        assert result["status"] == "partial"
        assert "duplicate_tag_write_failed" in result["warnings"]
        assert result["duplicates_tagged"] == 0
        assert "[also:" not in prop_value(fake.objects[ENT_B], "wiki_facts")


class TestPeerConflictsUnchanged:
    """T29: peer verdicts still become contradiction links; a failed check degrades."""

    @respx.mock
    def test_unparseable_batch_falls_back_to_the_single_check(self, monkeypatch):
        fake = _space()
        _extract(monkeypatch, "Bimba founded Regional in 1937.")
        model = _model(monkeypatch, None, {"contradictions": []})
        result = _ingest()
        assert result["status"] == "ok", result
        assert len(model.prompts) == 3, "one batch call, then one single call per check"
        assert result["self_conflicts_flagged"] == 0 and result["duplicates_tagged"] == 0
        assert "> [CONFLICT" not in prop_value(fake.objects[ENT_B], "wiki_facts")

    def test_peer_verdict_with_self_candidates_still_links_the_peer(self, monkeypatch):
        from anytype_llm_wiki.wiki import ingest

        written: list = []
        monkeypatch.setattr(
            ingest, "_write_contradiction_links",
            lambda client, rc, space, obj, target, peers, log: (written.append(peers) or 1, []),
        )
        monkeypatch.setattr(ingest, "_judge_contradiction_checks", lambda *a: {
            "check_1": {"contradictions": [{"object_id": "peer-1", "reason": "r"}],
                        "duplicates": []},
        })
        check = {
            "check_id": "check_1", "obj_id": "obj-1", "name": "O", "kind": "entity",
            "target": {"id": "obj-1", "properties": []},
            "candidates": [], "text_key": "wiki_facts", "label": "l", "source_id": "s",
            "earlier": (),
        }
        result = {"warnings": [], "contradictions_detected": 0}
        ingest._run_contradiction_checks([check], "space", None, None, result)
        assert written == [["peer-1"]] and result["contradictions_detected"] == 1


class TestSourceSummaryStaysOnTheSource:
    """T28 (spec section 8): the summary lives on the Source and is never copied into facts."""

    SUMMARY = "A page about the founding of Capoeira Regional in the 1930s."

    @respx.mock
    def test_ingest_keeps_the_summary_out_of_entity_and_concept_text(self, monkeypatch):
        from anytype_llm_wiki.wiki import ingest

        fake = _space()
        monkeypatch.setattr(ingest, "extract", lambda **kw: {
            "entities": [{"name": BIMBA, "description": "Bimba taught in Salvador."}],
            "concepts": [{"name": "Capoeira Regional", "definition": "A capoeira style."}],
            "summary": self.SUMMARY,
        })
        _model(monkeypatch, {"contradictions": [], "duplicates": []})
        result = _ingest()
        assert result["status"] == "ok", result
        (source,) = fake.created_of("wiki_source")
        assert prop_value(source, "wiki_summary") == self.SUMMARY
        for obj in fake.objects.values():
            if obj["type"]["key"] in ("wiki_entity", "wiki_concept"):
                for key in ("wiki_facts", "wiki_definition"):
                    assert self.SUMMARY not in (prop_value(obj, key) or ""), (obj["name"], key)

    @respx.mock
    def test_query_shows_the_source_neighbours_summary(self, monkeypatch):
        from .test_typed_links_surface import A, SRC1, _bootstrapped, _entity_props, _neighbour, _query

        fake = _bootstrapped()
        props = _entity_props([]) + [{"key": "wiki_sources", "objects": [SRC1]}]
        fake.seed("wiki_entity", "Mestre Bimba", props, A)
        fake.seed("wiki_source", "Page one", [{"key": "wiki_summary", "text": self.SUMMARY}], SRC1)
        result, prompts = _query(monkeypatch)
        assert _neighbour(result, SRC1) is not None, result["sources_consulted"]
        assert f"wiki_summary: {self.SUMMARY}" in prompts[0]
