"""wiki_ingest on real-shaped web pages (Aldeia-IT/aldeia-box#1427).

AC2 (excerpt is the article), AC4 (truncation warning), AC5 (degraded reason in
the result and the log), AC6 (re-ingest after a fix reuses the Source), AC9
(usable-content gate for URL ingest) and AC11 (no heading objects from a
degraded URL ingest). Anytype is a respx fake; extraction is stubbed.
"""

import logging
import socket

import httpx
import pytest
import respx

from .fakes import ANYTYPE_BASE, SPACE, FakeWiki

OLLAMA_BASE = "http://127.0.0.1:11434"
PAGE_URL = "https://lalaue.example/capoeira-schools/acmb/"


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

    def test_n1_url_match_stops_at_closing_delimiters(self):
        from anytype_llm_wiki.wiki.util import scrub_text_urls

        text = (
            "[x](https://u:pw@ex.org/a?t=1) and <https://ex.org/b?k=2> and "
            "\"https://ex.org/c?s=3\" and 'https://ex.org/d?s=4' and [https://ex.org/e?s=5]"
        )
        out = scrub_text_urls(text)
        assert out == (
            "[x](https://ex.org/a) and <https://ex.org/b> and "
            "\"https://ex.org/c\" and 'https://ex.org/d' and [https://ex.org/e]"
        ), out


class TestRememberSourceScrub:
    """R5: the agent Source's name and excerpt keep the note's text, lose the credential."""

    def test_note_keeps_text_and_loses_credential(self):
        from anytype_llm_wiki.wiki.remember import _create_remember_source

        calls = []

        class _Client:
            def create_object(self, space_id, type_key, name, properties):
                calls.append({"name": name, "properties": properties})
                return {"id": "src-1"}

        note = (
            "Why did the #1426 rename happen? See "
            "https://jan:pa55word@wiki.example/page?api_key=xyz for the thread."
        )
        assert _create_remember_source(_Client(), SPACE, note, {"warnings": []}, None) == "src-1"
        (call,) = calls
        excerpt = next(p["text"] for p in call["properties"] if p["key"] == "wiki_excerpt")
        for value in (call["name"], excerpt):
            assert value.startswith("Why did the #1426 rename happen? See "), value
            assert "https://wiki.example/page" in value
            assert "pa55word" not in value and "jan:" not in value and "xyz" not in value
        assert excerpt.endswith(" for the thread.")


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


NAMES = {
    "founding_date_conflict",
    "associacao-de-capoeira-mestre-bimba",
    "pt.wikipedia.org/wiki/Mestra_Janja",
    "Mestre Bimba",
    "bge-m3",
}
IDENTIFIER_LIKE = {
    "founding_date_conflict",
    "associacao-de-capoeira-mestre-bimba",
    "pt.wikipedia.org/wiki/Mestra_Janja",
}


def _five_names():
    return {"entities": [{"name": n, "description": "facts"} for n in sorted(NAMES)], "concepts": []}


class TestIdentifierNameGate:
    """AC10 (listed space refuses identifier-like names) and AC12 (unlisted keeps them)."""

    @respx.mock
    def test_listed_space_refuses_identifier_like_names(self, monkeypatch):
        monkeypatch.setenv("WIKI_REFUSE_IDENTIFIER_NAMES_SPACES", f"other-space, {SPACE}")
        fake = FakeWiki()
        fake.install()
        _stub_extract(monkeypatch, _five_names())
        result = _ingest()
        created = {p["name"] for p in fake.wiki_objects()}
        assert created == {"Mestre Bimba", "bge-m3"}, created
        warnings = [w for w in result["warnings"] if "identifier_like" in w]
        assert sorted(warnings) == sorted(
            f"name_policy_rejected: identifier_like: {n}" for n in IDENTIFIER_LIKE
        ), warnings

    @pytest.mark.parametrize("listed", [None, "", "other-space"])
    @respx.mock
    def test_unlisted_space_keeps_todays_naming(self, monkeypatch, listed):
        if listed is None:
            monkeypatch.delenv("WIKI_REFUSE_IDENTIFIER_NAMES_SPACES", raising=False)
        else:
            monkeypatch.setenv("WIKI_REFUSE_IDENTIFIER_NAMES_SPACES", listed)
        fake = FakeWiki()
        fake.install()
        _stub_extract(monkeypatch, _five_names())
        result = _ingest()
        created = {p["name"] for p in fake.wiki_objects()}
        assert created == NAMES, created
        assert not [w for w in result["warnings"] if "identifier_like" in w]

    @respx.mock
    def test_url_named_fallback_is_refused_and_source_kept(self, monkeypatch):
        monkeypatch.setenv("WIKI_REFUSE_IDENTIFIER_NAMES_SPACES", SPACE)
        headingless = (
            "<html><body><article><p>"
            + "Capoeira Regional was created in Salvador by Mestre Bimba in the 1930s. " * 8
            + "</p></article></body></html>"
        )
        fake = FakeWiki(page_body=headingless)
        fake.install()
        _stub_extract(monkeypatch, {"entities": [], "concepts": []})
        result = _ingest()
        assert fake.wiki_objects() == [], [p["name"] for p in fake.wiki_objects()]
        (source,) = fake.created_of("wiki_source")
        assert source["name"] == PAGE_URL, "the Source's own name is never gated"
        assert f"name_policy_rejected: identifier_like: {PAGE_URL}" in result["warnings"]


# Aldeia-IT/aldeia-box#1508 AC3: a profile page with a licence footer, site chrome
# (navigation, a byline) and a run of padding spaces, shaped on the 2026-11-07 drain
# pages (grupoliberdadecapoeira linhagem-mestres, velhosmestres); text rewritten.
_PAD = " " * 300
_CHROME_BODY = (
    "Mestre Indio fundou o grupo Oxossi em 1969 e ensinou capoeira de rua em Salvador, "
    "onde formou muitos alunos ao longo de varias decadas de trabalho dedicado."
)
CHROME_PAGE = f"""<html><head><title>Linhagem Mestres</title></head><body>
<div id="nav"><a href="/">Inicio</a> <a href="/mestres">Mestres</a> <a href="/contato">Contato</a></div>
<div id="page"><div id="content"><h1>Linhagem Mestres</h1>
<h4>1. Mestre Indio</h4>
<p>Grupo: Oxossi<br>Pais: Brasil<br>Cidade: Salvador, Bahia<br>Data de Nascimento: 1955{_PAD}Origem: Mestre Pele da Bomba</p>
<p>{_CHROME_BODY}</p>
<p>{_CHROME_BODY} Mais um paragrafo de texto corrido para que a pagina tenha corpo suficiente.</p>
</div></div>
<div class="site-info"><p>outubro, 2016</p><p>Copyright</p>
<p>Content is available under Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0) unless otherwise noted.</p></div>
</body></html>"""

# Names granite4.1:8b extracted from such text on the drain pages, plus real entities.
_FURNITURE = [
    "1970",
    "2016",
    "26 August 1997",
    "outubro, 2016",
    "Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)",
    "Velhosmestres.com",
]
_REAL = ["Mestre Indio", "Grupo Oxossi", "Mestre Pele da Bomba"]


def _model_output(names: list[str], relations: list[dict] | None = None) -> dict:
    return {
        "entities": [{"name": n, "description": f"{n} facts"} for n in names],
        "concepts": [],
        "relations": relations or [],
    }


def _entity_names(fake: FakeWiki) -> set[str]:
    return {
        p["name"]
        for p in fake.wiki_objects()
        if p.get("type_key") in ("wiki_entity", "wiki_concept")
    }


class TestPageChromeRegression:
    """Aldeia-IT/aldeia-box#1508 AC3: page chrome must not reach the extractor, and the
    furniture names a model still makes from a page never become objects.

    The fetch side runs the real fetch on the fixture page. The extraction side cannot
    call granite in a test, so the model is stubbed: it records the text it was given
    and answers with the junk names the drain wrote, next to real ones.
    """

    def test_fetched_text_keeps_the_body_and_drops_footer_byline_and_padding(self):
        from anytype_llm_wiki.wiki.fetch import extract_main_markdown

        text = extract_main_markdown(CHROME_PAGE)
        assert "fundou o grupo Oxossi em 1969" in text, text  # #1432 recovery intact
        assert "Origem: Mestre Pele da Bomba" in text, text
        assert "Creative Commons" not in text, text
        assert "Copyright" not in text, text
        assert "outubro, 2016" not in text, text
        assert " " * 3 not in text, repr(text)

    @respx.mock
    def test_ingest_sends_clean_text_and_writes_only_real_entities(self, monkeypatch):
        import anytype_llm_wiki.wiki.ingest as _ingest_mod

        fake = FakeWiki(page_body=CHROME_PAGE)
        fake.install()
        seen: list[str] = []

        def fake_extract(**kw):
            seen.append(kw["markdown"])
            return _model_output(
                _REAL + _FURNITURE,
                [
                    {"from": "Mestre Indio", "to": "Grupo Oxossi", "label": "founded"},
                    {"from": "Mestre Indio", "to": "1970", "label": "active in"},
                ],
            )

        monkeypatch.setattr(_ingest_mod, "extract", fake_extract)
        result = _ingest()
        assert result["status"] == "ok", result
        (markdown,) = seen
        assert "Creative Commons" not in markdown and " " * 3 not in markdown
        assert _entity_names(fake) == set(_REAL), _entity_names(fake)
        assert sorted(w for w in result["warnings"] if "page_furniture" in w) == sorted(
            f"name_policy_rejected: page_furniture: {n}" for n in _FURNITURE
        ), result["warnings"]
        assert len(fake.created_of("wiki_link")) == 1, fake.created_of("wiki_link")


class TestPageFurnitureGuardInIngest:
    """Aldeia-IT/aldeia-box#1508: ingest drops a non-primary candidate whose name is page
    furniture (``is_page_furniture_name``), in every space, with the warning
    ``name_policy_rejected: page_furniture: <name>``. The hinted primary subject is
    exempt: the caller named it.

    Known limitation: a real entity named only by a year or a date (a group or an
    event literally called "1968") is dropped unless it is the hinted primary subject.
    """

    @respx.mock
    def test_furniture_candidates_dropped_in_an_unlisted_space(self, monkeypatch):
        monkeypatch.delenv("WIKI_REFUSE_IDENTIFIER_NAMES_SPACES", raising=False)
        fake = FakeWiki()
        fake.install()
        _stub_extract(monkeypatch, _model_output(["Mestre Bimba", *_FURNITURE]))
        result = _ingest()
        assert _entity_names(fake) == {"Mestre Bimba"}, _entity_names(fake)
        assert sum("page_furniture" in w for w in result["warnings"]) == len(_FURNITURE)

    @respx.mock
    def test_furniture_concepts_dropped_too(self, monkeypatch):
        fake = FakeWiki()
        fake.install()
        _stub_extract(
            monkeypatch,
            {
                "entities": [{"name": "Mestre Bimba", "description": "d"}],
                "concepts": [
                    {"name": "Capoeira Regional", "definition": "c"},
                    {"name": "CC BY-SA 4.0", "definition": "licence"},
                ],
            },
        )
        result = _ingest()
        assert _entity_names(fake) == {"Mestre Bimba", "Capoeira Regional"}
        assert "name_policy_rejected: page_furniture: CC BY-SA 4.0" in result["warnings"]

    @respx.mock
    def test_a_real_entity_named_only_by_a_year_is_dropped(self, monkeypatch):
        """Documented limitation: the guard cannot tell the group "1968" from a year."""
        fake = FakeWiki()
        fake.install()
        _stub_extract(monkeypatch, _model_output(["Mestre Bimba", "1968"]))
        result = _ingest()
        assert _entity_names(fake) == {"Mestre Bimba"}
        assert "name_policy_rejected: page_furniture: 1968" in result["warnings"]

    @respx.mock
    def test_the_hinted_primary_subject_is_exempt(self, monkeypatch):
        from anytype_llm_wiki.wiki.ingest import wiki_ingest

        fake = FakeWiki()
        fake.install()
        out = _model_output(["1968", "Mestre Bimba", "2016"])
        out["primary_subject"] = "1968"
        _stub_extract(monkeypatch, out)
        result = wiki_ingest(source=PAGE_URL, space_id=SPACE, subject_hint="1968")
        assert _entity_names(fake) == {"1968", "Mestre Bimba"}, _entity_names(fake)
        assert [w for w in result["warnings"] if "page_furniture" in w] == [
            "name_policy_rejected: page_furniture: 2016"
        ]
