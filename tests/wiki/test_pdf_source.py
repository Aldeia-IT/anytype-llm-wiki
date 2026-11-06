"""PDF sources: read, gate, window and cite pages (Aldeia-IT/aldeia-box#1483 C1).

PDFs are generated with pypdf (``pdf_fixtures``): text pages carry a
Flate-compressed text layer, image pages have none. Anytype is the respx
``FakeWiki`` of the real-pages tests and extraction is a stub, so nothing here
reaches a live service.
"""

import httpx
import pytest
import respx

from .pdf_fixtures import make_pdf, text_is_compressed
from .test_ingest_real_pages import FakeWiki

PDF_URL = "https://lalaue.example/theses/capoeira.pdf"

BIMBA = (
    "Mestre Bimba founded the Centro de Cultura Fisica Regional in Salvador.\n"
    "His students learned the sequences of Capoeira Regional over many years,\n"
    "and the academy trained a generation of capoeiristas in Bahia."
)
PASTINHA = (
    "Mestre Pastinha opened the Centro Esportivo de Capoeira Angola in 1941.\n"
    "He wrote about the roda, the berimbau and the songs of the old masters,\n"
    "and his academy kept the Angola tradition alive in the Pelourinho."
)
SANTO_AMARO = (
    "Santo Amaro da Purificacao in the Reconcavo is the home of many capoeiristas.\n"
    "Besouro Manganga lived there, and the rodas of the town are remembered\n"
    "in the songs that every capoeira group in Bahia still sings today."
)


def _pages(n: int) -> list[str]:
    texts = [BIMBA, PASTINHA, SANTO_AMARO]
    return [f"{texts[i % 3]}\nPage marker line {i + 1}." for i in range(n)]


@pytest.fixture(autouse=True)
def _pdf_env(monkeypatch, tmp_path):
    monkeypatch.setenv("WIKI_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.delenv("WIKI_PDF_MAX_PAGES", raising=False)
    monkeypatch.delenv("WIKI_FETCH_MAX_PDF_BYTES", raising=False)


# ---------------------------------------------------------------------------
# read_pdf / fetch_source
# ---------------------------------------------------------------------------


class TestReadTextLayer:
    def test_flate_text_layer_read_with_page_numbers(self):
        from anytype_llm_wiki.wiki.pdf import read_pdf

        data = make_pdf([BIMBA, PASTINHA])
        assert text_is_compressed(data, "Mestre Bimba"), "fixture must use Flate streams"
        read = read_pdf(data, 40)
        assert [n for n, _ in read["pages"]] == [1, 2]
        assert "Mestre Bimba founded" in read["pages"][0][1]
        assert "Mestre Pastinha opened" in read["pages"][1][1]
        assert read["warnings"] == []

    def test_local_pdf_file_is_read_with_page_markers(self, tmp_path):
        from anytype_llm_wiki.wiki.fetch import fetch_source

        path = tmp_path / "thesis.pdf"
        path.write_bytes(make_pdf([BIMBA, PASTINHA]))
        fetched = fetch_source(str(path))
        assert fetched["unusable"] is None
        assert fetched["markdown"].startswith("[p. 1]\n\nMestre Bimba founded")
        assert "[p. 2]\n\nMestre Pastinha opened" in fetched["markdown"]
        assert [n for n, _ in fetched["pdf_pages"]] == [1, 2]

    def test_unreadable_pdf_is_a_data_error(self, tmp_path):
        from anytype_llm_wiki.wiki.fetch import fetch_source

        path = tmp_path / "broken.pdf"
        path.write_bytes(b"%PDF-1.7\nthis is not a pdf body at all\n%%EOF")
        fetched = fetch_source(str(path))
        assert fetched["markdown"].startswith("[DATA ERROR] pdf_unreadable"), fetched


class TestImageOnlyRefused:
    def test_image_only_pdf_is_refused(self, tmp_path):
        from anytype_llm_wiki.wiki.fetch import fetch_source

        path = tmp_path / "scan.pdf"
        path.write_bytes(make_pdf([None, None]))
        fetched = fetch_source(str(path))
        assert fetched["unusable"] == "image_only_pdf (no text layer; OCR is not supported)"

    def test_mixed_pdf_names_pages_without_text(self):
        from anytype_llm_wiki.wiki.pdf import read_pdf

        read = read_pdf(make_pdf([BIMBA, None, PASTINHA]), 40)
        assert [n for n, _ in read["pages"]] == [1, 3]
        assert read["warnings"] == [
            "pdf_pages_without_text: 1 of 3 pages have no text layer (p. 2); no OCR"
        ]

    def test_short_text_pdf_gets_the_html_gate(self, tmp_path):
        from anytype_llm_wiki.wiki.fetch import fetch_source

        path = tmp_path / "short.pdf"
        path.write_bytes(make_pdf(["Capoeira notes, page one of a short leaflet."]))
        fetched = fetch_source(str(path))
        assert fetched["unusable"].startswith("too_little_text"), fetched["unusable"]

    def test_garbled_share_counts_unmapped_glyphs(self):
        from anytype_llm_wiki.wiki.pdf import _garbled_share

        assert _garbled_share("Capoeira Regional") == 0.0
        assert _garbled_share("ab") == 0.5


class TestPageCap:
    def test_pages_past_the_cap_are_not_read_and_named(self, monkeypatch, tmp_path):
        from anytype_llm_wiki.wiki.fetch import fetch_source

        monkeypatch.setenv("WIKI_PDF_MAX_PAGES", "2")
        path = tmp_path / "long.pdf"
        path.write_bytes(make_pdf(_pages(5)))
        fetched = fetch_source(str(path))
        assert [n for n, _ in fetched["pdf_pages"]] == [1, 2]
        assert fetched["warnings"] == [
            "pdf_pages_capped: read 2 of 5 pages (WIKI_PDF_MAX_PAGES)"
        ]
        assert "[p. 3]" not in fetched["markdown"]

    def test_default_cap_is_forty(self):
        from anytype_llm_wiki.wiki import config

        assert config.pdf_max_pages() == 40


class TestRemotePdf:
    @pytest.fixture(autouse=True)
    def _resolve_public(self, monkeypatch):
        import socket

        from anytype_llm_wiki.wiki import fetch as fetch_mod

        monkeypatch.setattr(
            fetch_mod.socket,
            "getaddrinfo",
            lambda host, *a, **k: [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))
            ],
        )

    @respx.mock
    @pytest.mark.parametrize("content_type", ["application/pdf", "application/octet-stream"])
    def test_remote_pdf_is_read(self, content_type):
        from anytype_llm_wiki.wiki.fetch import fetch_source

        respx.get(PDF_URL).mock(
            return_value=httpx.Response(
                200, content=make_pdf([BIMBA, PASTINHA]), headers={"content-type": content_type}
            )
        )
        fetched = fetch_source(PDF_URL)
        assert fetched["unusable"] is None, fetched
        assert fetched["content_type"] == "application/pdf"
        assert fetched["raw"] is None
        assert fetched["markdown"].startswith("[p. 1]\n\nMestre Bimba founded")

    def test_html_quoting_the_magic_stays_a_page(self):
        from anytype_llm_wiki.wiki.pdf import is_pdf

        page = b"<html><body><p>The file starts with %PDF-1.7 bytes.</p></body></html>"
        assert not is_pdf(page, "text/html; charset=utf-8")
        assert is_pdf(b"%PDF-1.7\n...", "text/plain")
        assert is_pdf(b"junk\n%PDF-1.7\n...", "application/octet-stream")
        assert not is_pdf(b"plain text", None)

    @respx.mock
    def test_pdf_over_its_cap_is_refused_not_cut(self, monkeypatch):
        from anytype_llm_wiki.wiki.fetch import fetch_source

        data = make_pdf(_pages(3))
        monkeypatch.setenv("WIKI_FETCH_MAX_PDF_BYTES", str(len(data) - 1))
        respx.get(PDF_URL).mock(
            return_value=httpx.Response(
                200, content=data, headers={"content-type": "application/pdf"}
            )
        )
        fetched = fetch_source(PDF_URL)
        assert fetched["markdown"].startswith("[DATA ERROR] pdf_too_large"), fetched

    @respx.mock
    def test_pdf_cap_is_separate_from_the_page_cap(self, monkeypatch):
        """A PDF over WIKI_FETCH_MAX_BYTES but under the PDF cap is still read whole."""
        from anytype_llm_wiki.wiki.fetch import fetch_source

        data = make_pdf(_pages(3))
        monkeypatch.setenv("WIKI_FETCH_MAX_BYTES", "100")
        respx.get(PDF_URL).mock(
            return_value=httpx.Response(
                200, content=data, headers={"content-type": "application/pdf"}
            )
        )
        fetched = fetch_source(PDF_URL)
        assert [n for n, _ in fetched["pdf_pages"]] == [1, 2, 3]


# ---------------------------------------------------------------------------
# windows and page provenance
# ---------------------------------------------------------------------------


class TestWindows:
    def test_page_label(self):
        from anytype_llm_wiki.wiki.pdf import page_label

        assert page_label([3]) == "p. 3"
        assert page_label([5, 3, 4]) == "pp. 3–5"
        assert page_label([3, 5, 6]) == "pp. 3, 5–6"
        assert page_label([]) == ""

    def test_windows_fill_the_budget_in_order(self):
        from anytype_llm_wiki.wiki.pdf import page_windows

        pages = [(1, "a" * 40), (2, "b" * 40), (3, "c" * 40), (4, "d" * 200)]
        windows = page_windows(pages, 90)
        assert [[n for n, _ in w] for w in windows] == [[1, 2], [3], [4]]

    def test_extract_runs_once_per_window_with_page_provenance(self):
        from anytype_llm_wiki.wiki.pdf import extract_pages

        pages = [(1, BIMBA), (2, PASTINHA), (3, SANTO_AMARO)]
        seen = []

        def fake_extract(markdown, space_id, **kw):
            seen.append(markdown)
            if "Bimba" in markdown:
                return {"entities": [{"name": "Mestre Bimba", "description": "Founded an academy."}],
                        "concepts": [{"name": "Capoeira Regional", "definition": "A style."}]}
            return {"entities": [{"name": "Mestre Pastinha", "description": "Opened CECA."},
                                 {"name": "Bahia", "description": "A state."}],
                    "concepts": []}

        out = extract_pages(
            pages, space_id="s", extract_fn=fake_extract, budget_chars=len(BIMBA) + 5
        )
        assert out["windows"] == 3 and len(seen) == 3
        facts = {e["name"]: e["description"] for e in out["entities"]}
        assert facts["Mestre Bimba"] == "Founded an academy. [p. 1]"
        # Found in windows 2 and 3: one entry, each fact with its own page.
        assert facts["Mestre Pastinha"] == "Opened CECA. [p. 2]\nOpened CECA. [p. 3]"
        # Bahia is named on pages 1 and 3; window 2 (page 2) does not name it,
        # so window 2's fact falls back to the window's page, window 3's to p. 3.
        assert facts["Bahia"] == "A state. [p. 2]\nA state. [p. 3]"
        assert out["concepts"] == [{"name": "Capoeira Regional", "definition": "A style. [p. 1]"}]
        assert "error" not in out and out["warnings"] == []

    def test_fact_names_the_pages_of_its_window_that_mention_it(self):
        from anytype_llm_wiki.wiki.pdf import extract_pages

        pages = [(4, BIMBA), (5, PASTINHA), (6, SANTO_AMARO)]

        def fake_extract(markdown, space_id, **kw):
            return {"entities": [{"name": "Besouro Manganga", "description": "Lived there."},
                                 {"name": "Unnamed Teacher", "description": "Taught."}],
                    "concepts": []}

        out = extract_pages(pages, space_id="s", extract_fn=fake_extract, budget_chars=10_000)
        facts = {e["name"]: e["description"] for e in out["entities"]}
        assert facts["Besouro Manganga"] == "Lived there. [p. 6]"
        assert facts["Unnamed Teacher"] == "Taught. [pp. 4–6]"

    def test_partial_degradation_is_named(self):
        from anytype_llm_wiki.wiki.pdf import extract_pages

        def fake_extract(markdown, space_id, **kw):
            if "Pastinha" in markdown:
                return {"entities": [], "concepts": [], "error": "extraction_degraded: timeout"}
            return {"entities": [{"name": "Mestre Bimba", "description": "x"}], "concepts": [],
                    "truncated": {"kept_chars": 10, "total_chars": 20}}

        out = extract_pages(
            [(1, BIMBA), (2, PASTINHA)], space_id="s", extract_fn=fake_extract,
            budget_chars=len(BIMBA) + 5,
        )
        assert "error" not in out
        assert out["warnings"] == [
            "extraction_input_truncated: p. 1 10/20 chars",
            "extraction_partial: p. 2 degraded (timeout)",
        ]

    def test_all_windows_degraded_is_an_extraction_error(self):
        from anytype_llm_wiki.wiki.pdf import extract_pages

        def fake_extract(markdown, space_id, **kw):
            return {"entities": [], "concepts": [], "error": "extraction_degraded: malformed_json"}

        out = extract_pages(
            [(1, BIMBA), (2, PASTINHA)], space_id="s", extract_fn=fake_extract,
            budget_chars=len(BIMBA) + 5,
        )
        assert out["error"] == "extraction_degraded: malformed_json"

    def test_config_error_stops_at_once(self):
        from anytype_llm_wiki.wiki.pdf import extract_pages

        calls = []

        def fake_extract(markdown, space_id, **kw):
            calls.append(1)
            return {"entities": [], "concepts": [], "error": "[CONFIG ERROR] ollama_model_not_pulled"}

        out = extract_pages(
            [(1, BIMBA), (2, PASTINHA)], space_id="s", extract_fn=fake_extract,
            budget_chars=len(BIMBA) + 5,
        )
        assert out["error"].startswith("[CONFIG ERROR] ollama_model_not_pulled")
        assert calls == [1]

    def test_window_budget_matches_fit_source(self, monkeypatch):
        """A window of exactly the budget is not cut by extract()'s _fit_source."""
        from anytype_llm_wiki.wiki import extraction

        monkeypatch.setenv("WIKI_EXTRACT_MAX_INPUT_TOKENS", "4000")
        budget = extraction.source_budget_chars()
        assert budget > 0
        text = "x" * budget
        kept, truncated = extraction._fit_source(text, extraction._load_prompt())
        assert truncated is None and kept == text
        _kept, truncated = extraction._fit_source(text + "y", extraction._load_prompt())
        assert truncated is not None


# ---------------------------------------------------------------------------
# wiki_ingest end to end (fake Anytype, stubbed extract)
# ---------------------------------------------------------------------------


class _PdfWiki(FakeWiki):
    def __init__(self, pdf: bytes):
        super().__init__()
        self.pdf = pdf

    def _page(self, request):
        return httpx.Response(200, content=self.pdf, headers={"content-type": "application/pdf"})


@pytest.fixture
def _ingest_env(monkeypatch):
    import socket

    from anytype_llm_wiki.wiki import fetch as fetch_mod

    monkeypatch.setenv("ANYTYPE_API_KEY", "test-key")
    monkeypatch.setenv("ANYTYPE_API_URL", "http://127.0.0.1:31012")
    monkeypatch.setenv("ANYTYPE_API_VERSION", "2025-11-08")
    monkeypatch.setenv("WIKI_AUTO_REINDEX", "false")
    monkeypatch.delenv("WIKI_EXTRACT_ENDPOINT", raising=False)
    monkeypatch.setattr(
        fetch_mod.socket,
        "getaddrinfo",
        lambda host, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )


def _facts_of(fake, name):
    for payload in fake.created:
        if payload.get("name") == name:
            for prop in payload.get("properties", []):
                if prop["key"] in ("wiki_facts", "wiki_definition"):
                    return prop["text"]
    return None


@pytest.mark.usefixtures("_ingest_env")
class TestIngestPdf:
    @respx.mock
    def test_pdf_ingest_extracts_in_windows_and_cites_pages(self, monkeypatch):
        import anytype_llm_wiki.wiki.ingest as _ingest

        monkeypatch.setenv("WIKI_PDF_MAX_PAGES", "3")
        fake = _PdfWiki(make_pdf(_pages(4)))
        fake.install()
        calls = []

        def fake_extract(markdown, space_id, **kw):
            calls.append(markdown)
            name = "Mestre Bimba" if "Bimba" in markdown else "Mestre Pastinha"
            return {"entities": [{"name": name, "description": f"Named in window {len(calls)}."}],
                    "concepts": []}

        monkeypatch.setattr(_ingest, "extract", fake_extract)
        from anytype_llm_wiki.wiki import pdf as _pdf

        monkeypatch.setattr(_pdf, "source_budget_chars", lambda hint=None: 260)
        result = _ingest.wiki_ingest(source=PDF_URL, space_id="space-pdf-001")

        assert result["status"] == "ok", result
        assert len(calls) == 3, "one extract() per page window (pages 1, 2, 3)"
        assert "pdf_pages_capped: read 3 of 4 pages (WIKI_PDF_MAX_PAGES)" in result["warnings"]
        assert _facts_of(fake, "Mestre Bimba") == "Named in window 1. [p. 1]"
        assert _facts_of(fake, "Mestre Pastinha") == (
            "Named in window 2. [p. 2]\nNamed in window 3. [p. 3]"
        )
        (source,) = fake.created_of("wiki_source")
        excerpt = next(p["text"] for p in source["properties"] if p["key"] == "wiki_excerpt")
        assert excerpt.startswith("[p. 1]")

    @respx.mock
    def test_image_only_pdf_ingest_writes_nothing(self, monkeypatch):
        import anytype_llm_wiki.wiki.ingest as _ingest

        fake = _PdfWiki(make_pdf([None]))
        fake.install()

        def must_not_run(**kw):
            raise AssertionError("extract must not run")

        monkeypatch.setattr(_ingest, "extract", must_not_run)
        result = _ingest.wiki_ingest(source=PDF_URL, space_id="space-pdf-001")
        assert result["status"] == "error"
        assert result["error"] == (
            "[DATA ERROR] no_usable_content: image_only_pdf (no text layer; OCR is not supported)"
        )
        assert fake.created == []
