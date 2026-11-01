"""Tests for the main-content strip and the usable-content verdict in wiki/fetch.py.

Aldeia-IT/aldeia-box#1427 AC1 (boilerplate strip before markdownify) and AC9
(the raw-HTML verdict URL ingest uses to refuse pages with no usable content).
"""

import socket
from pathlib import Path

import httpx
import pytest
import respx

FIXTURES = Path(__file__).parent / "fixtures" / "pages"
LALAUE = (FIXTURES / "lalaue_shaped.html").read_text(encoding="utf-8")

_ARTICLE_TEXT = (
    "Mestre Bimba founded the first capoeira academy recognised by the state in Salvador. "
    "His Capoeira Regional added a structured teaching sequence, a graduation system and "
    "a set of fixed sequences that students practised in pairs before entering the roda. "
)


@pytest.fixture
def public_dns(monkeypatch):
    """Resolve every host to a public address so no real DNS lookup happens."""
    from anytype_llm_wiki.wiki import fetch as fetch_mod

    monkeypatch.setattr(
        fetch_mod.socket,
        "getaddrinfo",
        lambda host, *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))
        ],
    )


class TestStripBoilerplate:
    """AC1: landmarks and chrome are removed; the main content is the root."""

    def test_lalaue_shaped_page_starts_at_h1_without_menu_or_footer(self):
        from anytype_llm_wiki.wiki.fetch import _to_markdown

        md = _to_markdown(LALAUE, "text/html")
        assert md.startswith("# Associação De Capoeira Mestre Bimba"), md[:200]
        for junk in (
            "WHAT IS CAPOEIRA",
            "OUR MISSION",
            "Corridos",
            "Copyright",
            "Privacy Policy",
            "logo.png",
            "dataLayer",
            "trackPageView",
            "Share this page",
            "Capoeira School",  # the <title> text is not body content
        ):
            assert junk not in md, f"{junk!r} leaked into the markdown:\n{md}"
        assert "Centro de Cultura Fisica e Regional da Bahia" in md

    def test_local_html_file_is_stripped_too(self, tmp_path):
        from anytype_llm_wiki.wiki.fetch import fetch_url

        page = tmp_path / "lalaue.html"
        page.write_text(LALAUE, encoding="utf-8")
        md = fetch_url(str(page))
        assert md.startswith("# Associação De Capoeira Mestre Bimba"), md[:200]
        assert "OUR MISSION" not in md

    def test_main_element_is_the_root(self):
        from anytype_llm_wiki.wiki.fetch import strip_boilerplate

        html = (
            "<html><body><div class='promo'>Subscribe to our newsletter today</div>"
            f"<main><h1>Mestre Bimba</h1><p>{_ARTICLE_TEXT}</p></main>"
            "<div class='related'>Related posts you may like</div></body></html>"
        )
        out = strip_boilerplate(html)
        assert "Mestre Bimba" in out and "graduation system" in out
        assert "Subscribe to our newsletter" not in out
        assert "Related posts" not in out

    def test_role_main_and_aria_landmarks(self):
        from anytype_llm_wiki.wiki.fetch import strip_boilerplate

        html = (
            "<html><body><div role='banner'>Site banner text</div>"
            "<div role='navigation'>Home About Contact</div>"
            "<div role='search'>Search this site</div>"
            f"<div role='main'><h1>Roda</h1><p>{_ARTICLE_TEXT}</p>"
            "<form><input name='q'>Newsletter signup</form></div>"
            "<div role='contentinfo'>Footer contact info</div></body></html>"
        )
        out = strip_boilerplate(html)
        assert "graduation system" in out
        for junk in ("Site banner", "Home About", "Search this site", "Newsletter", "Footer contact"):
            assert junk not in out, junk

    def test_article_preferred_over_body(self):
        from anytype_llm_wiki.wiki.fetch import strip_boilerplate

        html = (
            "<html><body><div>Sidebar widget with a short blurb</div>"
            f"<article><h1>Roda</h1><p>{_ARTICLE_TEXT}</p></article></body></html>"
        )
        out = strip_boilerplate(html)
        assert "graduation system" in out
        assert "Sidebar widget" not in out

    def test_tiny_article_teaser_falls_back_to_stripped_body(self):
        """A root holding under 25 % of the body text gives way to the stripped body."""
        from anytype_llm_wiki.wiki.fetch import strip_boilerplate

        html = (
            "<html><body><nav>Menu entry</nav>"
            "<article><p>Read more</p></article>"
            f"<div class='content'><h1>Mestre Pastinha</h1><p>{_ARTICLE_TEXT * 3}</p></div>"
            "<footer>Footer text</footer></body></html>"
        )
        out = strip_boilerplate(html)
        assert "Mestre Pastinha" in out and "graduation system" in out
        assert "Menu entry" not in out and "Footer text" not in out

    def test_non_html_text_passes_through_unchanged(self):
        from anytype_llm_wiki.wiki.fetch import _to_markdown

        text = "# Plain notes\n\nnav header footer <not html>\n"
        assert _to_markdown(text, "text/plain") == text
        assert _to_markdown(text, "text/markdown") == text


class TestUsableContentVerdict:
    """AC9: the raw HTML (and the stripped markdown) decide whether a URL page is usable."""

    def test_normal_page_is_usable(self):
        from anytype_llm_wiki.wiki.fetch import _to_markdown, usable_content_verdict

        md = _to_markdown(LALAUE, "text/html")
        assert usable_content_verdict(LALAUE, md) is None

    def test_empty_body(self):
        from anytype_llm_wiki.wiki.fetch import usable_content_verdict

        assert usable_content_verdict("", "") == "empty"
        assert usable_content_verdict("   \n", "  \n") == "empty"

    def test_near_empty_page_reports_char_count(self):
        from anytype_llm_wiki.wiki.fetch import _to_markdown, usable_content_verdict

        html = (
            "<html><body><h1>Welcome</h1><p>Under construction. "
            "<a href='https://example.com/a-very-long-link-target-that-does-not-count'>Home</a></p>"
            "<img src='https://example.com/huge-image-url-that-does-not-count.png' alt=''></body></html>"
        )
        md = _to_markdown(html, "text/html")
        verdict = usable_content_verdict(html, md)
        assert verdict is not None and verdict.startswith("too_little_text ("), verdict
        n = int(verdict.split("(")[1].split()[0])
        assert n < 300
        assert "example.com" not in md or n < 60  # link targets are not counted

    def test_long_link_targets_do_not_count_as_text(self):
        from anytype_llm_wiki.wiki.fetch import usable_content_verdict

        md = " ".join(f"[x](https://example.com/{'p' * 80}/{i})" for i in range(10))
        verdict = usable_content_verdict("<html><body>links</body></html>", md)
        assert verdict and verdict.startswith("too_little_text"), verdict

    @pytest.mark.parametrize(
        "marker_html",
        [
            (
                "<html><head><title>Just a moment...</title></head><body>"
                "<div id='cf-chl-widget'>Verifying</div></body></html>"
            ),
            "<html><body><h1>Checking your browser before accessing the site</h1></body></html>",
            (
                "<html><head><title>Attention Required! | Cloudflare</title></head>"
                "<body><p>Sorry, you have been blocked</p></body></html>"
            ),
            "<html><body><div class='g-recaptcha' data-sitekey='x'></div></body></html>",
            "<html><body><div class='h-captcha'></div></body></html>",
            "<html><body><div class='cf-turnstile'></div></body></html>",
        ],
    )
    def test_challenge_page(self, marker_html):
        from anytype_llm_wiki.wiki.fetch import _to_markdown, usable_content_verdict

        md = _to_markdown(marker_html, "text/html")
        assert usable_content_verdict(marker_html, md) == "challenge_page"

    def test_captcha_in_a_form_on_a_short_real_page_is_not_a_challenge(self):
        """A group home page (~1,500 chars) with a login-form captcha is kept."""
        from anytype_llm_wiki.wiki.fetch import _to_markdown, usable_content_verdict

        html = (
            f"<html><body><div><h1>Grupo</h1><p>{_ARTICLE_TEXT * 6}</p></div>"
            "<input type='hidden' name='g-recaptcha-response'></body></html>"
        )
        md = _to_markdown(html, "text/html")
        assert usable_content_verdict(html, md) is None

    def test_captcha_widget_on_a_real_article_is_not_a_challenge(self):
        """A contact-form captcha beside a full article does not refuse the page."""
        from anytype_llm_wiki.wiki.fetch import _to_markdown, usable_content_verdict

        html = (
            f"<html><body><article><h1>Roda</h1><p>{_ARTICLE_TEXT * 20}</p></article>"
            "<div class='g-recaptcha'></div></body></html>"
        )
        md = _to_markdown(html, "text/html")
        assert usable_content_verdict(html, md) is None

    @pytest.mark.parametrize("mount", ["root", "app", "__next"])
    def test_js_shell_mount_point(self, mount):
        from anytype_llm_wiki.wiki.fetch import _to_markdown, usable_content_verdict

        html = (
            f"<!doctype html><html><head><title>App</title></head><body>"
            f"<div id='{mount}'></div><script src='/static/js/main.js'></script></body></html>"
        )
        md = _to_markdown(html, "text/html")
        assert usable_content_verdict(html, md) == "js_shell"

    def test_js_shell_noscript_notice_only(self):
        from anytype_llm_wiki.wiki.fetch import _to_markdown, usable_content_verdict

        html = (
            "<html><body><noscript>You need to enable JavaScript to run this app.</noscript>"
            "<div id='container'></div></body></html>"
        )
        md = _to_markdown(html, "text/html")
        assert usable_content_verdict(html, md) == "js_shell"


class TestFetchSource:
    """AC9: fetch_source returns the markdown plus the verdict; fetch_url is unchanged."""

    @respx.mock
    def test_url_returns_markdown_and_verdict(self, public_dns):
        from anytype_llm_wiki.wiki.fetch import fetch_source

        respx.get("https://lalaue.example/school").mock(
            return_value=httpx.Response(200, text=LALAUE, headers={"content-type": "text/html"})
        )
        fetched = fetch_source("https://lalaue.example/school")
        assert fetched["is_url"] is True
        assert fetched["unusable"] is None
        assert fetched["markdown"].startswith("# Associação De Capoeira Mestre Bimba")
        assert fetched["raw"] == LALAUE

    @respx.mock
    def test_url_js_shell_verdict(self, public_dns):
        from anytype_llm_wiki.wiki.fetch import fetch_source, fetch_url

        shell = "<html><body><div id='root'></div></body></html>"
        respx.get("https://spa.example/").mock(
            return_value=httpx.Response(200, text=shell, headers={"content-type": "text/html"})
        )
        assert fetch_source("https://spa.example/")["unusable"] == "js_shell"
        # fetch_url's contract (a markdown string) stays valid for its other callers.
        assert isinstance(fetch_url("https://spa.example/"), str)

    @respx.mock
    def test_403_is_fetch_failed(self, public_dns):
        from anytype_llm_wiki.wiki.fetch import fetch_source

        respx.get("https://blocked.example/").mock(return_value=httpx.Response(403))
        fetched = fetch_source("https://blocked.example/")
        assert fetched["markdown"].startswith("[DATA ERROR] fetch_failed")
        assert fetched["unusable"] is None

    def test_local_file_gets_no_verdict(self, tmp_path):
        from anytype_llm_wiki.wiki.fetch import fetch_source

        empty = tmp_path / "empty.md"
        empty.write_text("", encoding="utf-8")
        fetched = fetch_source(str(empty))
        assert fetched["is_url"] is False
        assert fetched["unusable"] is None
        assert fetched["markdown"] == ""
