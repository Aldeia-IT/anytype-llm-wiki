"""Tests for trafilatura main-content extraction with strip_boilerplate recovery.

Aldeia-IT/aldeia-box#1432 D10: trafilatura (favor_recall, include_images, image
markdown removed) is the primary extractor; every strip_boilerplate line it lacks is
appended unless it is link-heavy (D11a: no length cut-off); strip_boilerplate's markdown is the
fallback when trafilatura returns nothing or the usable-content gate refuses the
merged text (D8); the metadata title is prepended as an H1 (D5). The Wikipedia
head must be clean (D6, Aldeia-IT/aldeia-box#1429).

The fixtures are shaped pages: the markup that made trafilatura lose body text on
the trial pages, with rewritten text (see the comment at the top of each file).
"""

import socket
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "pages"


def _page(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _visible(markdown: str) -> str:
    from anytype_llm_wiki.wiki.fetch import markdown_visible_text

    return markdown_visible_text(markdown)


def _baseline(html: str) -> str:
    """strip_boilerplate's markdown, the pre-#1432 output and today's fallback."""
    from anytype_llm_wiki.wiki.fetch import _html_to_markdown, strip_boilerplate

    return _html_to_markdown(strip_boilerplate(html))


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """trafilatura must work on the HTML string alone: any socket use fails the test."""

    def _refuse(*args, **kwargs):
        raise AssertionError(f"network access attempted: {args[:1]!r}")

    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)
    monkeypatch.setattr(socket, "getaddrinfo", _refuse)


TRIAL_PAGES = [
    pytest.param(
        "velhosmestres_caption_accordion_shaped.html",
        [
            "aprendi capoeira ainda menino na beira da praia",
            "Tive quatro mestres de exemplo",
            "O segredo dos valentes de antigamente",
            "o finado dono da roda tomava conta de tudo",
        ],
        id="01-velhosmestres-caption-accordion",
    ),
    pytest.param(
        "capoeirahistory_bare_div_shaped.html",
        [
            "I find this story, told by the old master himself, remarkable",
            "Elegance in dress and care with the berimbau",
            "The third widget returns to normal paragraphs",
        ],
        id="04-capoeirahistory-bare-div",
    ),
    pytest.param(
        "capoeirahub_outside_main_shaped.html",
        [
            "a short hero text inside the main landmark",
            "Family Tree Sheets",
            "Atlas of Rodas",
        ],
        id="19-capoeirahub-outside-main",
    ),
    pytest.param(
        "capoeirahub_card_links_shaped.html",
        ["Mestre Braga opened his first academy", "Mestre Bola Sete wrote books", "Mestre Alpha"],
        id="20-21-capoeirahub-card-links",
    ),
    pytest.param(
        "sinha_carousel_faq_shaped.html",
        [
            "As the mother of two lively children",
            "both feel safe there",
            "I have no background in dance or fighting sports",
            "who has trained for four decades",
        ],
        id="41-sinha-carousel-faq",
    ),
]


class TestTrialPagesKeepBody:
    """D9/D10: no body text that strip_boilerplate keeps is lost."""

    @pytest.mark.parametrize("fixture, phrases", TRIAL_PAGES)
    def test_body_phrases_survive(self, fixture, phrases):
        from anytype_llm_wiki.wiki.fetch import _to_markdown

        visible = _visible(_to_markdown(_page(fixture), "text/html"))
        for phrase in phrases:
            assert phrase in visible, f"{phrase!r} lost from {fixture}:\n{visible}"

    @pytest.mark.parametrize("fixture, phrases", TRIAL_PAGES)
    def test_trafilatura_text_leads(self, fixture, phrases):
        """The output opens with trafilatura's titled text; recovered lines follow."""
        from anytype_llm_wiki.wiki.fetch import (
            _prepend_title,
            _to_markdown,
            _trafilatura_extract,
        )

        html = _page(fixture)
        body, title = _trafilatura_extract(html)
        assert body, "trafilatura returned nothing on the fixture"
        assert _to_markdown(html, "text/html").startswith(_prepend_title(body, title))

    def test_title_is_the_only_h1_when_trafilatura_drops_the_heading(self):
        """Review r1 S2: the baseline's H1 equals the prepended title; not recovered twice."""
        from anytype_llm_wiki.wiki.fetch import _to_markdown

        md = _to_markdown(_page("sinha_carousel_faq_shaped.html"), "text/html")
        h1_lines = [line for line in md.splitlines() if line.startswith("# ")]
        assert len(h1_lines) == 1, h1_lines
        assert md.startswith(h1_lines[0])

    def test_card_link_paragraphs_are_not_duplicated(self):
        """Review r1 S3: a paragraph inside a multi-line link is already present."""
        from anytype_llm_wiki.wiki.fetch import _to_markdown

        md = _to_markdown(_page("capoeirahub_card_links_shaped.html"), "text/html")
        body_lines = [line for line in md.splitlines() if len(line.strip()) > 40]
        assert len(body_lines) == len(set(body_lines)), body_lines

    def test_date_inside_a_long_paragraph_survives(self):
        """Review r1 B1: trafilatura drops <time> text mid-paragraph; the line is recovered."""
        from anytype_llm_wiki.wiki.fetch import _to_markdown

        filler = (
            "This paragraph is long on purpose so that its beginning and its end are both "
            "kept by trafilatura while an inline element in the middle is removed by it. "
        )
        html = (
            "<html><head><title>T</title></head><body><article><h1>T</h1>"
            f"<p>{filler}Ele nasceu em <time>12 de maio de 1920 no Recôncavo</time> e depois "
            f"{filler}</p><p>{filler * 2}</p></article></body></html>"
        )
        assert "12 de maio de 1920" in _to_markdown(html, "text/html")

    def test_fetch_url_on_a_local_html_file_uses_the_same_path(self, tmp_path):
        from anytype_llm_wiki.wiki.fetch import _to_markdown, fetch_url

        html = _page("sinha_carousel_faq_shaped.html")
        page = tmp_path / "page.html"
        page.write_text(html, encoding="utf-8")
        assert fetch_url(str(page)) == _to_markdown(html, "text/html")


class TestWikipediaHead:
    """D6 / Aldeia-IT/aldeia-box#1429: the excerpt starts with the article."""

    def test_head_has_no_language_list_tagline_or_thumbnail(self):
        from anytype_llm_wiki.wiki.fetch import _to_markdown

        md = _to_markdown(_page("ptwiki_vector_shaped.html"), "text/html")
        head = md[:1000]
        assert "Origem: Wikipédia" not in head, head
        for language in ("English", "Español", "Français", "Deutsch", "4 línguas"):
            assert language not in head, f"{language!r} in head:\n{head}"
        assert "![" not in head, head
        assert "upload.wikimedia.org" not in head, head
        assert "Aparência" not in head, head

    def test_article_starts_with_its_title_and_keeps_the_body(self):
        from anytype_llm_wiki.wiki.fetch import _to_markdown

        md = _to_markdown(_page("ptwiki_vector_shaped.html"), "text/html")
        assert md.startswith("# Mestre Exemplo\n"), md[:200]
        assert md.count("# Mestre Exemplo") == 1
        visible = _visible(md)
        for phrase in (
            "Aprendeu capoeira no cais do porto",
            "as rodas de domingo",
            "na mesma praça onde ele começou a ensinar",
        ):
            assert phrase in visible

    def test_baseline_head_was_dirty(self):
        """Guard: the fixture reproduces #1429 under strip_boilerplate alone."""
        head = _baseline(_page("ptwiki_vector_shaped.html"))[:1000]
        assert "English" in head and "Origem: Wikipédia" in head


class TestFallback:
    """D8: strip_boilerplate's markdown when trafilatura gives nothing usable."""

    HTML = _page("capoeirahistory_bare_div_shaped.html")

    @pytest.mark.parametrize("returned", [None, "", "   \n  "])
    def test_trafilatura_returns_nothing(self, monkeypatch, returned):
        import trafilatura

        from anytype_llm_wiki.wiki.fetch import _to_markdown

        monkeypatch.setattr(trafilatura, "extract", lambda *a, **k: returned)
        assert _to_markdown(self.HTML, "text/html") == _baseline(self.HTML)

    def test_trafilatura_raises(self, monkeypatch):
        import trafilatura

        from anytype_llm_wiki.wiki.fetch import _to_markdown

        def _boom(*a, **k):
            raise ValueError("parser failure")

        monkeypatch.setattr(trafilatura, "extract", _boom)
        assert _to_markdown(self.HTML, "text/html") == _baseline(self.HTML)

    def test_gate_refuses_the_merged_text(self, monkeypatch):
        from anytype_llm_wiki.wiki import fetch

        baseline = _baseline(self.HTML)
        seen = []

        def _refuse_all_but_baseline(raw, markdown):
            seen.append(markdown)
            return None if markdown == baseline else "too_little_text (12 chars)"

        monkeypatch.setattr(fetch, "usable_content_verdict", _refuse_all_but_baseline)
        assert fetch._to_markdown(self.HTML, "text/html") == baseline
        assert seen, "the gate was never consulted on trafilatura's text"

    def test_gate_refuses_a_near_empty_trafilatura_text(self, monkeypatch):
        """Real gate: a few words from trafilatura and nothing to recover -> baseline."""
        import trafilatura

        from anytype_llm_wiki.wiki.fetch import _to_markdown

        html = (
            "<html><head><title>Short</title></head><body><main>"
            "<p>Only a short teaser.</p></main></body></html>"
        )
        monkeypatch.setattr(trafilatura, "extract", lambda *a, **k: "Teaser.")
        md = _to_markdown(html, "text/html")
        assert md == _baseline(html) == "Only a short teaser."


class TestTitle:
    """D5: `# {title}` from trafilatura's metadata, never duplicated."""

    BODY = (
        "The first paragraph of a shaped article body is long enough to pass the gate, "
        "because it talks at length about rodas, berimbaus and the old masters of Bahia.\n\n"
        "A second paragraph adds more of the same so the usable-content gate is satisfied "
        "and the title logic is the only thing under test in this class."
    )

    @staticmethod
    def _html(body_html: str) -> str:
        return f"<html><head><title>Ignored</title></head><body><article>{body_html}</article></body></html>"

    def _run(self, monkeypatch, extracted: str, title: str | None) -> str:
        import trafilatura

        from anytype_llm_wiki.wiki.fetch import _to_markdown

        monkeypatch.setattr(trafilatura, "extract", lambda *a, **k: extracted)
        monkeypatch.setattr(
            trafilatura,
            "extract_metadata",
            lambda *a, **k: type("Meta", (), {"title": title})(),
        )
        paragraphs = "".join(f"<p>{p}</p>" for p in self.BODY.split("\n\n"))
        return _to_markdown(self._html(paragraphs), "text/html")

    def test_title_prepended_when_body_has_no_h1(self, monkeypatch):
        md = self._run(monkeypatch, self.BODY, "Roda de Domingo")
        assert md.startswith("# Roda de Domingo\n\n" + self.BODY[:40]), md[:200]

    def test_title_not_duplicated_when_body_opens_with_it(self, monkeypatch):
        md = self._run(monkeypatch, "# Roda de Domingo\n\n" + self.BODY, "Roda de Domingo")
        assert md.startswith("# Roda de Domingo\n\n"), md[:200]
        assert md.count("Roda de Domingo") == 1, md

    def test_title_match_ignores_case_and_spacing(self, monkeypatch):
        md = self._run(monkeypatch, "#  roda de  domingo\n\n" + self.BODY, "Roda de Domingo")
        assert md.startswith("#  roda de  domingo\n\n"), md[:200]
        assert sum(line.startswith("#") for line in md.splitlines()) == 1, md

    @pytest.mark.parametrize("title", [None, "", "   "])
    def test_no_title_no_heading(self, monkeypatch, title):
        md = self._run(monkeypatch, self.BODY, title)
        assert md.startswith(self.BODY[:40]), md[:200]

    def test_metadata_failure_means_no_title(self, monkeypatch):
        import trafilatura

        from anytype_llm_wiki.wiki.fetch import _to_markdown

        def _boom(*a, **k):
            raise ValueError("bad metadata")

        monkeypatch.setattr(trafilatura, "extract", lambda *a, **k: self.BODY)
        monkeypatch.setattr(trafilatura, "extract_metadata", _boom)
        paragraphs = "".join(f"<p>{p}</p>" for p in self.BODY.split("\n\n"))
        md = _to_markdown(self._html(paragraphs), "text/html")
        assert md.startswith(self.BODY[:40]), md[:200]


class TestRecoverMissingLines:
    """D10: baseline lines trafilatura lacks are appended; chrome lines are not."""

    PRIMARY = (
        "# Article\n\n"
        "The primary extractor kept this opening paragraph about the history of the roda."
    )

    def test_missing_long_line_appended_at_the_end(self):
        from anytype_llm_wiki.wiki.fetch import _recover_missing_lines

        missing = "A paragraph that only the baseline kept, long enough to count as body text."
        baseline = self.PRIMARY + "\n\n" + missing
        merged = _recover_missing_lines(self.PRIMARY, baseline)
        assert merged.startswith(self.PRIMARY)
        assert merged.rstrip().endswith(missing)

    def test_lines_already_present_are_not_duplicated(self):
        from anytype_llm_wiki.wiki.fetch import _recover_missing_lines

        baseline = "# Article\n\nThe primary extractor kept this opening paragraph about the history of the roda."
        assert _recover_missing_lines(self.PRIMARY, baseline) == self.PRIMARY

    def test_presence_ignores_link_targets_and_inline_tags(self):
        """The same sentence rendered by both extractors (link title, <sup>) is present."""
        from anytype_llm_wiki.wiki.fetch import _recover_missing_lines

        primary = (
            "He learned in [Santo Amaro](<https://x.test/Santo_Amaro_(Bahia)>) as a boy."
            "<sup>[\\[2\\]](#cite_note-2)</sup> Later he taught in the city for many years."
        )
        baseline = (
            'He learned in [Santo Amaro](https://x.test/Santo_Amaro_(Bahia) "Santo Amaro (Bahia)")'
            " as a boy.[[2]](#cite_note-2) Later he taught in the city for many years."
        )
        assert _recover_missing_lines(primary, baseline) == primary

    def test_short_body_lines_are_recovered_and_link_lines_still_skipped(self):
        """D11a: no length floor; a caption or name line is body, a link list is not."""
        from anytype_llm_wiki.wiki.fetch import _recover_missing_lines

        date = "Salvador, 1974"  # a photo caption, 14 visible chars
        name = "Mestre Ana"
        nav = "[Home](/) [Masters](/masters)"
        merged = _recover_missing_lines(
            self.PRIMARY, f"{self.PRIMARY}\n\n{date}\n\n{nav}\n\n{name}"
        )
        assert merged.endswith(f"{date}\n\n{name}"), merged
        assert "[Home]" not in merged

    def test_link_heavy_lines_are_skipped(self):
        from anytype_llm_wiki.wiki.fetch import _recover_missing_lines

        nav = (
            "* [Home page of the site](/) [Masters and their students](/masters) "
            "[Contact the editors](/contact)"
        )
        baseline = self.PRIMARY + "\n\n" + nav
        assert _recover_missing_lines(self.PRIMARY, baseline) == self.PRIMARY

    def test_short_line_found_inside_a_longer_word_is_still_recovered(self):
        """Review r1 S1: presence is judged on word boundaries ("Sim." vs "simples")."""
        from anytype_llm_wiki.wiki.fetch import _recover_missing_lines

        primary = "A resposta foi simples: Mestre Bimbalino ensinava em 19745 lugares."
        baseline = f"{primary}\n\nSim.\n\nBimba\n\n1974"
        merged = _recover_missing_lines(primary, baseline)
        assert merged.endswith("Sim.\n\nBimba\n\n1974"), merged

    def test_whole_line_must_be_present(self):
        """Review r1 B1: a line whose middle is missing from the primary is recovered."""
        from anytype_llm_wiki.wiki.fetch import _recover_missing_lines

        head = "The opening words of a long paragraph that both extractors keep intact here,"
        tail = "and the closing words of the same paragraph that both of them keep as well."
        primary = f"{head} {tail}"
        line = f"{head} on 12 May 1920 in the Recôncavo, {tail}"
        assert _recover_missing_lines(primary, line).endswith(line)

    def test_recovered_images_keep_only_their_alt_text(self):
        """Review r1 N1: image markdown is removed from recovered lines as from trafilatura's."""
        from anytype_llm_wiki.wiki.fetch import _recover_missing_lines

        baseline = f"{self.PRIMARY}\n\n![Mestre Ana at the roda, 1974](https://x.test/a.jpg)"
        merged = _recover_missing_lines(self.PRIMARY, baseline)
        assert merged.endswith("Mestre Ana at the roda, 1974"), merged
        assert "x.test" not in merged

    def test_a_repeated_missing_line_is_appended_once(self):
        """Review r1 N2."""
        from anytype_llm_wiki.wiki.fetch import _recover_missing_lines

        line = "Learn more about the classes of this group and its teachers."
        merged = _recover_missing_lines(self.PRIMARY, f"{line}\n\n{self.PRIMARY}\n\n{line}")
        assert merged.count(line) == 1, merged

    def test_short_headings_are_recovered(self):
        """A card or section title is short but it is content, not chrome."""
        from anytype_llm_wiki.wiki.fetch import _recover_missing_lines

        baseline = self.PRIMARY + "\n\n#### Mestre Braga"
        assert _recover_missing_lines(self.PRIMARY, baseline).endswith("#### Mestre Braga")

    def test_recovered_lines_keep_baseline_order(self):
        from anytype_llm_wiki.wiki.fetch import _recover_missing_lines

        first = "First missing paragraph, which the baseline shows before the second one."
        second = "Second missing paragraph, which the baseline shows after the first one."
        merged = _recover_missing_lines(self.PRIMARY, f"{first}\n\n{self.PRIMARY}\n\n{second}")
        assert merged.index(first) < merged.index(second)
        assert merged.index(self.PRIMARY) < merged.index(first)


class TestRecoverSkipsPageFurniture:
    """Aldeia-IT/aldeia-box#1508: the recall step does not append furniture lines, a
    licence / copyright notice or a line that only states a month with a date or year
    (a byline or edit stamp). The model turned them into junk entities. Body lines,
    a bare year line and a caption with a place stay recovered (Aldeia-IT/aldeia-box#1432 D11a)."""

    PRIMARY = TestRecoverMissingLines.PRIMARY

    @pytest.mark.parametrize(
        "line",
        [
            (
                "Content is available under Creative Commons Attribution-ShareAlike 4.0 "
                "International (CC BY-SA 4.0) unless otherwise noted."
            ),
            "Copyright",
            "Copyright 2016 Velhos Mestres",
            "© 2026 Grupo Liberdade. All rights reserved.",
            "Todos os direitos reservados.",
            "© 2016 Velhosmestres.com. All rights reserved.",
            "Licensed under CC BY-SA 4.0",
            (
                "This work is licensed under a Creative Commons Attribution-ShareAlike "
                "4.0 International License."
            ),
            "outubro, 2016",
            "1 de Janeiro, 2010",
            "26 August 1997",
        ],
    )
    def test_furniture_line_is_not_appended(self, line):
        from anytype_llm_wiki.wiki.fetch import _recover_missing_lines

        assert _recover_missing_lines(self.PRIMARY, f"{self.PRIMARY}\n\n{line}") == self.PRIMARY

    @pytest.mark.parametrize(
        "line",
        [
            "1974",
            "Salvador, 1974",
            "Maio",
            "Mestre Ana",
            "He wrote the songs of the group and kept the copyright on all of them.",
            # Body sentences that mention ©, Creative Commons or copyright (review F1).
            (
                "Photo © Pierre Verger, taken in Salvador in 1946, shows Mestre Pastinha "
                "teaching at the academy."
            ),
            (
                "The recordings were later licensed under Creative Commons by the family "
                "so that students could share them."
            ),
            "Copyright disputes over the songs went on for years after Bimba died in 1974.",
            # A long line is body text even when it carries a notice phrase.
            (
                "The archive, all rights reserved by the family since the founder died, "
                "holds letters, photographs and recordings of the rodas that he led in "
                "Salvador and in Rio de Janeiro between 1940 and 1970."
            ),
            # A short body line that mentions a notice mid-sentence: the notice must
            # be the whole line (Aldeia-IT/aldeia-box#1508 fix round 2).
            (
                "The 1978 recording of the ladainha, licensed under the Creative Commons "
                "Attribution 4.0 licence by the family, is kept in the archive."
            ),
            "The songbook, all rights reserved, stayed with the family.",
            "His CC BY-SA 4.0 photos of the roda are in the archive.",
            "© 2016 photo by Pierre Verger of Mestre Pastinha teaching at his academy in Salvador",
            # Version numbers and Portuguese words are not dates (review F2, F3).
            "1.2.3",
            "Out 1",
            "Mar 3",
        ],
    )
    def test_body_lines_stay_recovered(self, line):
        from anytype_llm_wiki.wiki.fetch import _recover_missing_lines

        merged = _recover_missing_lines(self.PRIMARY, f"{self.PRIMARY}\n\n{line}")
        assert merged.endswith(line), merged


class TestCollapseSpaceRuns:
    """Aldeia-IT/aldeia-box#1508: runs of spaces inside a line of trafilatura's text
    become one space (a ~300-space padding run split a profile block from its text,
    and the model listed 15 sentences as entities). Markdown that relies on spaces
    keeps them: a hard break (two or more trailing spaces) stays a hard break,
    indentation, fenced code blocks and headings are untouched."""

    def test_interior_run_becomes_one_space(self):
        from anytype_llm_wiki.wiki.fetch import _collapse_space_runs

        padded = "Origem: Mestre Pelé da Bomba" + " " * 300 + "Mestre Índio fundou o grupo."
        assert _collapse_space_runs(padded) == (
            "Origem: Mestre Pelé da Bomba Mestre Índio fundou o grupo."
        )

    def test_non_breaking_space_and_tab_runs_collapse(self):
        from anytype_llm_wiki.wiki.fetch import _collapse_space_runs

        assert _collapse_space_runs("Grupo:   Oxossi\t\tPais: Brasil") == (
            "Grupo: Oxossi Pais: Brasil"
        )

    def test_a_single_non_breaking_space_is_kept(self):
        from anytype_llm_wiki.wiki.fetch import _collapse_space_runs

        assert _collapse_space_runs("Mestre Bimba") == "Mestre Bimba"

    def test_hard_break_is_kept_and_a_long_trailing_run_kept_as_one_hard_break(self):
        from anytype_llm_wiki.wiki.fetch import _collapse_space_runs

        assert _collapse_space_runs("line one  \nline two") == "line one  \nline two"
        assert _collapse_space_runs("line one" + " " * 40 + "\nline two") == (
            "line one  \nline two"
        )

    def test_indentation_is_kept(self):
        from anytype_llm_wiki.wiki.fetch import _collapse_space_runs

        text = "* item\n  * nested  item\n\n    indented   code"
        assert _collapse_space_runs(text) == "* item\n  * nested item\n\n    indented   code"

    def test_fenced_code_block_is_untouched(self):
        from anytype_llm_wiki.wiki.fetch import _collapse_space_runs

        text = "Before  it.\n\n```\nx    =  1\n```\n\nAfter   it."
        assert _collapse_space_runs(text) == "Before it.\n\n```\nx    =  1\n```\n\nAfter it."

    def test_a_fence_closes_only_on_its_own_character(self):
        """Review F6: inside a ``~~~`` block a ``` line is code, not the closing fence
        (CommonMark), so the lines after it stay untouched until ``~~~``."""
        from anytype_llm_wiki.wiki.fetch import _collapse_space_runs

        text = "~~~\n```\nx    =  1\n~~~\nAfter   it."
        assert _collapse_space_runs(text) == "~~~\n```\nx    =  1\n~~~\nAfter it."

    def test_a_longer_fence_needs_a_long_enough_closer(self):
        from anytype_llm_wiki.wiki.fetch import _collapse_space_runs

        text = "````\n```\nx    =  1\n````\nAfter   it."
        assert _collapse_space_runs(text) == "````\n```\nx    =  1\n````\nAfter it."

    def test_headings_are_untouched(self):
        from anytype_llm_wiki.wiki.fetch import _collapse_space_runs

        assert _collapse_space_runs("#  roda de  domingo") == "#  roda de  domingo"

    def test_trafilatura_text_is_collapsed(self, monkeypatch):
        """The collapse runs on trafilatura's output inside the fetch path."""
        import trafilatura

        from anytype_llm_wiki.wiki.fetch import extract_main_markdown

        body = (
            "The first paragraph of a shaped article body is long enough to pass the gate,"
            + " " * 120
            + "because it talks at length about rodas, berimbaus and the old masters of Bahia. "
        ) * 3
        monkeypatch.setattr(trafilatura, "extract", lambda *a, **k: body)
        html = f"<html><body><article><p>{body}</p></article></body></html>"
        md = extract_main_markdown(html)
        assert "gate, because" in md, md[:300]
        assert "  " not in md.replace("  \n", ""), md[:300]
