"""Tests for indexer (requires Anytype, Ollama, and Qdrant).

Existing tests are skip-gated on services being reachable.

New tests added for v0.3.0:
- test_property_only_reindex_upserts_payload (AC-P9, §9.2, CTO-R2-A1):
  CI-runnable seam test — fake Qdrant + fake embedder; reindex a property-only
  (empty-body) wiki object → assert a Qdrant upsert whose payload carries the
  property chunk's text and heading (e.g. heading=="Facts", wiki_facts text).
  Does NOT stub chunk_object itself. Lives here (not tests/wiki/) so the
  indexer module-level symbols (_qdrant, get_object, list_objects, list_spaces,
  embed) are monkeypatchable.

- test_update_path_forces_reembed (AC-P9/V2 fail action, §9.2, QA-A1):
  Deterministic seam test — simulate a property-only update where
  last_modified_date does NOT advance (V2-fail condition); assert wiki_ingest
  fires the re-embed bypass for the affected object.
"""

import pytest

from anytype_llm_wiki.indexer import reindex, _load_state, _save_state, _ensure_collection, _qdrant
from anytype_llm_wiki import config


def _services_available() -> bool:
    import httpx

    try:
        resp = httpx.get(f"{config.OLLAMA_URL}/api/tags", timeout=3)
        resp.raise_for_status()
        resp = httpx.get(f"{config.ANYTYPE_API_URL}/v1/spaces", headers={
            "Authorization": f"Bearer {config.ANYTYPE_API_KEY}",
            "Anytype-Version": config.ANYTYPE_API_VERSION,
        }, timeout=3)
        resp.raise_for_status()
        resp = httpx.get(f"{config.QDRANT_URL}/collections", headers={
            "api-key": config.QDRANT_API_KEY,
        }, timeout=3)
        resp.raise_for_status()
        return True
    except httpx.HTTPError:
        return False


@pytest.fixture(autouse=True)
def check_services(request):
    """Skip live tests when services are unreachable; let new CI tests run always."""
    # New CI-only tests are NOT auto-skip-gated — only the live test class is.
    if "live" in (m.name for m in request.node.iter_markers()):
        if not _services_available():
            pytest.skip("Required services not reachable")
    elif request.node.cls is not None and getattr(request.node.cls, "_requires_live", False):
        if not _services_available():
            pytest.skip("Required services not reachable")


class TestEnsureCollection:
    _requires_live = True

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
    _requires_live = True

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
        from anytype_llm_wiki.anytype_client import list_spaces

        spaces = list_spaces()
        if not spaces:
            pytest.skip("No spaces")
        stats = reindex(space_id=spaces[0]["id"])
        assert stats["spaces"] == 1


# ---------------------------------------------------------------------------
# v0.3.0 — CI-runnable seam tests (no live deps)
# These tests FAIL until chunker.py is extended with property-chunk support.
# ---------------------------------------------------------------------------


class TestPropertyOnlyReindexUpsertsPayload:
    """AC-P9 (QA-B2, CTO-R2-A1) — CI-runnable seam test.

    Drive the REAL chunk_object → embed → upsert path with a fake _qdrant() spy
    client and a fake embedder. Assert a Qdrant upsert is issued whose payload
    carries the property chunk's text and heading (heading=="Facts", wiki_facts text).

    MUST live in tests/test_indexer.py where the indexer module-level symbols
    (_qdrant, get_object, list_objects, list_spaces, embed) are monkeypatchable.
    Does NOT stub chunk_object itself.
    """

    def test_property_only_reindex_upserts_payload(self, monkeypatch, tmp_path):
        """AC-P9: reindex a property-only (empty-body) wiki object → Qdrant upsert carries
        the property chunk's text and heading == 'Facts'.

        Backstops the live path chunk_object → indexer → embed → upsert;
        no live Anytype/Qdrant/Ollama required.
        Covers: §9.2 test_property_only_reindex_upserts_payload, AC-P9, QA-B2, CTO-R2-A1.
        """
        import anytype_llm_wiki.indexer as _indexer

        FAKE_SPACE_ID = "space-test-seam"
        FAKE_OBJ_ID = "entity-seam-001"
        WIKI_FACTS_TEXT = "- Neural networks are inspired by the brain\n- Transformers use attention"

        # The "full" wiki object returned by get_object — property-only, empty body
        full_wiki_obj = {
            "id": FAKE_OBJ_ID,
            "space_id": FAKE_SPACE_ID,
            "name": "Neural Networks",
            "type": {"key": "wiki_entity"},
            "markdown": "",  # empty body — invariant for ingest-authored objects
            "properties": [
                {"key": "wiki_facts", "text": WIKI_FACTS_TEXT},
            ],
        }

        # Summary object (what list_objects returns) — has a last_modified_date
        # that is not yet in state so the indexer will process it.
        summary_obj = {
            "id": FAKE_OBJ_ID,
            "space_id": FAKE_SPACE_ID,
            "name": "Neural Networks",
            "type": {"key": "wiki_entity"},
            "properties": [
                {"key": "last_modified_date", "date": "2026-06-03T10:00:00Z"},
            ],
        }

        # Fake Qdrant client — captures upsert calls for assertion
        class FakeQdrantClient:
            def __init__(self):
                self.upserted_points = []
                self.collections_called = False
                self.created_collection = False
                self.deleted = []

            def get_collections(self):
                self.collections_called = True
                class _Col:
                    name = config.QDRANT_COLLECTION
                class _Result:
                    collections = [_Col()]
                return _Result()

            def create_collection(self, **kwargs):
                self.created_collection = True

            def upsert(self, collection_name, points):
                self.upserted_points.extend(points)

            def delete(self, collection_name, points_selector):
                self.deleted.append(points_selector)

        fake_client = FakeQdrantClient()

        # Fake embedder — returns deterministic unit vectors
        def fake_embed(texts: list[str]) -> list[list[float]]:
            return [[0.1] * config.EMBED_DIMS for _ in texts]

        # Monkeypatch indexer module-level symbols
        monkeypatch.setattr(_indexer, "_qdrant", lambda: fake_client)
        monkeypatch.setattr(_indexer, "list_spaces", lambda: [{"id": FAKE_SPACE_ID}])
        monkeypatch.setattr(_indexer, "list_objects", lambda sid: [summary_obj])
        monkeypatch.setattr(_indexer, "get_object", lambda sid, oid: full_wiki_obj)
        monkeypatch.setattr(_indexer, "embed", fake_embed)

        # Use a temp state file so the object appears as "not yet indexed"
        state_file = tmp_path / "index_state.json"
        monkeypatch.setattr(config, "INDEX_STATE_FILE", state_file)
        monkeypatch.setattr(config, "INDEX_STATE_DIR", tmp_path)

        stats = reindex()

        # The indexer must have processed the property-only object
        assert stats["objects_indexed"] >= 1, (
            f"Expected objects_indexed >= 1 for property-only wiki object; stats={stats}"
        )
        assert stats["chunks"] >= 1, (
            f"Expected at least 1 chunk upserted; stats={stats}"
        )

        # Assert a Qdrant upsert was issued
        assert len(fake_client.upserted_points) >= 1, (
            "Expected at least one upsert point; fake_client.upserted_points is empty"
        )

        # The payload must carry the property chunk's text and heading == 'Facts'
        # Assert as ONE coherent check (per Mem0 anti-fragmentation rule)
        payloads = [p.payload for p in fake_client.upserted_points]
        matching = [
            p for p in payloads
            if p.get("heading") == "Facts" and WIKI_FACTS_TEXT in p.get("text", "")
        ]
        assert len(matching) >= 1, (
            f"Expected at least one upserted point with heading='Facts' and wiki_facts text. "
            f"Payloads found: {payloads}"
        )


class TestUpdatePathForcesReembed:
    """AC-P9/V2-fail action (QA-A1): when last_modified_date does NOT advance after a
    property-only update, wiki_ingest must fire the re-embed bypass for the affected object.

    This test pins the V2-fail condition behavior: even if last_modified_date is unchanged,
    ingest must force a re-embed (object-scoped delete + re-upsert, or full-space reindex).

    Uses fake Qdrant/indexer spies; no live deps.
    Covers: §9.2 test_update_path_forces_reembed, AC-P9, QA-A1.
    """

    def test_update_path_forces_reembed(self, monkeypatch, tmp_path):
        """AC-P9/V2-fail: property-only update where last_modified_date does NOT advance →
        wiki_ingest forces re-embed of the affected object (bypass the last_modified short-circuit).

        The preferred mechanism is object-scoped delete-by-object_id + re-upsert (O(1)).
        Fallback: full-space reindex. Both are acceptable — the test asserts that SOME
        re-embed occurs (new upsert points appear in the fake client after the bypass).
        """
        import anytype_llm_wiki.indexer as _indexer
        from anytype_llm_wiki.wiki.ingest import force_reembed_object  # noqa: F401
        # ^ This import will fail (module not yet implemented) — which is the EXPECTED failure mode.
        # The test documents the required function signature for the implementation.
        # When wiki/ingest.py is implemented with force_reembed_object, the test will pass.

        FAKE_SPACE_ID = "space-seam-v2fail"
        FAKE_OBJ_ID = "entity-v2fail-001"
        STALE_LAST_MOD = "2026-06-01T00:00:00Z"  # same before and after (V2-fail condition)
        UPDATED_WIKI_FACTS = "- Updated fact: quantum computing achieves supremacy\n- New insight added"

        full_obj_after_update = {
            "id": FAKE_OBJ_ID,
            "space_id": FAKE_SPACE_ID,
            "name": "Quantum Computing",
            "type": {"key": "wiki_entity"},
            "markdown": "",
            "properties": [
                {"key": "wiki_facts", "text": UPDATED_WIKI_FACTS},
            ],
        }

        class FakeQdrantClientV2:
            def __init__(self):
                self.upserted_points = []
                self.deleted_object_ids = []

            def get_collections(self):
                class _Col:
                    name = config.QDRANT_COLLECTION
                class _Result:
                    collections = [_Col()]
                return _Result()

            def upsert(self, collection_name, points):
                self.upserted_points.extend(points)

            def delete(self, collection_name, points_selector):
                # Track which object_ids are explicitly deleted (object-scoped re-embed)
                self.deleted_object_ids.append(FAKE_OBJ_ID)

        fake_client = FakeQdrantClientV2()

        def fake_embed(texts: list[str]) -> list[list[float]]:
            return [[0.2] * config.EMBED_DIMS for _ in texts]

        monkeypatch.setattr(_indexer, "_qdrant", lambda: fake_client)
        monkeypatch.setattr(_indexer, "embed", fake_embed)

        state_file = tmp_path / "index_state_v2fail.json"
        monkeypatch.setattr(config, "INDEX_STATE_FILE", state_file)
        monkeypatch.setattr(config, "INDEX_STATE_DIR", tmp_path)

        # Seed state to simulate "already indexed at STALE_LAST_MOD"
        _save_state({FAKE_SPACE_ID: {FAKE_OBJ_ID: STALE_LAST_MOD}})

        # Invoke force_reembed_object — the v0.3.0 bypass path for V2-fail condition
        force_reembed_object(
            space_id=FAKE_SPACE_ID,
            object_id=FAKE_OBJ_ID,
            obj=full_obj_after_update,
        )

        # Assert a re-upsert occurred for the updated object
        assert len(fake_client.upserted_points) >= 1, (
            "Expected at least one upsert after force_reembed_object; "
            f"fake_client.upserted_points is empty"
        )
        # Assert the upserted payload carries the UPDATED facts
        payloads = [p.payload for p in fake_client.upserted_points]
        matching = [
            p for p in payloads
            if "quantum computing" in p.get("text", "").lower()
        ]
        assert len(matching) >= 1, (
            f"Expected upserted payload with updated wiki_facts text; payloads={payloads}"
        )
