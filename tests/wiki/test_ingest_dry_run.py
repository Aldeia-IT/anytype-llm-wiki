"""Tests for scripts/ingest_dry_run.py (Aldeia-IT/aldeia-box#1427 AC7).

The harness runs fetch -> extract() per URL, prints one JSON object per page and
touches nothing else: no Anytype or Qdrant client, no HTTP call besides the page
fetch and the Ollama extraction.
"""

import importlib.util
import json
import socket
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
import respx

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ingest_dry_run.py"
LALAUE = (Path(__file__).parent / "fixtures" / "pages" / "lalaue_shaped.html").read_text(
    encoding="utf-8"
)
OLLAMA = "http://127.0.0.1:11434"


def _load():
    spec = importlib.util.spec_from_file_location("ingest_dry_run", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stream(text: str) -> bytes:
    return (
        json.dumps({"response": text, "done": False}).encode()
        + b"\n"
        + json.dumps({"response": "", "done": True, "done_reason": "stop"}).encode()
        + b"\n"
    )


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("WIKI_EXTRACT_ENDPOINT", raising=False)
    from anytype_llm_wiki.wiki import fetch as fetch_mod

    monkeypatch.setattr(
        fetch_mod.socket,
        "getaddrinfo",
        lambda host, *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))
        ],
    )


EXTRACTED = {
    "entities": [
        {"name": "Mestre Bimba", "description": "Founded the first recognised school."},
        {"name": "founding_date_conflict", "description": "a label"},
    ],
    "concepts": [{"name": "Capoeira Regional", "definition": "A capoeira style."}],
    "relations": [{"source": "Mestre Bimba", "target": "Capoeira Regional"}],
}


class TestDryRunHarness:
    @respx.mock  # assert_all_mocked: any other HTTP call raises
    def test_one_json_object_per_page_and_no_other_http(self, capsys):
        respx.get("https://lalaue.example/acmb").mock(
            return_value=httpx.Response(200, text=LALAUE, headers={"content-type": "text/html"})
        )
        respx.get("https://spa.example/").mock(
            return_value=httpx.Response(
                200,
                text="<html><body><div id='root'></div></body></html>",
                headers={"content-type": "text/html"},
            )
        )
        generate = respx.post(f"{OLLAMA}/api/generate").mock(
            return_value=httpx.Response(200, content=_stream(json.dumps(EXTRACTED)))
        )

        rc = _load().main(
            ["--refuse-identifier-names", "https://lalaue.example/acmb", "https://spa.example/"]
        )
        assert rc == 0
        lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
        assert len(lines) == 2
        page, shell = (json.loads(ln) for ln in lines)

        assert page["url"] == "https://lalaue.example/acmb"
        assert page["chars_before_strip"] > page["chars_after_strip"] > 0
        assert page["excerpt"].startswith("# Associação De Capoeira Mestre Bimba")
        assert len(page["excerpt"]) <= 1000
        assert {e["name"] for e in page["entities"]} == {"Mestre Bimba", "founding_date_conflict"}
        assert page["entities"][0]["facts"]
        assert page["concepts"] == [{"name": "Capoeira Regional", "facts": "A capoeira style."}]
        assert page["relation_count"] == 1
        assert page["extraction_error"] is None
        assert page["truncated"] is None
        assert page["unusable"] is None
        assert page["refused_names"] == ["founding_date_conflict"]
        for key in ("fetch_seconds", "extraction_seconds"):
            assert isinstance(page[key], float)

        # The usable-content gate refuses the JS shell; extraction never runs for it.
        assert shell["unusable"] == "js_shell"
        assert shell["entities"] == [] and shell["extraction_seconds"] is None
        assert generate.call_count == 1

    @respx.mock
    def test_without_flag_nothing_is_refused_and_degraded_reason_shown(self, capsys):
        respx.get("https://lalaue.example/acmb").mock(
            return_value=httpx.Response(200, text=LALAUE, headers={"content-type": "text/html"})
        )
        respx.post(f"{OLLAMA}/api/generate").mock(
            return_value=httpx.Response(200, content=_stream("not json"))
        )
        respx.post(f"{OLLAMA}/api/chat").mock(return_value=httpx.Response(503))
        assert _load().main(["https://lalaue.example/acmb"]) == 0
        page = json.loads(capsys.readouterr().out.strip())
        assert page["refused_names"] == []
        assert page["extraction_error"] == "http_error: 503"

    def test_imports_no_anytype_or_qdrant_client(self):
        """No Anytype read client, Qdrant, indexer or ingest pipeline gets imported.

        ``anytype_llm_wiki.wiki/__init__`` re-exports ``wiki_bootstrap``, which loads
        the ``wiki_client`` module as a side effect of importing the package; the
        harness never constructs a client (the respx tests above prove no Anytype
        call is made).
        """
        code = (
            "import importlib.util, sys;"
            f"spec = importlib.util.spec_from_file_location('h', {str(SCRIPT)!r});"
            "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m);"
            "bad = [n for n in sys.modules if n.startswith('qdrant_client') or n in ("
            "'anytype_llm_wiki.anytype_client', 'anytype_llm_wiki.wiki.remember',"
            "'anytype_llm_wiki.wiki.ingest', 'anytype_llm_wiki.indexer')];"
            "print(','.join(bad))"
        )
        out = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT, check=True
        )
        assert out.stdout.strip() == "", out.stdout


class TestDryRunSubjectHint:
    """Aldeia-IT/aldeia-box#1430: --subject-hint reports primary_name and hint_warnings."""

    def _run(self, args, extracted, capsys):
        with respx.mock:
            respx.get("https://lalaue.example/acmb").mock(
                return_value=httpx.Response(
                    200, text=LALAUE, headers={"content-type": "text/html"}
                )
            )
            generate = respx.post(f"{OLLAMA}/api/generate").mock(
                return_value=httpx.Response(200, content=_stream(json.dumps(extracted)))
            )
            assert _load().main([*args, "https://lalaue.example/acmb"]) == 0
        return json.loads(capsys.readouterr().out.strip()), generate

    def test_marked_entity_is_renamed_and_the_hint_reaches_the_prompt(self, capsys):
        extracted = {
            "entities": [{"name": "Manoel dos Reis Machado", "description": "d"}],
            "concepts": [],
            "primary_subject": "Manoel dos Reis Machado",
        }
        page, generate = self._run(["--subject-hint", "Mestre Bimba"], extracted, capsys)
        assert page["primary_name"] == "Mestre Bimba"
        assert page["marked"] == "Manoel dos Reis Machado"
        assert page["hint_warnings"] == []
        assert [e["name"] for e in page["entities"]] == ["Mestre Bimba"]
        assert 'primary subject is "Mestre Bimba"' in json.loads(
            generate.calls[0].request.content
        )["prompt"]

    def test_unmatched_hint_is_reported(self, capsys):
        extracted = {"entities": [{"name": "Salvador", "description": "d"}], "concepts": []}
        page, _ = self._run(["--subject-hint", "Mestre Bimba"], extracted, capsys)
        assert page["primary_name"] is None
        assert page["marked"] is None
        assert page["hint_warnings"] == [
            'subject_hint_unmatched: no extracted entity is the primary subject "Mestre Bimba"'
        ]

    def test_strip_name_titles_mirrors_a_listed_space(self, capsys):
        extracted = {
            "entities": [{"name": "Mestre Bimba", "description": "d"}],
            "concepts": [],
        }
        page, _ = self._run(
            ["--subject-hint", "Mestre Bimba", "--strip-name-titles"], extracted, capsys
        )
        assert page["primary_name"] == "Bimba"

    def test_without_a_hint_the_report_has_null_primary_and_no_warnings(self, capsys):
        extracted = {"entities": [{"name": "Salvador", "description": "d"}], "concepts": []}
        page, generate = self._run([], extracted, capsys)
        assert page["primary_name"] is None and page["hint_warnings"] == []
        assert page["marked"] is None
        assert "PRIMARY SUBJECT" not in json.loads(generate.calls[0].request.content)["prompt"]


def test_a_hinted_run_with_title_strip_does_not_import_the_indexer():
    """The hint planning and the title strip need no indexer (and so no Qdrant)."""
    code = (
        "import importlib.util, sys;"
        f"spec = importlib.util.spec_from_file_location('h', {str(SCRIPT)!r});"
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m);"
        "m.fetch_source = lambda url: {'markdown': 'x' * 400, 'is_url': True, 'unusable': None,"
        " 'raw': None, 'content_type': 'text/html'};"
        "m._to_markdown = lambda *a, **k: 'x' * 400;"
        "m.extract = lambda **kw: {'entities': [{'name': 'Mestre Bimba', 'description': 'd'}],"
        " 'concepts': [], 'primary_subject': 'Mestre Bimba'};"
        "r = m.dry_run('https://e.x/p', False, 'Bimba', True);"
        "assert r['primary_name'] == 'Bimba', r;"
        "bad = [n for n in sys.modules if n.startswith('qdrant_client') or n in ("
        "'anytype_llm_wiki.indexer', 'anytype_llm_wiki.wiki.ingest',"
        "'anytype_llm_wiki.wiki.remember')];"
        "print(','.join(bad))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT, check=False
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "", out.stdout
