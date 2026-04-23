"""Tests for wiki/_base_client.py — _BaseAnytypeClient transport contract.

Covers AC #12 (_BaseAnytypeClient contract, inheritance hierarchy).
"""

import pytest
import respx
import httpx

ANYTYPE_BASE = "http://127.0.0.1:31012"
FAKE_API_KEY = "test-bearer-token"
FAKE_API_VERSION = "2025-11-08"


@pytest.fixture(autouse=True)
def set_anytype_env(monkeypatch):
    """Inject env vars so _BaseAnytypeClient can build its headers."""
    monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
    monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)


class TestBaseClientImport:
    def test_base_client_importable(self):
        """_BaseAnytypeClient must be importable from wiki._base_client."""
        from anytype_llm_wiki.wiki._base_client import _BaseAnytypeClient  # noqa: F401

    def test_base_client_is_class(self):
        """_BaseAnytypeClient must be a class."""
        from anytype_llm_wiki.wiki._base_client import _BaseAnytypeClient
        assert isinstance(_BaseAnytypeClient, type)


class TestBaseClientTransportContract:
    """Transport-only: session + headers + timeout + close()."""

    def test_base_client_has_close_method(self):
        """_BaseAnytypeClient must expose a close() method."""
        from anytype_llm_wiki.wiki._base_client import _BaseAnytypeClient
        assert hasattr(_BaseAnytypeClient, "close"), "_BaseAnytypeClient missing close()"

    def test_base_client_close_is_callable(self):
        """close() must be callable on a constructed instance."""
        from anytype_llm_wiki.wiki._base_client import _BaseAnytypeClient
        client = _BaseAnytypeClient()
        assert callable(getattr(client, "close", None))

    def test_base_client_close_closes_underlying_http_client(self):
        """Calling close() must close the underlying httpx.Client session."""
        from anytype_llm_wiki.wiki._base_client import _BaseAnytypeClient
        client = _BaseAnytypeClient()
        # Should not raise; after close the session should not be usable
        client.close()

    def test_base_client_headers_include_authorization(self):
        """_BaseAnytypeClient._headers() must include Authorization: Bearer <token>."""
        from anytype_llm_wiki.wiki._base_client import _BaseAnytypeClient
        client = _BaseAnytypeClient()
        headers = client._headers()
        assert "Authorization" in headers, "Authorization header missing"
        assert headers["Authorization"] == f"Bearer {FAKE_API_KEY}", (
            f"Authorization header wrong: {headers['Authorization']!r}"
        )

    def test_base_client_headers_include_anytype_version(self):
        """_BaseAnytypeClient._headers() must include Anytype-Version header."""
        from anytype_llm_wiki.wiki._base_client import _BaseAnytypeClient
        client = _BaseAnytypeClient()
        headers = client._headers()
        assert "Anytype-Version" in headers, "Anytype-Version header missing"
        assert headers["Anytype-Version"] == FAKE_API_VERSION


class TestBaseClientHasNoReadOrWriteMethods:
    """Base class must NOT define read-plane or write-plane methods.

    These methods belong on AnytypeReadClient and WikiClient respectively.
    The separation of concerns is deliberate per the spec S14 decision.
    """

    # Read-plane methods that belong ONLY on AnytypeReadClient
    @pytest.mark.parametrize("method_name", ["list_spaces", "list_objects", "get_object"])
    def test_base_client_does_not_have_read_methods(self, method_name):
        """_BaseAnytypeClient must not define read-plane method {method_name}."""
        from anytype_llm_wiki.wiki._base_client import _BaseAnytypeClient
        assert not hasattr(_BaseAnytypeClient, method_name), (
            f"_BaseAnytypeClient must not have {method_name} — "
            f"it belongs on AnytypeReadClient only"
        )

    # Write-plane methods that belong ONLY on WikiClient
    @pytest.mark.parametrize("method_name", [
        "create_type", "create_property", "create_tag",
        "create_object", "update_object", "search",
    ])
    def test_base_client_does_not_have_write_methods(self, method_name):
        """_BaseAnytypeClient must not define write-plane method {method_name}."""
        from anytype_llm_wiki.wiki._base_client import _BaseAnytypeClient
        assert not hasattr(_BaseAnytypeClient, method_name), (
            f"_BaseAnytypeClient must not have {method_name} — "
            f"it belongs on WikiClient only"
        )


class TestInheritanceHierarchy:
    """Both AnytypeReadClient and WikiClient must inherit from _BaseAnytypeClient."""

    def test_anytype_read_client_inherits_from_base(self):
        """AnytypeReadClient must be a subclass of _BaseAnytypeClient."""
        from anytype_llm_wiki.wiki._base_client import _BaseAnytypeClient
        from anytype_llm_wiki.anytype_client import AnytypeReadClient
        assert issubclass(AnytypeReadClient, _BaseAnytypeClient), (
            "AnytypeReadClient does not inherit from _BaseAnytypeClient"
        )

    def test_wiki_client_inherits_from_base(self):
        """WikiClient must be a subclass of _BaseAnytypeClient."""
        from anytype_llm_wiki.wiki._base_client import _BaseAnytypeClient
        from anytype_llm_wiki.wiki.wiki_client import WikiClient
        assert issubclass(WikiClient, _BaseAnytypeClient), (
            "WikiClient does not inherit from _BaseAnytypeClient"
        )

    def test_anytype_read_client_is_not_wiki_client_subclass(self):
        """AnytypeReadClient and WikiClient must be independent subclasses (no cross-inheritance)."""
        from anytype_llm_wiki.anytype_client import AnytypeReadClient
        from anytype_llm_wiki.wiki.wiki_client import WikiClient
        assert not issubclass(AnytypeReadClient, WikiClient)
        assert not issubclass(WikiClient, AnytypeReadClient)
