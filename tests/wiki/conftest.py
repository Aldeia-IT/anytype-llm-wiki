"""Shared fixtures for tests/wiki/ — respx mocks, base URLs, and canned Anytype responses."""

import pytest
import respx
import httpx

ANYTYPE_BASE = "http://127.0.0.1:31012"
FAKE_SPACE_ID = "space-test-001"
FAKE_API_KEY = "test-api-key-xxx"
FAKE_API_VERSION = "2025-11-08"

# Canned type-creation response (returned for every create-type POST in mocked tests)
def _make_type_response(type_key: str, space_id: str = FAKE_SPACE_ID) -> dict:
    return {
        "type": {
            "id": f"obj-{type_key}",
            "key": type_key,
            "name": type_key.replace("wiki_", "").capitalize(),
            "spaceId": space_id,
        }
    }


def _make_property_response(property_key: str, type_key: str) -> dict:
    return {
        "property": {
            "id": f"prop-{property_key}",
            "key": property_key,
            "typeKey": type_key,
        }
    }


def _make_tag_response(tag: str, property_key: str) -> dict:
    return {
        "option": {
            "id": f"tag-{tag}",
            "name": tag,
            "propertyKey": property_key,
        }
    }


def _make_collection_response(space_id: str = FAKE_SPACE_ID) -> dict:
    return {
        "object": {
            "id": "coll-wiki-root-001",
            "name": "Wiki",
            "spaceId": space_id,
        }
    }


def _make_wiki_log_response(space_id: str = FAKE_SPACE_ID) -> dict:
    return {
        "object": {
            "id": "log-001",
            "name": "bootstrap",
            "spaceId": space_id,
        }
    }


@pytest.fixture
def anytype_env(monkeypatch):
    """Set Anytype env vars to point at the test base URL with a fake API key."""
    monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
    monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)


@pytest.fixture
def anytype_available():
    """Skip test if ANYTYPE_API_KEY is not set in the environment (live-API guard)."""
    import os
    if not os.environ.get("ANYTYPE_API_KEY"):
        pytest.skip("ANYTYPE_API_KEY not set — live-API test skipped")


@pytest.fixture
def mock_anytype():
    """Context manager that activates respx mocking for Anytype HTTP calls.

    Yields the respx mock router so individual tests can add route-specific matchers.
    """
    with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
        yield router
