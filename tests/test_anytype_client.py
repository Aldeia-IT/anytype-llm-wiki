"""Tests for Anytype API client.

Live-API tests (TestListSpaces, TestListObjects, TestGetObject) require a running
Anytype CLI — they skip automatically when Anytype is unreachable.

v0.2.0 additions (AC #12 — BLOCKING-CTO-1):
  - TestAnytypeReadClientClassPath: covers AnytypeReadClient().list_spaces() /
    list_objects() / get_object() with respx-mocked responses (no live network).
  - TestModuleWrapperPath: covers the module-level free functions
    (list_spaces, list_objects, get_object) with respx mocks.
  - TestImportRegressionIndexer: asserts that the import used by indexer.py:11
    still resolves after the v0.2.0 refactor.
  - TestBaseClientInheritance: asserts AnytypeReadClient is a subclass of
    _BaseAnytypeClient.
"""

import pytest
import respx
import httpx

from anytype_llm_wiki.anytype_client import list_spaces, list_objects, get_object
from anytype_llm_wiki import config

ANYTYPE_BASE = "http://127.0.0.1:31012"
FAKE_API_KEY = "test-client-key"
FAKE_API_VERSION = "2025-11-08"


@pytest.fixture
def check_anytype():
    """Skip LIVE tests if Anytype API is not reachable.

    This fixture is NOT autouse — live test classes request it explicitly via
    a class-level autouse fixture. The v0.2.0 mock-based test classes do not
    request this fixture and therefore are not gated by live-API availability.
    """
    import httpx as _httpx

    try:
        _httpx.get(
            f"{config.ANYTYPE_API_URL}/v1/spaces",
            headers={
                "Authorization": f"Bearer {config.ANYTYPE_API_KEY}",
                "Anytype-Version": config.ANYTYPE_API_VERSION,
            },
            timeout=5,
        )
    except (_httpx.ConnectError, _httpx.TimeoutException, _httpx.LocalProtocolError):
        pytest.skip("Anytype API not reachable")


class TestListSpaces:
    @pytest.fixture(autouse=True)
    def _require_live_anytype(self, check_anytype):
        """Gate this test class on live Anytype availability."""
        pass

    def test_returns_list(self):
        spaces = list_spaces()
        assert isinstance(spaces, list)
        assert len(spaces) > 0

    def test_space_has_id_and_name(self):
        spaces = list_spaces()
        for space in spaces:
            assert "id" in space
            assert "name" in space


class TestListObjects:
    @pytest.fixture(autouse=True)
    def _require_live_anytype(self, check_anytype):
        pass

    def test_returns_list(self):
        spaces = list_spaces()
        objects = list_objects(spaces[0]["id"])
        assert isinstance(objects, list)

    def test_objects_have_required_fields(self):
        spaces = list_spaces()
        objects = list_objects(spaces[0]["id"])
        if objects:
            obj = objects[0]
            assert "id" in obj
            assert "name" in obj
            assert "type" in obj


class TestGetObject:
    @pytest.fixture(autouse=True)
    def _require_live_anytype(self, check_anytype):
        pass

    def test_returns_markdown(self):
        spaces = list_spaces()
        objects = list_objects(spaces[0]["id"])
        if not objects:
            pytest.skip("No objects in space")
        obj = get_object(spaces[0]["id"], objects[0]["id"])
        assert "id" in obj
        assert "markdown" in obj


# ---------------------------------------------------------------------------
# v0.2.0 additions — AC #12 (BLOCKING-CTO-1)
# All tests below use respx mocks and do NOT require a live Anytype instance.
# They are NOT gated by the autouse check_anytype fixture.
# ---------------------------------------------------------------------------


class TestAnytypeReadClientImport:
    """AC #12(a): AnytypeReadClient must be importable from anytype_client."""

    def test_anytype_read_client_importable(self):
        """AnytypeReadClient must be importable from anytype_llm_wiki.anytype_client."""
        # This test must FAIL before v0.2.0 implementation (class does not exist yet)
        from anytype_llm_wiki.anytype_client import AnytypeReadClient  # noqa: F401

    def test_anytype_read_client_is_class(self):
        from anytype_llm_wiki.anytype_client import AnytypeReadClient
        assert isinstance(AnytypeReadClient, type)


class TestAnytypeReadClientClassPath:
    """AC #12(a): Class-level path AnytypeReadClient().list_spaces() etc. with respx mocks."""

    @respx.mock
    def test_class_list_spaces_returns_list(self, monkeypatch):
        """AnytypeReadClient().list_spaces() must return a list of dicts."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        respx.get(f"{ANYTYPE_BASE}/v1/spaces").mock(
            return_value=httpx.Response(200, json={
                "data": [{"id": "space-1", "name": "My Space"}]
            })
        )
        from anytype_llm_wiki.anytype_client import AnytypeReadClient
        client = AnytypeReadClient()
        result = client.list_spaces()
        assert isinstance(result, list)
        assert result[0]["id"] == "space-1"

    @respx.mock
    def test_class_list_spaces_space_has_id_and_name(self, monkeypatch):
        """AnytypeReadClient().list_spaces() result items must have 'id' and 'name'."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        respx.get(f"{ANYTYPE_BASE}/v1/spaces").mock(
            return_value=httpx.Response(200, json={
                "data": [{"id": "sp1", "name": "Space One"}]
            })
        )
        from anytype_llm_wiki.anytype_client import AnytypeReadClient
        result = AnytypeReadClient().list_spaces()
        assert "id" in result[0]
        assert "name" in result[0]

    @respx.mock
    def test_class_list_objects_returns_list(self, monkeypatch):
        """AnytypeReadClient().list_objects(space_id) must return a list."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        space_id = "space-1"
        respx.get(f"{ANYTYPE_BASE}/v1/spaces/{space_id}/objects").mock(
            return_value=httpx.Response(200, json={
                "data": [{"id": "obj-1", "name": "Note", "type": "page"}],
                "pagination": {"has_more": False}
            })
        )
        from anytype_llm_wiki.anytype_client import AnytypeReadClient
        result = AnytypeReadClient().list_objects(space_id)
        assert isinstance(result, list)
        assert result[0]["id"] == "obj-1"

    @respx.mock
    def test_class_get_object_returns_dict_with_id(self, monkeypatch):
        """AnytypeReadClient().get_object(space_id, object_id) must return a dict with 'id'."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        space_id = "space-1"
        object_id = "obj-1"
        respx.get(f"{ANYTYPE_BASE}/v1/spaces/{space_id}/objects/{object_id}").mock(
            return_value=httpx.Response(200, json={
                "object": {"id": object_id, "name": "Note", "markdown": "# Note\nContent."}
            })
        )
        from anytype_llm_wiki.anytype_client import AnytypeReadClient
        result = AnytypeReadClient().get_object(space_id, object_id)
        assert isinstance(result, dict)
        assert result["id"] == object_id


class TestModuleWrapperPath:
    """AC #12(b): module-level wrapper functions resolve and return same data as class path."""

    @respx.mock
    def test_wrapper_list_spaces_returns_same_data_as_class(self, monkeypatch):
        """Module-level list_spaces() must return the same data as AnytypeReadClient().list_spaces()."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        respx.get(f"{ANYTYPE_BASE}/v1/spaces").mock(
            return_value=httpx.Response(200, json={
                "data": [{"id": "sp-w", "name": "Wrapper Space"}]
            })
        )
        from anytype_llm_wiki import anytype_client as _ac
        result = _ac.list_spaces()
        assert isinstance(result, list)
        assert result[0]["id"] == "sp-w"

    @respx.mock
    def test_wrapper_list_objects_returns_list(self, monkeypatch):
        """Module-level list_objects() must resolve and return a list."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        space_id = "sp-w"
        respx.get(f"{ANYTYPE_BASE}/v1/spaces/{space_id}/objects").mock(
            return_value=httpx.Response(200, json={
                "data": [{"id": "o-w", "name": "Object", "type": "page"}],
                "pagination": {"has_more": False}
            })
        )
        from anytype_llm_wiki import anytype_client as _ac
        result = _ac.list_objects(space_id)
        assert isinstance(result, list)

    @respx.mock
    def test_wrapper_get_object_returns_dict(self, monkeypatch):
        """Module-level get_object() must resolve and return a dict."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        space_id = "sp-w"
        object_id = "o-w"
        respx.get(f"{ANYTYPE_BASE}/v1/spaces/{space_id}/objects/{object_id}").mock(
            return_value=httpx.Response(200, json={
                "object": {"id": object_id, "markdown": "# Title"}
            })
        )
        from anytype_llm_wiki import anytype_client as _ac
        result = _ac.get_object(space_id, object_id)
        assert isinstance(result, dict)
        assert result["id"] == object_id


class TestImportRegressionIndexer:
    """AC #12(c): The exact import used by indexer.py:11 must still resolve after v0.2.0 refactor."""

    def test_indexer_import_surface_still_resolves(self):
        """from anytype_llm_wiki.anytype_client import get_object, list_objects, list_spaces

        This is the exact import statement from indexer.py:11.
        Must resolve without ImportError after the v0.2.0 anytype_client.py refactor.
        """
        # Import in the same form as indexer.py:11 uses
        from anytype_llm_wiki.anytype_client import get_object, list_objects, list_spaces  # noqa: F401

    def test_indexer_imported_functions_are_callable(self):
        """All three functions imported by indexer.py must be callable."""
        from anytype_llm_wiki.anytype_client import get_object, list_objects, list_spaces
        assert callable(list_spaces)
        assert callable(list_objects)
        assert callable(get_object)


class TestBaseClientInheritance:
    """AC #12 — AnytypeReadClient must inherit from _BaseAnytypeClient."""

    def test_anytype_read_client_inherits_from_base_anytype_client(self):
        """AnytypeReadClient must be a subclass of _BaseAnytypeClient (shared base contract)."""
        from anytype_llm_wiki.anytype_client import AnytypeReadClient
        from anytype_llm_wiki.wiki._base_client import _BaseAnytypeClient
        assert issubclass(AnytypeReadClient, _BaseAnytypeClient), (
            "AnytypeReadClient does not inherit from _BaseAnytypeClient. "
            "The v0.2.0 refactor requires both read and write clients to share "
            "the same transport contract."
        )
