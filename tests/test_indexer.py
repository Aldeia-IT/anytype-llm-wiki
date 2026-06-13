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

    def test_save_is_atomic_and_leaves_no_temp(self, tmp_path, monkeypatch):
        """#342: _save_state writes via a temp file + os.replace(). The result fully
        replaces prior content (atomic rename, not append) and no stray temp file is
        left behind in the state directory."""
        state_file = tmp_path / "state.json"
        monkeypatch.setattr(config, "INDEX_STATE_FILE", state_file)
        monkeypatch.setattr(config, "INDEX_STATE_DIR", tmp_path)
        _save_state({"space-1": {"obj-1": "v1"}})
        _save_state({"space-2": {"obj-2": "v2"}})  # must fully replace, not merge
        assert _load_state() == {"space-2": {"obj-2": "v2"}}
        leftovers = [p.name for p in tmp_path.iterdir() if p.name != "state.json"]
        assert leftovers == [], f"temp files left behind after _save_state: {leftovers}"


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


def test_reindex_creates_payload_indexes(monkeypatch, tmp_path):
    """#336 AC-IDX (updated from AC-F7a): reindex() calls _ensure_payload_indexes →
    type_key, space_id, last_modified_date, source_type, domain_tags all in created_indexes.

    The old assertion 'source_type not in created_indexes' is REMOVED (it was the
    deferral guard for #336 which this test now pins as REQUIRED).
    """
    import anytype_llm_wiki.indexer as _indexer

    fake = FakeQdrantClientWithSearch()
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(_indexer, "list_spaces", lambda: [])
    # Isolate index state so reindex()'s _save_state never touches real machine state.
    monkeypatch.setattr(config, "INDEX_STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(config, "INDEX_STATE_DIR", tmp_path)
    _indexer.reindex()
    assert set(fake.created_indexes) >= {
        "type_key", "space_id", "last_modified_date",
        "source_type", "domain_tags",   # NEW in #336: both must be KEYWORD-indexed
    }, (
        f"Missing indexes; expected {{type_key, space_id, last_modified_date, source_type, domain_tags}}; "
        f"got: {fake.created_indexes}"
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


def test_scoped_reindex_does_not_stamp_schema_marker(monkeypatch, tmp_path):
    """Review C1: a SCOPED reindex(space_id=...) must backfill its named space
    (force_full applies) but must NOT advance the global _payload_schema_version
    marker. A single-space reindex auto-fires after every wiki_ingest/wiki_remember;
    stamping the marker there would strand every other space on the old payload.
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

    # SCOPED reindex of the named space only.
    stats = _indexer.reindex(space_id="sp-1")
    assert stats["objects_indexed"] == 1, (
        f"Scoped reindex with schema bump MUST still re-embed its named space; stats={stats}"
    )
    assert fake.upserted_points, "Expected Qdrant upsert after forced re-embed of scoped space"

    new_state = json.loads(state_file.read_text())
    assert new_state["_payload_schema_version"] == 1, (
        "Scoped reindex MUST NOT advance the global _payload_schema_version marker "
        "(it must remain 1 so a later full reindex still backfills other spaces); "
        f"got {new_state}"
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


# ---------------------------------------------------------------------------
# #342 — reindex overlap guard (host-local advisory lock)
# ---------------------------------------------------------------------------


class TestReindexLock:
    """#342 item 2: reindex() takes a non-blocking host-local advisory lock so two
    concurrent runs cannot race the shared state.json write. CI-runnable (no live deps)."""

    def test_reindex_skips_when_lock_held(self, tmp_path, monkeypatch):
        """A reindex started while another holds the lock skips cleanly (does no work,
        returns skipped=True) instead of racing the state write."""
        import fcntl as _fcntl
        import os as _os
        import anytype_llm_wiki.indexer as _indexer

        monkeypatch.setattr(config, "INDEX_STATE_FILE", tmp_path / "state.json")
        monkeypatch.setattr(config, "INDEX_STATE_DIR", tmp_path)

        def _boom_spaces():
            raise AssertionError("reindex did work despite the lock being held")

        def _boom_qdrant():
            raise AssertionError("reindex touched Qdrant despite the lock being held")

        monkeypatch.setattr(_indexer, "list_spaces", _boom_spaces)
        monkeypatch.setattr(_indexer, "_qdrant", _boom_qdrant)

        # Simulate a concurrent reindex already holding the lock (separate fd →
        # flock conflicts even within this process).
        lock_path = tmp_path / "reindex.lock"
        fd = _os.open(str(lock_path), _os.O_CREAT | _os.O_RDWR, 0o600)
        _fcntl.flock(fd, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
        try:
            stats = _indexer.reindex()
        finally:
            _os.close(fd)

        assert stats.get("skipped") is True, f"expected skip while lock held; got {stats}"
        assert stats.get("reason") == "reindex_in_progress"
        assert stats["objects_indexed"] == 0

    def test_reindex_runs_when_lock_free(self, tmp_path, monkeypatch):
        """With a free lock, reindex() acquires it and runs normally (no skip flag)."""
        import anytype_llm_wiki.indexer as _indexer

        monkeypatch.setattr(config, "INDEX_STATE_FILE", tmp_path / "state.json")
        monkeypatch.setattr(config, "INDEX_STATE_DIR", tmp_path)
        fake = FakeQdrantClientWithSearch()
        monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
        monkeypatch.setattr(_indexer, "list_spaces", lambda: [])
        stats = _indexer.reindex()
        assert not stats.get("skipped"), f"reindex should run with a free lock; got {stats}"
        assert stats["spaces"] == 0


# ---------------------------------------------------------------------------
# #336 — AC-PAYLOAD: _chunk_to_payload propagates source_type/domain_tags
# ---------------------------------------------------------------------------


def test_chunk_to_payload_propagates_and_omits():
    """#336 AC-PAYLOAD: _chunk_to_payload copies source_type/domain_tags when present
    and OMITS them (key absent, not null) when absent.

    This closes the SF8 gap: AC-S2/S3 cover chunk_object output and AC-F-* cover
    filter build, but this independently exercises the payload-builder copy/omit seam.
    """
    import anytype_llm_wiki.indexer as _indexer

    # present → copied through
    p = _indexer._chunk_to_payload({
        "object_id": "o", "space_id": "s", "object_name": "n",
        "type_key": "wiki_source", "heading": "Excerpt", "text": "t",
        "source_type": "document", "domain_tags": ["ai", "ml"],
    })
    assert p["source_type"] == "document", (
        f"source_type must be copied to payload; got {p.get('source_type')!r}"
    )
    assert p["domain_tags"] == ["ai", "ml"], (
        f"domain_tags must be copied to payload; got {p.get('domain_tags')!r}"
    )

    # absent → KEY ABSENT from payload dict (not null), matching Qdrant filter-miss-on-absent
    p2 = _indexer._chunk_to_payload({
        "object_id": "o", "space_id": "s", "object_name": "n",
        "type_key": "wiki_entity", "heading": "Facts", "text": "t",
    })
    assert "source_type" not in p2, (
        "source_type must be ABSENT (not None) from payload when not in chunk"
    )
    assert "domain_tags" not in p2, (
        "domain_tags must be ABSENT (not None) from payload when not in chunk"
    )


# ---------------------------------------------------------------------------
# #336 — AC-F-ST: source_type filter applied (MatchAny)
# ---------------------------------------------------------------------------


def test_source_type_filter_applied(monkeypatch):
    """#336 AC-F-ST: source_type=[...] → FieldCondition(key='source_type', MatchAny) in must list."""
    from qdrant_client.models import FieldCondition
    import anytype_llm_wiki.indexer as _indexer

    fake = FakeQdrantClientWithSearch()
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(_indexer, "embed_query", lambda q: [0.1] * config.EMBED_DIMS)
    _indexer.semantic_search_core(query="test", source_type=["document"])
    assert fake.query_filter is not None, "Expected a non-None query_filter with source_type filter"
    must = fake.query_filter.must
    st_cond = next(
        (c for c in must if isinstance(c, FieldCondition) and c.key == "source_type"), None
    )
    assert st_cond is not None, (
        f"Expected FieldCondition(key='source_type') in must list; got must={must}"
    )
    assert st_cond.match.any == ["document"], (
        f"source_type FieldCondition must use MatchAny(any=['document']); got {st_cond.match}"
    )


# ---------------------------------------------------------------------------
# #336 — AC-F-DT: domain_tags filter applied (MatchAny, ANY-overlap)
# ---------------------------------------------------------------------------


def test_domain_tags_filter_applied(monkeypatch):
    """#336 AC-F-DT: domain_tags=[...] → FieldCondition(key='domain_tags', MatchAny) in must list."""
    from qdrant_client.models import FieldCondition
    import anytype_llm_wiki.indexer as _indexer

    fake = FakeQdrantClientWithSearch()
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(_indexer, "embed_query", lambda q: [0.1] * config.EMBED_DIMS)
    _indexer.semantic_search_core(query="test", domain_tags=["ai", "ml"])
    assert fake.query_filter is not None, "Expected a non-None query_filter with domain_tags filter"
    must = fake.query_filter.must
    dt_cond = next(
        (c for c in must if isinstance(c, FieldCondition) and c.key == "domain_tags"), None
    )
    assert dt_cond is not None, (
        f"Expected FieldCondition(key='domain_tags') in must list; got must={must}"
    )
    assert set(dt_cond.match.any) == {"ai", "ml"}, (
        f"domain_tags FieldCondition must use MatchAny(any=['ai','ml']); got {dt_cond.match}"
    )


# ---------------------------------------------------------------------------
# #336 — AC-F-COMB: Combined AND filter (source_type + domain_tags + existing)
# ---------------------------------------------------------------------------


def test_combined_filter_source_type_and_domain_tags(monkeypatch):
    """#336 AC-F-COMB: types + source_type + domain_tags → all clauses in must (AND composition)."""
    from qdrant_client.models import FieldCondition
    import anytype_llm_wiki.indexer as _indexer

    fake = FakeQdrantClientWithSearch()
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(_indexer, "embed_query", lambda q: [0.1] * config.EMBED_DIMS)
    _indexer.semantic_search_core(
        query="test",
        types=["wiki_entity"],
        source_type=["document"],
        domain_tags=["ai"],
    )
    assert fake.query_filter is not None, "Expected a non-None query_filter"
    must = fake.query_filter.must
    assert any(isinstance(c, FieldCondition) and c.key == "source_type" for c in must), (
        f"source_type FieldCondition missing from must; got must={must}"
    )
    assert any(isinstance(c, FieldCondition) and c.key == "domain_tags" for c in must), (
        f"domain_tags FieldCondition missing from must; got must={must}"
    )
    # The types group is a nested Filter(should=[...]) inside must (from #323)
    assert any(hasattr(c, "should") and c.should for c in must), (
        f"types Filter(should=[...]) missing from must; got must={must}"
    )


# ---------------------------------------------------------------------------
# #336 — AC-IDX (version): PAYLOAD_SCHEMA_VERSION=3 forces full re-embed
# ---------------------------------------------------------------------------


def test_schema_version_3_bump_forces_full_reembed(monkeypatch, tmp_path):
    """#336 AC-IDX (version bump): stored version=2, PAYLOAD_SCHEMA_VERSION=3 →
    unchanged object STILL re-embedded; state stamped with version 3.
    """
    import anytype_llm_wiki.indexer as _indexer

    state = {"_payload_schema_version": 2, "sp-1": {"obj-1": "2026-01-01T00:00:00Z"}}
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps(state))
    monkeypatch.setattr(config, "INDEX_STATE_FILE", state_file)
    monkeypatch.setattr(config, "INDEX_STATE_DIR", tmp_path)
    monkeypatch.setattr(config, "PAYLOAD_SCHEMA_VERSION", 3)

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
        f"With schema v2→v3 bump, unchanged object MUST be re-indexed; stats={stats}"
    )
    assert fake.upserted_points, "Expected Qdrant upsert after forced v3 re-embed"
    new_state = json.loads(state_file.read_text())
    assert new_state["_payload_schema_version"] == 3, (
        f"State file must be stamped with PAYLOAD_SCHEMA_VERSION=3; got {new_state}"
    )


# ---------------------------------------------------------------------------
# #336 — AC-V-SS: Invalid source_type raises ValueError from semantic_search
# ---------------------------------------------------------------------------


def test_invalid_source_type_raises_value_error():
    """#336 AC-V-SS: source_type with an empty string raises ValueError from semantic_search."""
    import pytest as _pytest
    from anytype_llm_wiki.server import semantic_search

    with _pytest.raises(ValueError, match="source_type"):
        semantic_search(query="test", source_type=[""])  # empty string in list


def test_invalid_domain_tags_raises_value_error():
    """#336 AC-V-SS (domain_tags variant): domain_tags with an empty string raises ValueError."""
    import pytest as _pytest
    from anytype_llm_wiki.server import semantic_search

    with _pytest.raises(ValueError, match="domain_tags"):
        semantic_search(query="test", domain_tags=[""])  # empty string in list


# ---------------------------------------------------------------------------
# #336 — AC-V-ZERO: Unknown filter value → zero matches, no raise
# ---------------------------------------------------------------------------


def test_unknown_filter_value_yields_zero_no_raise(monkeypatch):
    """#336 AC-V-ZERO: structurally-valid but unknown filter value → empty result, no raise.

    The filter IS built (MatchAny with the unknown value) and Qdrant returns no
    matches — no exception. Pins the documented unknown-value→zero-match/no-raise
    behavior (D11/§14 — the typo footgun's only structural guarantee).
    """
    import anytype_llm_wiki.indexer as _indexer

    fake = FakeQdrantClientWithSearch(mock_results=[])
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(_indexer, "embed_query", lambda q: [0.1] * config.EMBED_DIMS)

    # structurally valid but semantically unknown domain tag
    result = _indexer.semantic_search_core(query="test", domain_tags=["nonexistent-domain-xyz"])
    assert result == [], (
        f"Unknown domain tag must return empty result, not raise; got {result}"
    )


# ---------------------------------------------------------------------------
# #336 — OD-B Option 2 default-semantics regression
# ---------------------------------------------------------------------------


def test_semantic_search_default_excludes_wiki_source(monkeypatch):
    """#336 OD-B Option 2: server.py:semantic_search with no 'types' param must default-exclude wiki_source.

    Per spec §11 Step 6, the OD-B guard lives in server.py:semantic_search — NOT in
    semantic_search_core. semantic_search_core must remain filter-free when called with no
    types (test_no_filter_regression guards that). This test targets the server.py seam by
    monkeypatching semantic_search_core in the server module's namespace and inspecting the
    `types` argument that server.semantic_search passes down.

    Pre-impl (current): semantic_search passes types=None straight to semantic_search_core.
    Post-impl (correct): semantic_search builds a default types list that omits wiki_source
    when no types= argument is provided, then passes that list to semantic_search_core.

    Two assertions:
    (a) DEFAULT call: captured types is not None AND "wiki_source" NOT in captured types.
    (b) EXPLICIT override: semantic_search(query="test", types=["wiki_source"]) passes
        ["wiki_source"] through unchanged (the caller's explicit intent overrides the default).

    RED now: captured types is None (server.py passes None as-is). GREEN after impl.
    test_no_filter_regression stays GREEN because that test calls semantic_search_core
    directly — the OD-B guard is in server.py, not in semantic_search_core.
    """
    import anytype_llm_wiki.server as _server_mod

    captured_calls: list[dict] = []

    def fake_core(query, space_id=None, types=None, ingested_after=None,
                  ingested_before=None, limit=10, **kwargs):
        captured_calls.append({"types": types, "query": query})
        return []

    monkeypatch.setattr(_server_mod, "semantic_search_core", fake_core)

    from anytype_llm_wiki.server import semantic_search

    # (a) DEFAULT call — no types= supplied
    captured_calls.clear()
    semantic_search(query="test")
    assert captured_calls, "semantic_search must call semantic_search_core"
    default_types = captured_calls[-1]["types"]

    assert default_types is not None, (
        "#336 OD-B FAIL: server.py:semantic_search must pass a non-None types list to "
        "semantic_search_core when no types= argument is given — the default must exclude "
        "wiki_source. Pre-impl: types=None is passed straight through (expected red)."
    )
    assert "wiki_source" not in default_types, (
        f"#336 OD-B FAIL: 'wiki_source' must NOT appear in the default types list. "
        f"Got default_types={default_types!r}. The default call must scope to the non-source "
        f"type set (wiki_entity, wiki_concept, etc.) and exclude wiki_source."
    )

    # (b) EXPLICIT override — caller passes types=["wiki_source"] → must be honoured as-is
    captured_calls.clear()
    semantic_search(query="test", types=["wiki_source"])
    assert captured_calls, "semantic_search must call semantic_search_core for explicit types too"
    explicit_types = captured_calls[-1]["types"]
    assert explicit_types is not None and "wiki_source" in explicit_types, (
        f"#336 OD-B FAIL: explicit types=['wiki_source'] must be passed through unchanged. "
        f"Got explicit_types={explicit_types!r}."
    )


# ---------------------------------------------------------------------------
# #336 — B2: PAYLOAD_SCHEMA_VERSION constant guard
# ---------------------------------------------------------------------------


def test_payload_schema_version_is_3():
    """#336 §12: PAYLOAD_SCHEMA_VERSION must be exactly 3 in config.py.

    test_schema_version_3_bump_forces_full_reembed monkeypatches the constant to 3
    to exercise the mechanic — but that does NOT gate the actual constant in config.py.
    An implementer who leaves PAYLOAD_SCHEMA_VERSION = 2 would pass the mechanic test
    but break the payload index compat. This guard fails until the constant is bumped.

    RED now (config has 2). GREEN after impl sets PAYLOAD_SCHEMA_VERSION = 3.
    """
    from anytype_llm_wiki import config as _config
    assert _config.PAYLOAD_SCHEMA_VERSION == 3, (
        f"PAYLOAD_SCHEMA_VERSION must be 3 after #336 (was 2 pre-impl); "
        f"got {_config.PAYLOAD_SCHEMA_VERSION}"
    )
