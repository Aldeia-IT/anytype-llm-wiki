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

New tests added for v1 (issue #323) — type+date metadata filter:
- FakeQdrantClientWithSearch: fake client supporting query_points and
  create_payload_index, used by all filter tests below.
- AC-F1 test_no_filter_regression: no filter params → query_filter=None
- AC-F2 test_type_filter_applied: types → nested Filter(should=[...]) shape
- AC-F4 test_date_range_filter_applied: DatetimeRange condition on last_modified_date
- AC-F5 test_combined_filter_and, test_empty_list_types_is_no_filter,
        test_zero_result_filter
- AC-F6 test_invalid_date_raises_value_error (from semantic_search)
- AC-F7 test_reindex_creates_payload_indexes, test_reembed_does_not_create_payload_indexes
- AC-F11 test_schema_version_bump_forces_full_reembed, test_no_bump_keeps_incremental_skip
- AC-F12 test_reembed_writes_last_modified_date
"""

import json
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


# ---------------------------------------------------------------------------
# v1 (issue #323) — Type+date metadata filter: CI-runnable seam tests
# These tests FAIL until:
#   - semantic_search_core accepts ingested_after / ingested_before params
#   - _ensure_payload_indexes is added (reindex path only)
#   - _chunk_to_payload helper is added (writes last_modified_date)
#   - config.PAYLOAD_SCHEMA_VERSION constant is added
# ---------------------------------------------------------------------------


class FakeQdrantClientWithSearch:
    """Fake Qdrant client for metadata-filter tests (spec §10.1).

    Supports query_points (captures query_filter), create_payload_index
    (records which fields were indexed), upsert, delete, get_collections,
    create_collection.  Never emits UserWarning.
    """

    def __init__(self, mock_results=None):
        self.upserted_points = []
        self.deleted = []
        self.query_calls = []
        self.query_filter = None
        self.created_indexes = []
        self._mock_results = mock_results or []

    def get_collections(self):
        class _Col:
            name = config.QDRANT_COLLECTION

        class _Result:
            collections = [_Col()]

        return _Result()

    def create_collection(self, **kwargs):
        pass

    def create_payload_index(self, collection_name, field_name, field_schema=None, **kwargs):
        self.created_indexes.append(field_name)  # no-op; never emits a warning

    def upsert(self, collection_name, points):
        self.upserted_points.extend(points)

    def delete(self, collection_name, points_selector):
        self.deleted.append(points_selector)

    def query_points(self, collection_name, query, query_filter=None, limit=10, with_payload=True):
        self.query_filter = query_filter
        self.query_calls.append({
            "collection_name": collection_name,
            "query_filter": query_filter,
            "limit": limit,
            "with_payload": with_payload,
        })

        class _Result:
            points = self._mock_results

        _Result.points = self._mock_results
        return _Result()


# ---------------------------------------------------------------------------
# AC-F1 — No-filter regression
# ---------------------------------------------------------------------------


def test_no_filter_regression(monkeypatch):
    """AC-F1: no filter params → query_filter=None, collection+limit+with_payload unchanged."""
    import anytype_llm_wiki.indexer as _indexer

    fake = FakeQdrantClientWithSearch()
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(_indexer, "embed_query", lambda q: [0.1] * config.EMBED_DIMS)
    _indexer.semantic_search_core(query="test")
    call = fake.query_calls[-1]
    assert call["query_filter"] is None
    assert call["collection_name"] == config.QDRANT_COLLECTION
    assert call["limit"] == 10
    assert call["with_payload"] is True


# ---------------------------------------------------------------------------
# AC-F2 — Type filter applied (nested should shape)
# ---------------------------------------------------------------------------


def test_type_filter_applied(monkeypatch):
    """AC-F2: types → nested Filter(should=[FieldCondition(MatchValue)]) appended to must."""
    import anytype_llm_wiki.indexer as _indexer

    fake = FakeQdrantClientWithSearch()
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(_indexer, "embed_query", lambda q: [0.1] * config.EMBED_DIMS)
    _indexer.semantic_search_core(query="test", types=["wiki_entity", "wiki_concept"])
    must = fake.query_filter.must
    type_cond = next((c for c in must if hasattr(c, "should") and c.should), None)
    assert type_cond is not None, f"No nested type Filter in must: {must}"
    keys = {c.match.value for c in type_cond.should if hasattr(c, "match")}
    assert {"wiki_entity", "wiki_concept"} <= keys


# ---------------------------------------------------------------------------
# AC-F4 — Date range filter applied (DatetimeRange, both bounds)
# ---------------------------------------------------------------------------


def test_date_range_filter_applied(monkeypatch):
    """AC-F4: ingested_after/before → FieldCondition(last_modified_date, DatetimeRange)."""
    from qdrant_client.models import DatetimeRange, FieldCondition
    import anytype_llm_wiki.indexer as _indexer

    fake = FakeQdrantClientWithSearch()
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(_indexer, "embed_query", lambda q: [0.1] * config.EMBED_DIMS)
    _indexer.semantic_search_core(
        query="test",
        ingested_after="2026-01-01T00:00:00Z",
        ingested_before="2026-06-30T23:59:59Z",
    )
    must = fake.query_filter.must
    date_cond = next(
        (c for c in must if isinstance(c, FieldCondition) and c.key == "last_modified_date"),
        None,
    )
    assert date_cond is not None, f"No date FieldCondition in must: {must}"
    assert isinstance(date_cond.range, DatetimeRange), (
        f"Expected DatetimeRange (not Range), got {type(date_cond.range)}"
    )
    assert date_cond.range.gte is not None and date_cond.range.lte is not None


# ---------------------------------------------------------------------------
# AC-F5 — Combined AND filter (type + date)
# ---------------------------------------------------------------------------


def test_combined_filter_and(monkeypatch):
    """AC-F5: type + date both present → both conditions in must list."""
    from qdrant_client.models import FieldCondition
    import anytype_llm_wiki.indexer as _indexer

    fake = FakeQdrantClientWithSearch()
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(_indexer, "embed_query", lambda q: [0.1] * config.EMBED_DIMS)
    _indexer.semantic_search_core(
        query="test",
        types=["wiki_entity"],
        ingested_after="2026-01-01T00:00:00Z",
    )
    must = fake.query_filter.must
    assert any(hasattr(c, "should") and c.should for c in must), "Missing nested type Filter"
    assert any(
        isinstance(c, FieldCondition) and c.key == "last_modified_date" for c in must
    ), "Missing date FieldCondition"


# ---------------------------------------------------------------------------
# AC-F5b — Empty-list types == no filter
# ---------------------------------------------------------------------------


def test_empty_list_types_is_no_filter(monkeypatch):
    """AC-F5b: types=[] is falsy → query_filter=None (no type condition)."""
    import anytype_llm_wiki.indexer as _indexer

    fake = FakeQdrantClientWithSearch()
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(_indexer, "embed_query", lambda q: [0.1] * config.EMBED_DIMS)
    _indexer.semantic_search_core(query="test", types=[])
    assert fake.query_filter is None


# ---------------------------------------------------------------------------
# AC-F5c — Zero-result filter returns empty list (no error)
# ---------------------------------------------------------------------------


def test_zero_result_filter(monkeypatch):
    """AC-F5c: zero-result filter returns [] without raising."""
    import anytype_llm_wiki.indexer as _indexer

    fake = FakeQdrantClientWithSearch(mock_results=[])
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(_indexer, "embed_query", lambda q: [0.1] * config.EMBED_DIMS)
    out = _indexer.semantic_search_core(query="test", types=["wiki_entity"])
    assert out == []


# ---------------------------------------------------------------------------
# AC-F6 — Invalid date raises ValueError from semantic_search
# ---------------------------------------------------------------------------


def test_invalid_date_raises_value_error():
    """AC-F6: malformed ingested_after raises ValueError from semantic_search MCP tool."""
    import pytest as _pytest
    from anytype_llm_wiki.server import semantic_search
    with _pytest.raises(ValueError, match="ingested_after"):
        semantic_search(query="test", ingested_after="not-a-date")


# ---------------------------------------------------------------------------
# AC-F7 — Payload indexes on reindex path; NOT on reembed hot path
# ---------------------------------------------------------------------------


def test_reindex_creates_payload_indexes(monkeypatch):
    """AC-F7a: reindex() calls _ensure_payload_indexes → type_key, space_id,
    last_modified_date in created_indexes; source_type must NOT be there.
    """
    import anytype_llm_wiki.indexer as _indexer

    fake = FakeQdrantClientWithSearch()
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(_indexer, "list_spaces", lambda: [])
    _indexer.reindex()
    assert set(fake.created_indexes) >= {"type_key", "space_id", "last_modified_date"}, (
        f"Expected payload indexes for type_key/space_id/last_modified_date; "
        f"got: {fake.created_indexes}"
    )
    assert "source_type" not in fake.created_indexes, (
        "source_type must NOT be indexed (deferred to #336)"
    )


def test_reembed_does_not_create_payload_indexes(monkeypatch):
    """AC-F7b: reembed_object() must NOT call create_payload_index."""
    import anytype_llm_wiki.indexer as _indexer

    fake = FakeQdrantClientWithSearch()
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(
        _indexer, "embed", lambda texts: [[0.1] * config.EMBED_DIMS for _ in texts]
    )
    _indexer.reembed_object(
        "sp-1",
        "obj-1",
        {
            "id": "obj-1",
            "space_id": "sp-1",
            "name": "X",
            "type": {"key": "wiki_entity"},
            "markdown": "# H\nbody",
            "properties": [],
        },
    )
    assert fake.created_indexes == [], (
        f"reembed_object must NOT call create_payload_index. "
        f"Got: {fake.created_indexes}"
    )


# ---------------------------------------------------------------------------
# AC-F11 — Schema-version bump forces full re-embed; no bump preserves skip
# ---------------------------------------------------------------------------


def test_schema_version_bump_forces_full_reembed(monkeypatch, tmp_path):
    """AC-F11a: stored _payload_schema_version < code version → unchanged object
    is still re-embedded; new version stamped in state file.
    """
    import anytype_llm_wiki.indexer as _indexer

    state = {"_payload_schema_version": 1, "sp-1": {"obj-1": "2026-01-01T00:00:00Z"}}
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps(state))
    monkeypatch.setattr(config, "INDEX_STATE_FILE", state_file)
    monkeypatch.setattr(config, "INDEX_STATE_DIR", tmp_path)
    monkeypatch.setattr(config, "PAYLOAD_SCHEMA_VERSION", 2)

    fake = FakeQdrantClientWithSearch()
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(_indexer, "list_spaces", lambda: [{"id": "sp-1"}])
    monkeypatch.setattr(
        _indexer,
        "list_objects",
        lambda sid: [
            {
                "id": "obj-1",
                "properties": [{"key": "last_modified_date", "date": "2026-01-01T00:00:00Z"}],
            }
        ],
    )
    monkeypatch.setattr(
        _indexer,
        "get_object",
        lambda sid, oid: {
            "id": "obj-1",
            "space_id": "sp-1",
            "name": "X",
            "type": {"key": "wiki_entity"},
            "markdown": "# H\nbody",
            "properties": [{"key": "last_modified_date", "date": "2026-01-01T00:00:00Z"}],
        },
    )
    monkeypatch.setattr(
        _indexer, "embed", lambda texts: [[0.1] * config.EMBED_DIMS for _ in texts]
    )

    stats = _indexer.reindex()
    assert stats["objects_indexed"] == 1, (
        f"With schema version bump, unchanged object MUST be re-indexed; stats={stats}"
    )
    assert fake.upserted_points, "Expected Qdrant upsert after forced re-embed"
    new_state = json.loads(state_file.read_text())
    assert new_state["_payload_schema_version"] == 2, (
        f"State file must be stamped with new PAYLOAD_SCHEMA_VERSION=2; got {new_state}"
    )


def test_no_bump_keeps_incremental_skip(monkeypatch, tmp_path):
    """AC-F11b: stored version == code version → unchanged object skipped (objects_indexed=0)."""
    import anytype_llm_wiki.indexer as _indexer

    state = {"_payload_schema_version": 2, "sp-1": {"obj-1": "2026-01-01T00:00:00Z"}}
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps(state))
    monkeypatch.setattr(config, "INDEX_STATE_FILE", state_file)
    monkeypatch.setattr(config, "INDEX_STATE_DIR", tmp_path)
    monkeypatch.setattr(config, "PAYLOAD_SCHEMA_VERSION", 2)

    fake = FakeQdrantClientWithSearch()
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(_indexer, "list_spaces", lambda: [{"id": "sp-1"}])
    monkeypatch.setattr(
        _indexer,
        "list_objects",
        lambda sid: [
            {
                "id": "obj-1",
                "properties": [{"key": "last_modified_date", "date": "2026-01-01T00:00:00Z"}],
            }
        ],
    )
    monkeypatch.setattr(
        _indexer, "embed", lambda texts: [[0.1] * config.EMBED_DIMS for _ in texts]
    )

    stats = _indexer.reindex()
    assert stats["objects_indexed"] == 0, (
        f"No schema version bump → incremental skip must be preserved; stats={stats}"
    )


# ---------------------------------------------------------------------------
# AC-F12 — reembed_object writes last_modified_date
# ---------------------------------------------------------------------------


def test_reembed_writes_last_modified_date(monkeypatch):
    """AC-F12: reembed_object with a dated object → every upserted point's payload
    carries last_modified_date.
    """
    import anytype_llm_wiki.indexer as _indexer

    fake = FakeQdrantClientWithSearch()
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(
        _indexer, "embed", lambda texts: [[0.1] * config.EMBED_DIMS for _ in texts]
    )
    _indexer.reembed_object(
        "sp-1",
        "obj-1",
        {
            "id": "obj-1",
            "space_id": "sp-1",
            "name": "X",
            "type": {"key": "wiki_entity"},
            "markdown": "# H\nbody",
            "properties": [{"key": "last_modified_date", "date": "2026-05-01T00:00:00Z"}],
        },
    )
    assert fake.upserted_points, "Expected at least one upserted point"
    assert all(
        p.payload.get("last_modified_date") == "2026-05-01T00:00:00Z"
        for p in fake.upserted_points
    ), (
        f"All upserted payloads must carry last_modified_date='2026-05-01T00:00:00Z'. "
        f"Got: {[p.payload for p in fake.upserted_points]}"
    )
