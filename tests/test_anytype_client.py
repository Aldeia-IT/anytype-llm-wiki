"""Tests for Anytype API client (requires running Anytype CLI)."""

import pytest

from anytype_llm_wiki.anytype_client import list_spaces, list_objects, get_object
from anytype_llm_wiki import config


@pytest.fixture(autouse=True)
def check_anytype():
    """Skip if Anytype API is not reachable."""
    import httpx

    try:
        resp = httpx.get(
            f"{config.ANYTYPE_API_URL}/v1/spaces",
            headers={
                "Authorization": f"Bearer {config.ANYTYPE_API_KEY}",
                "Anytype-Version": config.ANYTYPE_API_VERSION,
            },
            timeout=5,
        )
        resp.raise_for_status()
    except httpx.HTTPError:
        pytest.skip("Anytype API not reachable")


class TestListSpaces:
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
    def test_returns_markdown(self):
        spaces = list_spaces()
        objects = list_objects(spaces[0]["id"])
        if not objects:
            pytest.skip("No objects in space")
        obj = get_object(spaces[0]["id"], objects[0]["id"])
        assert "id" in obj
        assert "markdown" in obj
