"""Tests for indexer (requires Anytype, Ollama, and Qdrant)."""

import pytest

from anytype_rag.indexer import reindex, _load_state, _save_state, _ensure_collection, _qdrant
from anytype_rag import config


def _services_available() -> bool:
    import httpx

    try:
        httpx.get(f"{config.OLLAMA_URL}/api/tags", timeout=3)
        httpx.get(f"{config.ANYTYPE_API_URL}/v1/spaces", headers={
            "Authorization": f"Bearer {config.ANYTYPE_API_KEY}",
            "Anytype-Version": config.ANYTYPE_API_VERSION,
        }, timeout=3)
        httpx.get(f"{config.QDRANT_URL}/collections", headers={
            "api-key": config.QDRANT_API_KEY,
        }, timeout=3)
        return True
    except (httpx.ConnectError, httpx.TimeoutException):
        return False


@pytest.fixture(autouse=True)
def check_services():
    if not _services_available():
        pytest.skip("Required services not reachable")


class TestEnsureCollection:
    def test_creates_collection(self):
        client = _qdrant()
        _ensure_collection(client)
        names = [c.name for c in client.get_collections().collections]
        assert config.QDRANT_COLLECTION in names

    def test_idempotent(self):
        client = _qdrant()
        _ensure_collection(client)
        _ensure_collection(client)  # should not raise


class TestState:
    def test_load_missing_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "INDEX_STATE_FILE", tmp_path / "missing.json")
        assert _load_state() == {}

    def test_save_and_load(self, tmp_path, monkeypatch):
        state_file = tmp_path / "state.json"
        monkeypatch.setattr(config, "INDEX_STATE_FILE", state_file)
        monkeypatch.setattr(config, "INDEX_STATE_DIR", tmp_path)
        _save_state({"space-1": {"obj-1": "2026-01-01T00:00:00Z"}})
        loaded = _load_state()
        assert loaded == {"space-1": {"obj-1": "2026-01-01T00:00:00Z"}}


class TestReindex:
    def test_reindex_returns_stats(self):
        stats = reindex()
        assert "spaces" in stats
        assert "objects_checked" in stats
        assert "objects_indexed" in stats
        assert "chunks" in stats
        assert stats["spaces"] > 0

    def test_reindex_idempotent(self):
        # First run indexes everything
        stats1 = reindex()
        # Second run should find nothing changed
        stats2 = reindex()
        assert stats2["objects_indexed"] == 0

    def test_reindex_specific_space(self):
        from anytype_rag.anytype_client import list_spaces

        spaces = list_spaces()
        if not spaces:
            pytest.skip("No spaces")
        stats = reindex(space_id=spaces[0]["id"])
        assert stats["spaces"] == 1
