"""Tests for wiki/wiki_client.py — WikiClient write-plane API.

Covers AC #12 (WikiClient method surface).
Uses respx to mock all Anytype HTTP calls.
"""

import pytest
import respx
import httpx

ANYTYPE_BASE = "http://127.0.0.1:31012"
FAKE_SPACE_ID = "space-wiki-client-test"
FAKE_API_KEY = "test-wiki-client-key"
FAKE_API_VERSION = "2025-11-08"


@pytest.fixture(autouse=True)
def set_anytype_env(monkeypatch):
    monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
    monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)


class TestWikiClientImport:
    def test_wiki_client_importable(self):
        """WikiClient must be importable from wiki.wiki_client."""
        from anytype_llm_wiki.wiki.wiki_client import WikiClient  # noqa: F401

    def test_wiki_client_is_class(self):
        from anytype_llm_wiki.wiki.wiki_client import WikiClient
        assert isinstance(WikiClient, type)


class TestWikiClientMethodSurface:
    """WikiClient must expose all write-plane methods specified in the API."""

    @pytest.mark.parametrize("method_name", [
        "create_type",
        "create_property",
        "create_tag",
        "create_object",
        "update_object",
        "search",
    ])
    def test_wiki_client_has_method(self, method_name):
        """WikiClient must have method {method_name}."""
        from anytype_llm_wiki.wiki.wiki_client import WikiClient
        assert hasattr(WikiClient, method_name), (
            f"WikiClient missing method: {method_name}"
        )
        assert callable(getattr(WikiClient, method_name))


class TestWikiClientCreateType:
    """create_type POSTs to /v1/spaces/{space_id}/types and returns the type dict."""

    @respx.mock
    def test_create_type_posts_to_correct_url(self, monkeypatch):
        """create_type must POST to /v1/spaces/{space_id}/types."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        route = respx.post(
            f"{ANYTYPE_BASE}/v1/spaces/{FAKE_SPACE_ID}/types"
        ).mock(return_value=httpx.Response(200, json={
            "type": {"id": "obj-wiki_source", "key": "wiki_source"}
        }))
        from anytype_llm_wiki.wiki.wiki_client import WikiClient
        client = WikiClient()
        result = client.create_type(
            FAKE_SPACE_ID,
            {"type_key": "wiki_source", "name": "Source"},
        )
        assert route.called
        assert result["id"] == "obj-wiki_source"

    @respx.mock
    def test_create_type_returns_dict(self, monkeypatch):
        """create_type must return a dict."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        respx.post(
            f"{ANYTYPE_BASE}/v1/spaces/{FAKE_SPACE_ID}/types"
        ).mock(return_value=httpx.Response(200, json={
            "type": {"id": "t1", "key": "wiki_entity"}
        }))
        from anytype_llm_wiki.wiki.wiki_client import WikiClient
        client = WikiClient()
        result = client.create_type(FAKE_SPACE_ID, {"type_key": "wiki_entity"})
        assert isinstance(result, dict)


class TestWikiClientCreateProperty:
    """create_property POSTs to /v1/spaces/{space_id}/properties and returns the property dict."""

    @respx.mock
    def test_create_property_posts_to_correct_url(self, monkeypatch):
        """create_property must POST to /v1/spaces/{space_id}/properties."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        route = respx.post(
            f"{ANYTYPE_BASE}/v1/spaces/{FAKE_SPACE_ID}/properties"
        ).mock(return_value=httpx.Response(200, json={
            "property": {"id": "prop-wiki_url", "key": "wiki_url"}
        }))
        from anytype_llm_wiki.wiki.wiki_client import WikiClient
        client = WikiClient()
        result = client.create_property(
            FAKE_SPACE_ID,
            "wiki_source",
            {"property_key": "wiki_url", "format": "url"},
        )
        assert route.called
        assert isinstance(result, dict)


class TestWikiClientCreateTag:
    """create_tag POSTs to the appropriate option-creation endpoint."""

    @respx.mock
    def test_create_tag_returns_dict(self, monkeypatch):
        """create_tag must return a dict with tag info."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        # Match any POST (endpoint shape is flexible per the create_tag contract).
        # NOTE: the original `respx.post(respx.patterns.M)` form raises a TypeError
        # at route-registration time in respx 0.23.x (M is a combinator factory,
        # not a URL). A no-arg `respx.post()` is the idiomatic match-any-POST form
        # and preserves this test's sole assertion (result is a dict). See debrief.
        respx.post().mock(return_value=httpx.Response(200, json={
            "option": {"id": "tag-wiki_ai-research", "name": "wiki_ai-research"}
        }))
        from anytype_llm_wiki.wiki.wiki_client import WikiClient
        client = WikiClient()
        result = client.create_tag(FAKE_SPACE_ID, "wiki_domain_tags", "wiki_ai-research")
        assert isinstance(result, dict)


class TestWikiClientSearch:
    """search queries the Anytype search endpoint and returns a list of objects."""

    @respx.mock
    def test_search_returns_list(self, monkeypatch):
        """search must return a list."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        respx.post(
            f"{ANYTYPE_BASE}/v1/spaces/{FAKE_SPACE_ID}/search"
        ).mock(return_value=httpx.Response(200, json={"data": []}))
        from anytype_llm_wiki.wiki.wiki_client import WikiClient
        client = WikiClient()
        result = client.search(FAKE_SPACE_ID, query="BGE-M3")
        assert isinstance(result, list)


class TestWikiClientUpdateObject:
    """update_object PATCHes the object and returns the updated dict."""

    @respx.mock
    def test_update_object_patches_correct_url(self, monkeypatch):
        """update_object must PATCH /v1/spaces/{space_id}/objects/{object_id}."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        object_id = "obj-123"
        route = respx.patch(
            f"{ANYTYPE_BASE}/v1/spaces/{FAKE_SPACE_ID}/objects/{object_id}"
        ).mock(return_value=httpx.Response(200, json={
            "object": {"id": object_id, "name": "Updated"}
        }))
        from anytype_llm_wiki.wiki.wiki_client import WikiClient
        client = WikiClient()
        result = client.update_object(
            FAKE_SPACE_ID,
            object_id,
            {"name": "Updated"},
        )
        assert route.called
        assert isinstance(result, dict)
