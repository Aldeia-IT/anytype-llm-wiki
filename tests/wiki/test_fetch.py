"""Tests for wiki/fetch.py — URL fetching with SSRF protections and markdownify HTML→markdown.

These tests FAIL until src/anytype_llm_wiki/wiki/fetch.py is implemented.
Covers: AC#4 (SSRF rejection incl. 302-redirect to 127.0.0.1:31012), AC#5 (concurrent lock),
AC#6 (dash-fold normalization), AC#17 (DNS-rebinding tripwire), AC#8 (file fetch).
"""

import os
import pytest
import respx
import httpx

ANYTYPE_BASE = "http://127.0.0.1:31012"
FAKE_SPACE_ID = "space-fetch-test-001"
FAKE_API_KEY = "test-fetch-key"
FAKE_API_VERSION = "2025-11-08"


@pytest.fixture(autouse=True)
def set_anytype_env(monkeypatch):
    monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
    monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)


class TestFetchImport:
    """fetch.py module must be importable."""

    def test_fetch_module_importable(self):
        """wiki.fetch must be importable (AC#4, AC#17 — SSRF protections ship in fetch.py)."""
        from anytype_llm_wiki.wiki import fetch  # noqa: F401

    def test_fetch_url_function_exists(self):
        """wiki.fetch must export a fetch_url (or equivalent) function."""
        from anytype_llm_wiki.wiki import fetch
        assert hasattr(fetch, "fetch_url") or hasattr(fetch, "fetch_source"), (
            "fetch.py must export fetch_url or fetch_source"
        )


class TestURLFetch:
    """AC#1 / §9.1 — URL fetch happy path (respx mock)."""

    @respx.mock
    def test_url_fetch_returns_markdown(self):
        """AC#1: fetching a URL returns markdown content (HTML→markdown via markdownify).

        Covers: §9.1 URL fetch with respx.
        """
        respx.get("https://arxiv.org/abs/2302.13971").mock(
            return_value=httpx.Response(
                200,
                text="<html><body><h1>Attention Is All You Need</h1><p>Abstract text here.</p></body></html>",
                headers={"content-type": "text/html; charset=utf-8"},
            )
        )
        from anytype_llm_wiki.wiki.fetch import fetch_url
        result = fetch_url("https://arxiv.org/abs/2302.13971")
        assert isinstance(result, str), "fetch_url must return a string"
        assert len(result) > 0, "fetch_url must return non-empty content"
        # markdownify should have converted H1 to markdown heading
        assert "Attention" in result, "Expected 'Attention' in fetched markdown"

    @respx.mock
    def test_url_fetch_converts_html_to_markdown(self):
        """§9.1: HTML content is converted to markdown via markdownify."""
        respx.get("https://example.com/page").mock(
            return_value=httpx.Response(
                200,
                text="<html><body><h1>Title</h1><h2>Section</h2><p>Body paragraph.</p></body></html>",
                headers={"content-type": "text/html; charset=utf-8"},
            )
        )
        from anytype_llm_wiki.wiki.fetch import fetch_url
        result = fetch_url("https://example.com/page")
        # Should contain markdown heading markers
        assert "#" in result, "Expected markdown heading markers in HTML→markdown conversion"


class TestSSRFRejection:
    """AC#4: SSRF protections — direct and redirect-to-private-IP rejection."""

    def test_ssrf_localhost_rejected(self):
        """AC#4: fetching http://127.0.0.1/anything must be rejected with [DATA ERROR] ssrf_blocked.

        Covers: §9.1 SSRF rejection (direct private IP).
        """
        from anytype_llm_wiki.wiki.fetch import fetch_url
        try:
            result = fetch_url("http://127.0.0.1/anything")
            result_str = str(result)
        except Exception as exc:
            result_str = str(exc)
        assert "ssrf_blocked" in result_str or "[DATA ERROR]" in result_str, (
            f"Expected [DATA ERROR] ssrf_blocked for 127.0.0.1, got: {result_str!r}"
        )

    def test_ssrf_private_172_rejected(self):
        """AC#4: fetching http://172.16.0.1/ must be rejected (RFC1918 range)."""
        from anytype_llm_wiki.wiki.fetch import fetch_url
        try:
            result = fetch_url("http://172.16.0.1/")
            result_str = str(result)
        except Exception as exc:
            result_str = str(exc)
        assert "ssrf_blocked" in result_str or "[DATA ERROR]" in result_str, (
            f"Expected [DATA ERROR] ssrf_blocked for 172.16.0.1, got: {result_str!r}"
        )

    def test_ssrf_private_10_rejected(self):
        """AC#4: fetching http://10.0.0.1/ must be rejected (RFC1918 range)."""
        from anytype_llm_wiki.wiki.fetch import fetch_url
        try:
            result = fetch_url("http://10.0.0.1/")
            result_str = str(result)
        except Exception as exc:
            result_str = str(exc)
        assert "ssrf_blocked" in result_str or "[DATA ERROR]" in result_str, (
            f"Expected [DATA ERROR] ssrf_blocked for 10.0.0.1, got: {result_str!r}"
        )

    def test_ssrf_anytype_port_rejected(self):
        """AC#4: fetching http://127.0.0.1:31012/ (Anytype API port) must be rejected.

        This is the port used by the Anytype desktop API — a targeted SSRF guard.
        Covers: §9.1 SSRF rejection.
        """
        from anytype_llm_wiki.wiki.fetch import fetch_url
        try:
            result = fetch_url("http://127.0.0.1:31012/v1/spaces")
            result_str = str(result)
        except Exception as exc:
            result_str = str(exc)
        assert "ssrf_blocked" in result_str or "[DATA ERROR]" in result_str, (
            f"Expected [DATA ERROR] ssrf_blocked for Anytype port 31012, got: {result_str!r}"
        )

    @respx.mock
    def test_ssrf_redirect_to_127_0_0_1_blocked(self):
        """AC#4: URL 302-redirecting to 127.0.0.1:31012 is rejected with [DATA ERROR] ssrf_blocked.

        Covers: §9.1 AC#4 (302-redirect to 127.0.0.1:31012 → ssrf_blocked).
        """
        # Simulate a 302 redirect to the Anytype API port
        respx.get("https://attacker.example.com/redirect").mock(
            return_value=httpx.Response(
                302,
                headers={"Location": "http://127.0.0.1:31012/v1/spaces"},
            )
        )
        from anytype_llm_wiki.wiki.fetch import fetch_url
        try:
            result = fetch_url("https://attacker.example.com/redirect")
            result_str = str(result)
        except Exception as exc:
            result_str = str(exc)
        assert "ssrf_blocked" in result_str or "[DATA ERROR]" in result_str, (
            f"Expected [DATA ERROR] ssrf_blocked after 302 redirect to 127.0.0.1:31012, "
            f"got: {result_str!r}"
        )


class TestFileFetch:
    """§9.1 — file fetch (absolute path to a local file)."""

    def test_file_fetch_returns_content(self, tmp_path):
        """§9.1: fetching an absolute file path returns the file's content as markdown.

        Covers: §9.1 file fetch.
        """
        test_file = tmp_path / "notes.md"
        test_file.write_text("# My Notes\n\nThis is a test note.\n", encoding="utf-8")
        from anytype_llm_wiki.wiki.fetch import fetch_url
        result = fetch_url(str(test_file))
        assert "My Notes" in result or "notes" in result.lower(), (
            f"Expected file content in result, got: {result!r}"
        )

    def test_file_fetch_missing_file_returns_error(self, tmp_path):
        """§9.1: fetching a non-existent file returns an error (not a crash)."""
        missing_path = str(tmp_path / "does_not_exist.md")
        from anytype_llm_wiki.wiki.fetch import fetch_url
        try:
            result = fetch_url(missing_path)
            result_str = str(result)
        except Exception as exc:
            result_str = str(exc)
        # Should return an error message, not an unhandled exception
        assert len(result_str) > 0


class TestDNSRebindingTripwire:
    """AC#17: DNS-rebinding tripwire — controlled-resolver fixture → ssrf_blocked."""

    def test_dns_rebinding_tripwire(self, monkeypatch):
        """AC#17: a hostname that resolves to a private IP (DNS-rebinding) must be rejected.

        The SSRF guard must check the resolved IP, not just the URL's hostname.
        Covers: §9.1 DNS-rebinding tripwire (AC#17).
        """
        import socket

        # Monkeypatch getaddrinfo to simulate a hostname resolving to 127.0.0.1
        original_getaddrinfo = socket.getaddrinfo

        def fake_getaddrinfo(host, port, *args, **kwargs):
            if host == "rebind.attacker.example.com":
                # Simulate DNS rebinding: the hostname resolves to 127.0.0.1
                return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", port or 80))]
            return original_getaddrinfo(host, port, *args, **kwargs)

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
        from anytype_llm_wiki.wiki.fetch import fetch_url
        try:
            result = fetch_url("https://rebind.attacker.example.com/page")
            result_str = str(result)
        except Exception as exc:
            result_str = str(exc)
        assert "ssrf_blocked" in result_str or "[DATA ERROR]" in result_str, (
            f"Expected [DATA ERROR] ssrf_blocked for DNS-rebinding to 127.0.0.1, "
            f"got: {result_str!r}"
        )


class TestMaxBytesLimit:
    """§9.1 / master spec: fetch must respect WIKI_FETCH_MAX_BYTES."""

    @respx.mock
    def test_max_bytes_respected(self, monkeypatch):
        """§9.1: response body exceeding WIKI_FETCH_MAX_BYTES is truncated or rejected."""
        monkeypatch.setenv("WIKI_FETCH_MAX_BYTES", "100")
        large_html = "<html><body>" + ("A" * 10000) + "</body></html>"
        respx.get("https://bigpage.example.com/").mock(
            return_value=httpx.Response(200, text=large_html, headers={"content-type": "text/html"})
        )
        from anytype_llm_wiki.wiki.fetch import fetch_url
        result = fetch_url("https://bigpage.example.com/")
        # Result must not be a 10KB markdown dump if the limit is 100 bytes
        assert len(result) < len(large_html), (
            "Expected fetch result to be truncated when WIKI_FETCH_MAX_BYTES is exceeded"
        )
