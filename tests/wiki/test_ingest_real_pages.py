"""wiki_ingest on real-shaped web pages (Aldeia-IT/aldeia-box#1427).

AC2 (excerpt is the article), AC4 (truncation warning), AC5 (degraded reason in
the result and the log), AC6 (re-ingest after a fix reuses the Source), AC9
(usable-content gate for URL ingest) and AC11 (no heading objects from a
degraded URL ingest). Anytype is a respx fake; extraction is stubbed.
"""

import json
import logging
import socket
from pathlib import Path

import httpx
import pytest
import respx

ANYTYPE_BASE = "http://127.0.0.1:31012"
OLLAMA_BASE = "http://127.0.0.1:11434"
SPACE = "space-real-pages-001"
PAGE_URL = "https://lalaue.example/capoeira-schools/acmb/"
LALAUE = (Path(__file__).parent / "fixtures" / "pages" / "lalaue_shaped.html").read_text(
    encoding="utf-8"
)


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("ANYTYPE_API_KEY", "test-key")
    monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
    monkeypatch.setenv("ANYTYPE_API_VERSION", "2025-11-08")
    monkeypatch.setenv("WIKI_AUTO_REINDEX", "false")
    monkeypatch.setenv("WIKI_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.delenv("WIKI_EXTRACT_ENDPOINT", raising=False)
    from anytype_llm_wiki.wiki import fetch as fetch_mod

    monkeypatch.setattr(
        fetch_mod.socket,
        "getaddrinfo",
        lambda host, *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))
        ],
    )


def _schema_ok():
    from anytype_llm_wiki.wiki.types_schema import WIKI_SCHEMA_VERSION

    return {
        "data": [
            {
                "id": "coll-wiki-001",
                "name": "Wiki",
                "type": {"key": "collection"},
                "properties": [{"key": "wiki_schema_version", "text": WIKI_SCHEMA_VERSION}],
            }
        ],
        "pagination": {"has_more": False},
    }


class FakeWiki:
    """In-memory Anytype: search by normalized name, create/patch objects, log writes."""

    def __init__(self, page_body: str | None = LALAUE, page_status: int = 200):
        self.store: dict = {}
        self.created: list[dict] = []
        self.patched: list[dict] = []
        self.page_body = page_body
        self.page_status = page_status
        self.n = 0

    def install(self):
        respx.get(url__startswith=ANYTYPE_BASE).mock(
            side_effect=lambda request: httpx.Response(200, json=_schema_ok())
        )
        respx.get(url__startswith="https://lalaue.example/").mock(side_effect=self._page)
        respx.post(url__startswith=ANYTYPE_BASE).mock(side_effect=self._post)
        respx.patch(url__startswith=ANYTYPE_BASE).mock(side_effect=self._patch)

    def _page(self, request):
        return httpx.Response(
            self.page_status,
            text=self.page_body or "",
            headers={"content-type": "text/html; charset=utf-8"},
        )

    def _post(self, request):
        from anytype_llm_wiki.wiki.util import normalize_title

        url = str(request.url)
        payload = json.loads(request.content or b"{}")
        if "/search" in url:
            q = normalize_title(payload.get("query", ""))
            data = [
                {"id": o["id"], "name": o["name"], "type": {"key": tk}, "properties": []}
                for (n, tk), o in self.store.items()
                if n == q
            ]
            return httpx.Response(200, json={"data": data, "pagination": {"has_more": False}})
        if "/objects" in url:
            self.n += 1
            oid = f"obj-{self.n}"
            name = payload.get("name", "")
            tk = payload.get("type_key", "")
            self.store[(normalize_title(name), tk)] = {"id": oid, "name": name}
            self.created.append(payload)
            return httpx.Response(201, json={"object": {"id": oid, "name": name}})
        return httpx.Response(200, json={})

    def _patch(self, request):
        self.patched.append(json.loads(request.content or b"{}"))
        return httpx.Response(200, json={"object": {"id": "patched"}})

    def created_of(self, type_key: str) -> list[dict]:
        return [p for p in self.created if p.get("type_key") == type_key]

    def wiki_objects(self) -> list[dict]:
        return [
            p for p in self.created if p.get("type_key") not in ("wiki_source", "wiki_log")
        ]


def _stub_extract(monkeypatch, result: dict | Exception):
    import anytype_llm_wiki.wiki.ingest as _ingest

    def fake_extract(**kw):
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(_ingest, "extract", fake_extract)


def _ingest(source=PAGE_URL):
    from anytype_llm_wiki.wiki.ingest import wiki_ingest

    return wiki_ingest(source=source, space_id=SPACE)


GOOD = {
    "entities": [{"name": "Mestre Bimba", "description": "Founder of Capoeira Regional."}],
    "concepts": [{"name": "Capoeira Regional", "description": "A capoeira style."}],
}


class TestExcerptIsTheArticle:
    """AC2: wiki_excerpt is built from the stripped markdown."""

    @respx.mock
    def test_excerpt_starts_with_the_page_title(self, monkeypatch):
        fake = FakeWiki()
        fake.install()
        _stub_extract(monkeypatch, GOOD)
        result = _ingest()
        assert result["status"] == "ok", result
        (source,) = fake.created_of("wiki_source")
        excerpt = next(p["text"] for p in source["properties"] if p["key"] == "wiki_excerpt")
        assert excerpt.startswith("# Associação De Capoeira Mestre Bimba"), excerpt[:120]
        assert "WHAT IS CAPOEIRA" not in excerpt


class TestExcerptScrub:
    """AC2/R1: credentials in embedded URLs go; headings and text after ``?`` stay."""

    def test_credential_url_scrubbed_but_prose_survives(self):
        from anytype_llm_wiki.wiki.util import scrub_text_urls

        text = (
            "# Title\n\nWho founded it? Mestre Bimba. See "
            "https://user:hunter2@example.com/page?token=abc123 for more."
        )
        out = scrub_text_urls(text)
        assert out.startswith("# Title\n\nWho founded it? Mestre Bimba. See ")
        assert "hunter2" not in out and "abc123" not in out and "user:" not in out
        assert "https://example.com/page" in out
        assert out.endswith(" for more.")


class TestTruncationWarning:
    """AC4: ingest surfaces extract()'s truncation as a warning."""

    @respx.mock
    def test_truncated_extraction_adds_warning(self, monkeypatch):
        fake = FakeWiki()
        fake.install()
        _stub_extract(monkeypatch, {**GOOD, "truncated": {"kept_chars": 120, "total_chars": 999}})
        result = _ingest()
        assert "extraction_input_truncated: 120/999 chars" in result["warnings"]
        assert "extraction_degraded" not in result["warnings"]


class TestDegradedReason:
    """AC5: the reason reaches result["extraction_error"] and one log line."""

    @pytest.mark.parametrize(
        "reason",
        [
            "timeout",
            "http_error: ConnectError",
            "http_error: 503",
            "malformed_json",
            "output_truncated",
            "stream_error: llama runner process has terminated",
        ],
    )
    @respx.mock
    def test_reason_reaches_result_and_log(self, monkeypatch, caplog, reason):
        fake = FakeWiki()
        fake.install()
        _stub_extract(
            monkeypatch,
            {"entities": [], "concepts": [], "error": f"extraction_degraded: {reason}"},
        )
        with caplog.at_level(logging.WARNING, logger="anytype_llm_wiki.wiki.ingest"):
            result = _ingest()
        assert result["extraction_error"] == reason
        assert "extraction_degraded" in result["warnings"], "the bare warning stays"
        records = [r for r in caplog.records if r.name == "anytype_llm_wiki.wiki.ingest"]
        degraded = [r for r in records if reason in r.getMessage()]
        assert len(degraded) == 1, [r.getMessage() for r in records]
        msg = degraded[0].getMessage()
        assert PAGE_URL in msg
        assert "s" in msg and any(ch.isdigit() for ch in msg), "elapsed seconds are logged"

    @respx.mock
    def test_unexpected_exception(self, monkeypatch, caplog):
        fake = FakeWiki()
        fake.install()
        _stub_extract(monkeypatch, RuntimeError("kaboom with details"))
        with caplog.at_level(logging.WARNING, logger="anytype_llm_wiki.wiki.ingest"):
            result = _ingest()
        assert result["extraction_error"] == "unexpected: RuntimeError"
        assert "extraction_degraded" in result["warnings"]
        assert any("unexpected: RuntimeError" in r.getMessage() for r in caplog.records)

    @respx.mock
    def test_clean_ingest_has_no_extraction_error(self, monkeypatch, caplog):
        fake = FakeWiki()
        fake.install()
        _stub_extract(monkeypatch, GOOD)
        with caplog.at_level(logging.WARNING, logger="anytype_llm_wiki.wiki.ingest"):
            result = _ingest()
        assert "extraction_error" not in result
        assert not [r for r in caplog.records if r.name == "anytype_llm_wiki.wiki.ingest"]


class TestNoHeadingObjectsFromDegradedUrl:
    """AC11: a degraded URL ingest creates the Source and a WikiLog only."""

    @pytest.mark.parametrize("reason", ["timeout", "malformed_json"])
    @respx.mock
    def test_degraded_url_creates_only_the_source(self, monkeypatch, reason):
        fake = FakeWiki()
        fake.install()
        _stub_extract(
            monkeypatch,
            {"entities": [], "concepts": [], "error": f"extraction_degraded: {reason}"},
        )
        result = _ingest()
        assert result["status"] == "ok", result
        assert len(fake.created_of("wiki_source")) == 1
        assert fake.wiki_objects() == [], [p["name"] for p in fake.wiki_objects()]
        assert result["objects_created"] == []
        assert result["relations_created"] == 0
        assert result["wiki_log_id"], "the WikiLog is still written"
        assert result["extraction_error"] == reason

    @respx.mock
    def test_unexpected_exception_on_url_creates_only_the_source(self, monkeypatch):
        fake = FakeWiki()
        fake.install()
        _stub_extract(monkeypatch, RuntimeError("boom"))
        result = _ingest()
        assert result["extraction_error"] == "unexpected: RuntimeError"
        assert len(fake.created_of("wiki_source")) == 1
        assert fake.wiki_objects() == []

    @respx.mock
    def test_real_timeout_through_ollama_creates_only_the_source(self, monkeypatch):
        """End to end: a streamed chunk-gap timeout on the Ollama wire."""

        class _Stall(httpx.SyncByteStream):
            def __iter__(self):
                raise httpx.ReadTimeout("stalled")
                yield b""  # pragma: no cover

        fake = FakeWiki()
        fake.install()
        respx.post(f"{OLLAMA_BASE}/api/generate").mock(
            return_value=httpx.Response(200, stream=_Stall())
        )
        result = _ingest()
        assert result["extraction_error"] == "timeout"
        assert fake.wiki_objects() == []
        assert len(fake.created_of("wiki_source")) == 1

    @pytest.mark.parametrize("reason", ["timeout", "malformed_json"])
    @respx.mock
    def test_local_markdown_file_keeps_heading_fallback(self, monkeypatch, tmp_path, reason):
        fake = FakeWiki()
        fake.install()
        _stub_extract(
            monkeypatch,
            {"entities": [], "concepts": [], "error": f"extraction_degraded: {reason}"},
        )
        md = tmp_path / "notes.md"
        md.write_text("# Roda Notes\n\nbody.\n\n## Instruments\n\nberimbau.\n", encoding="utf-8")
        result = _ingest(str(md))
        names = {p["name"] for p in fake.wiki_objects()}
        assert {"Roda Notes", "Instruments"} <= names, names
        assert result["extraction_error"] == reason


class TestReingestAfterFix:
    """AC6: a degraded ingest, then a good one, reuses the Source and fills it."""

    @respx.mock
    def test_reingest_reuses_source_and_creates_entities(self, monkeypatch):
        fake = FakeWiki()
        fake.install()
        _stub_extract(
            monkeypatch,
            {"entities": [], "concepts": [], "error": "extraction_degraded: timeout"},
        )
        first = _ingest()
        assert first["extraction_error"] == "timeout"

        _stub_extract(monkeypatch, GOOD)
        second = _ingest()

        assert len(fake.created_of("wiki_source")) == 1, "no duplicate Source"
        assert second["source_object_id"] == first["source_object_id"]
        created = {o["title"] for o in second["objects_created"]}
        assert created == {"Mestre Bimba", "Capoeira Regional"}, created
        assert "extraction_error" not in second


class TestUsableContentGate:
    """AC9: URL pages with no usable content are refused before any write."""

    def _assert_refused(self, result, fake, reason_prefix):
        assert result["status"] == "error", result
        assert result["error"].startswith(
            f"[DATA ERROR] no_usable_content: {reason_prefix}"
        ), result["error"]
        assert fake.created == [], "no create_object (no Source, no WikiLog)"
        assert fake.patched == [], "no update_object"
        assert result["source_object_id"] is None
        assert result["wiki_log_id"] is None

    @respx.mock
    def test_empty_200_body(self, monkeypatch):
        fake = FakeWiki(page_body="")
        fake.install()
        _stub_extract(monkeypatch, AssertionError("extract must not run"))
        self._assert_refused(_ingest(), fake, "empty")

    @respx.mock
    def test_js_shell(self, monkeypatch):
        fake = FakeWiki(page_body="<html><body><div id='__next'></div></body></html>")
        fake.install()
        _stub_extract(monkeypatch, AssertionError("extract must not run"))
        self._assert_refused(_ingest(), fake, "js_shell")

    @respx.mock
    def test_challenge_page(self, monkeypatch):
        fake = FakeWiki(
            page_body="<html><head><title>Just a moment...</title></head>"
            "<body><div id='cf-chl-widget-x'></div></body></html>"
        )
        fake.install()
        _stub_extract(monkeypatch, AssertionError("extract must not run"))
        self._assert_refused(_ingest(), fake, "challenge_page")

    @respx.mock
    def test_near_empty_page(self, monkeypatch):
        fake = FakeWiki(page_body="<html><body><h1>Soon</h1><p>Site coming soon.</p></body></html>")
        fake.install()
        _stub_extract(monkeypatch, AssertionError("extract must not run"))
        result = _ingest()
        self._assert_refused(result, fake, "too_little_text (")
        assert result["error"].endswith(" chars)")

    @respx.mock
    def test_403_still_fetch_failed(self, monkeypatch):
        fake = FakeWiki(page_status=403)
        fake.install()
        _stub_extract(monkeypatch, AssertionError("extract must not run"))
        result = _ingest()
        assert result["status"] == "error"
        assert result["error"].startswith("[DATA ERROR] fetch_failed")
        assert fake.created == [] and fake.patched == []

    @respx.mock
    def test_local_empty_file_still_empty_source(self, monkeypatch, tmp_path):
        fake = FakeWiki()
        fake.install()
        _stub_extract(monkeypatch, AssertionError("extract must not run"))
        empty = tmp_path / "empty.md"
        empty.write_text("", encoding="utf-8")
        result = _ingest(str(empty))
        assert result["status"] == "ok"
        assert "empty_source" in result["warnings"]
        assert len(fake.created_of("wiki_source")) == 1
