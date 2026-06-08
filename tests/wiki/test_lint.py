"""Tests for wiki/lint.py — wiki_lint v0.5.0 structural health check.

These tests FAIL until src/anytype_llm_wiki/wiki/lint.py is implemented.
Covers: AC1–AC16 (spec #286), 32 CI-mocked tests + 2 live smoke tests.

Wire-contract verified:
- WikiClient.search  → POST  /v1/spaces/{space_id}/search
- WikiClient.list_objects → GET /v1/spaces/{space_id}/objects
- WikiClient.list_properties → GET /v1/spaces/{space_id}/properties
- WikiClient.list_tags → GET /v1/spaces/{space_id}/properties/{property_id}/tags
- WikiClient.create_object → POST /v1/spaces/{space_id}/objects
- AnytypeReadClient.get_object → GET /v1/spaces/{space_id}/objects/{id}?format=md
"""

import json
import os
import pytest
import respx
import httpx
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call

# ---------------------------------------------------------------------------
# Constants (self-contained; mirror conftest.py values)
# ---------------------------------------------------------------------------

ANYTYPE_BASE = "http://127.0.0.1:31012"
FAKE_SPACE_ID = "space-lint-test-001"
FAKE_API_KEY = "test-lint-key"
FAKE_API_VERSION = "2025-11-08"


# ---------------------------------------------------------------------------
# Autouse env fixture — set Anytype env vars + valid ALDEIA_DIR for every test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def set_anytype_env(monkeypatch):
    """Set Anytype env vars and a valid ALDEIA_DIR (QA#30) for all tests."""
    monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
    monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
    # Point ALDEIA_DIR at the real .aldeia dir containing patch-decision.md so
    # QA#30 pre-check passes by default. Tests that test the failure path override this.
    repo_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    aldeia_dir = os.path.join(
        repo_root,
        ".aldeia",
        "140-wiki-library-module-port-llm-wiki-pattern-onto-any",
    )
    monkeypatch.setenv("ALDEIA_DIR", aldeia_dir)


# ---------------------------------------------------------------------------
# Canned response builders
# ---------------------------------------------------------------------------

def _schema_marker(version: str | None = None) -> dict:
    """Return the root 'Wiki' collection object used as the schema-version marker.

    ``_schema_version_from_objects`` requires name=='Wiki' AND type.key=='collection'
    (G4 guard).  This object is recognised as the schema marker but is NOT a wiki
    wiki_entity / wiki_concept / etc., so the check-battery's wiki-type filter will
    correctly exclude it from the per-object check loop.
    """
    if version is None:
        from anytype_llm_wiki.wiki.types_schema import WIKI_SCHEMA_VERSION
        version = WIKI_SCHEMA_VERSION
    return {
        "id": "coll-wiki-001",
        "name": "Wiki",
        "type": {"key": "collection"},
        "properties": [
            {"key": "wiki_schema_version", "text": version}
        ],
    }


def _schema_current_response():
    """Single-page list_objects response stamped with the live WIKI_SCHEMA_VERSION.

    Contains ONLY the schema marker (no wiki objects).  Used by schema pre-check
    tests that do not need wiki objects in the enumeration.  The QA#25 gate passes.
    """
    return {
        "data": [_schema_marker()],
        "pagination": {"has_more": False},
    }


def _schema_outdated_response():
    """list_objects with version older than code — triggers wiki_schema_outdated."""
    return {
        "data": [_schema_marker("0.0.1")],
        "pagination": {"has_more": False},
    }


def _schema_newer_response():
    """list_objects with version newer than code — triggers wiki_schema_newer warning."""
    return {
        "data": [_schema_marker("99.99.99")],
        "pagination": {"has_more": False},
    }


def _empty_list_response():
    return {"data": [], "pagination": {"has_more": False}}


def _paginated_response(objects: list[dict], has_more: bool = False) -> dict:
    return {"data": objects, "pagination": {"has_more": has_more}}


def _make_entity(
    object_id: str,
    name: str = "Test Entity",
    relations: list | None = None,
    backlinks: list | None = None,
    wiki_status: str | None = None,
    wiki_contradictions: list | None = None,
    wiki_last_reviewed: str | None = None,
    wiki_sources: list | None = None,
    description: str | None = None,
    last_modified: str | None = None,
) -> dict:
    """Build a wiki_entity object dict suitable for list_objects / get_object responses."""
    props = [
        {"key": "wiki_description", "text": description or f"Description of {name}."},
        {"key": "wiki_relations", "objects": relations or []},
    ]
    if wiki_status is not None:
        # id must match the resolved tag id from _make_tags_response (e.g. "tag-needs-review-id")
        props.append({"key": "wiki_status", "select": {"name": wiki_status, "id": f"tag-{wiki_status}-id"}})
    if wiki_contradictions is not None:
        props.append({"key": "wiki_contradictions", "objects": wiki_contradictions})
    if wiki_last_reviewed is not None:
        props.append({"key": "wiki_last_reviewed", "date": wiki_last_reviewed})
    if wiki_sources is not None:
        props.append({"key": "wiki_sources", "objects": wiki_sources})

    obj: dict = {
        "id": object_id,
        "name": name,
        "type": {"key": "wiki_entity"},
        "properties": props,
    }
    if backlinks is not None:
        obj["backlinks"] = backlinks
    if last_modified is not None:
        obj["last_modified_date"] = last_modified
    return obj


def _make_concept(
    object_id: str,
    name: str = "Test Concept",
    relations: list | None = None,
    backlinks: list | None = None,
    wiki_status: str | None = None,
    wiki_sources: list | None = None,
) -> dict:
    """Build a wiki_concept object dict."""
    props = [
        {"key": "wiki_description", "text": f"Description of {name}."},
        {"key": "wiki_related", "objects": relations or []},
    ]
    if wiki_status is not None:
        # id must match the resolved tag id from _make_tags_response (e.g. "tag-needs-review-id")
        props.append({"key": "wiki_status", "select": {"name": wiki_status, "id": f"tag-{wiki_status}-id"}})
    if wiki_sources is not None:
        props.append({"key": "wiki_sources", "objects": wiki_sources})

    obj: dict = {
        "id": object_id,
        "name": name,
        "type": {"key": "wiki_concept"},
        "properties": props,
    }
    if backlinks is not None:
        obj["backlinks"] = backlinks
    return obj


def _make_source(
    object_id: str,
    name: str = "Test Source",
    wiki_ingested_at: str | None = None,
) -> dict:
    """Build a wiki_source object dict with optional wiki_ingested_at timestamp."""
    props = []
    if wiki_ingested_at is not None:
        props.append({"key": "wiki_ingested_at", "date": wiki_ingested_at})
    return {
        "id": object_id,
        "name": name,
        "type": {"key": "wiki_source"},
        "properties": props,
    }


def _make_wikilog(
    object_id: str,
    wiki_action: str = "ingest",
    wiki_notes: str = "",
    wiki_timestamp: str | None = None,
) -> dict:
    """Build a wiki_log object dict."""
    props = [
        {"key": "wiki_action", "select": {"name": wiki_action, "id": f"tag-{wiki_action}"}},
        {"key": "wiki_notes", "text": wiki_notes},
    ]
    if wiki_timestamp:
        props.append({"key": "wiki_timestamp", "date": wiki_timestamp})
    return {
        "id": object_id,
        "name": f"WikiLog {object_id}",
        "type": {"key": "wiki_log"},
        "properties": props,
    }


def _make_get_object_envelope(obj: dict) -> dict:
    """Wrap an object dict in the get_object API response envelope."""
    return {"object": obj}


def _make_search_response(objects: list[dict]) -> dict:
    return {"data": objects, "pagination": {"has_more": False}}


def _make_properties_response() -> dict:
    """Return a mock list_properties response with wiki_status property."""
    return {
        "data": [
            {
                "id": "prop-wiki-status-001",
                "key": "wiki_status",
                "name": "Wiki Status",
            },
            {
                "id": "prop-wiki-action-001",
                "key": "wiki_action",
                "name": "Wiki Action",
            },
        ],
        "pagination": {"has_more": False},
    }


def _make_tags_response(property_id: str) -> dict:
    """Return mock tags for a property — covers needs-review, reviewed, archived, ingest, lint."""
    all_tags = [
        {"id": "tag-needs-review-id", "name": "needs-review", "propertyKey": "wiki_status"},
        {"id": "tag-reviewed-id", "name": "reviewed", "propertyKey": "wiki_status"},
        {"id": "tag-archived-id", "name": "archived", "propertyKey": "wiki_status"},
        {"id": "tag-ingest-id", "name": "ingest", "propertyKey": "wiki_action"},
        {"id": "tag-lint-id", "name": "lint", "propertyKey": "wiki_action"},
    ]
    return {"data": all_tags, "pagination": {"has_more": False}}


def _standard_mocks(objects=None, schema_version=None):
    """Return a ``(get_side_effect, register_object)`` pair for GET mocking.

    Handles:
    - list_objects  → ONE single-page enumeration containing [schema_marker, *objects]
                      (query.py pattern: single WikiClient.list_objects call returns
                       the schema-version marker collection AND all wiki objects in one
                       combined data[] array so _schema_version_from_objects and the
                       check battery both operate on the same list — spec Pre-Checks step
                       2 "one paginated list_objects sequence" / note G9).
    - list_properties → wiki_status + wiki_action properties
    - list_tags       → needs-review + ingest + lint tags (property-scoped two-step)
    - get_object      → individual object fetches (envelope), served from _cached_objects

    Parameters
    ----------
    objects:
        Wiki objects to include in the enumeration after the schema marker.
        Defaults to [] (empty space — schema check passes, zero wiki objects found).
    schema_version:
        Version string for the schema marker.  Defaults to the current
        WIKI_SCHEMA_VERSION so QA#25 passes.  Pass ``"0.0.1"`` to trigger the
        outdated branch or ``"99.99.99"`` for the newer branch *within a combined
        single-page response that also carries wiki objects*.

    Notes
    -----
    The schema marker object (type.key == "collection", name == "Wiki") is
    deliberately NOT a wiki_entity / wiki_concept / etc., so the check-battery's
    wiki-type filter will exclude it from per-object processing while
    _schema_version_from_objects will still find the version on the same list.
    """
    _wiki_objects = list(objects) if objects is not None else []
    _single_page = {
        "data": [_schema_marker(schema_version)] + _wiki_objects,
        "pagination": {"has_more": False},
    }

    _cached_objects: dict[str, dict] = {}

    def get_side_effect(request, **kwargs):
        url_str = str(request.url)
        path = request.url.path

        # list_properties
        if "/properties" in path and "/tags" not in path:
            return httpx.Response(200, json=_make_properties_response())

        # list_tags for a property (property-scoped two-step tag resolution)
        if "/properties/" in path and "/tags" in path:
            # Extract property_id from path like /v1/spaces/{sid}/properties/{pid}/tags
            parts = path.split("/")
            try:
                prop_idx = parts.index("properties")
                prop_id = parts[prop_idx + 1]
            except (ValueError, IndexError):
                prop_id = "unknown"
            return httpx.Response(200, json=_make_tags_response(prop_id))

        # get_object: /v1/spaces/{sid}/objects/{oid}?format=md
        # The "?" check is load-bearing: AnytypeReadClient.get_object always appends
        # ?format=md per the wire contract, distinguishing it from list_objects which
        # uses /objects (no trailing slash, no query string on the collection path).
        if "/objects/" in path and "?" in url_str:
            oid = path.rstrip("/").split("/")[-1]
            if oid in _cached_objects:
                return httpx.Response(200, json=_make_get_object_envelope(_cached_objects[oid]))
            # Return a minimal object if not pre-seeded
            return httpx.Response(200, json=_make_get_object_envelope(
                _make_entity(oid, name=f"Object {oid}")
            ))

        # list_objects: /v1/spaces/{sid}/objects?offset=...&limit=...
        # Returns a SINGLE page containing [schema_marker, *wiki_objects] with
        # has_more=False.  A spec-faithful single-call impl calls list_objects once,
        # _paginated_get fetches this one page, and both _schema_version_from_objects
        # and the check-battery filter operate on the same combined all_objects list
        # (mirrors query.py ~line 408 and test_query.py ~line 556).
        if "/objects" in path and "?" in url_str and "/objects/" not in path:
            return httpx.Response(200, json=_single_page)

        # space-level tags — MUST NOT be called (returns 404 to expose misuse)
        if path.endswith("/tags") and "/properties/" not in path:
            return httpx.Response(404, json={"error": "space-level tags endpoint not found"})

        return httpx.Response(200, json=_empty_list_response())

    def register_object(obj: dict):
        """Pre-seed an object so get_object returns a real envelope for it."""
        _cached_objects[obj["id"]] = obj

    return get_side_effect, register_object


# ---------------------------------------------------------------------------
# Section 1 — Import / callable
# ---------------------------------------------------------------------------

class TestWikiLintImport:
    """wiki_lint must be importable and callable."""

    def test_wiki_lint_importable(self):
        """wiki_lint must be importable from anytype_llm_wiki.wiki.lint."""
        from anytype_llm_wiki.wiki.lint import wiki_lint  # noqa: F401

    def test_wiki_lint_is_callable(self):
        from anytype_llm_wiki.wiki.lint import wiki_lint
        assert callable(wiki_lint)

    def test_wiki_lint_signature(self):
        """wiki_lint must accept space_id, severity_threshold, and include_duplicates."""
        import inspect
        from anytype_llm_wiki.wiki.lint import wiki_lint
        sig = inspect.signature(wiki_lint)
        params = list(sig.parameters.keys())
        assert "space_id" in params
        assert "severity_threshold" in params
        assert "include_duplicates" in params
        # Defaults
        assert sig.parameters["severity_threshold"].default == "all"
        assert sig.parameters["include_duplicates"].default is False


# ---------------------------------------------------------------------------
# Section 2 — Config resolvers (AC12 / Configuration section)
# ---------------------------------------------------------------------------

class TestLintConfigResolvers:
    """New lint config resolvers must exist with correct defaults."""

    def test_lint_config_importable(self):
        from anytype_llm_wiki.wiki.config import (  # noqa: F401
            lint_oversized_chars,
            lint_orphan_grace_days,
            lint_stale_needs_review_days,
            lint_max_objects,
            lint_pipeline_window_seconds,
            lint_duplicate_max_score,
        )

    def test_lint_oversized_chars_default(self, monkeypatch):
        monkeypatch.delenv("WIKI_LINT_OVERSIZED_CHARS", raising=False)
        from anytype_llm_wiki.wiki.config import lint_oversized_chars
        assert lint_oversized_chars() == 2000

    def test_lint_orphan_grace_days_default(self, monkeypatch):
        monkeypatch.delenv("WIKI_LINT_ORPHAN_GRACE_DAYS", raising=False)
        from anytype_llm_wiki.wiki.config import lint_orphan_grace_days
        assert lint_orphan_grace_days() == 7

    def test_lint_stale_needs_review_days_default(self, monkeypatch):
        monkeypatch.delenv("WIKI_LINT_STALE_NEEDS_REVIEW_DAYS", raising=False)
        from anytype_llm_wiki.wiki.config import lint_stale_needs_review_days
        assert lint_stale_needs_review_days() == 30

    def test_lint_max_objects_default(self, monkeypatch):
        monkeypatch.delenv("WIKI_LINT_MAX_OBJECTS", raising=False)
        from anytype_llm_wiki.wiki.config import lint_max_objects
        assert lint_max_objects() == 2000

    def test_lint_pipeline_window_seconds_default(self, monkeypatch):
        monkeypatch.delenv("WIKI_LINT_PIPELINE_WINDOW_SECONDS", raising=False)
        from anytype_llm_wiki.wiki.config import lint_pipeline_window_seconds
        assert lint_pipeline_window_seconds() == 300

    def test_lint_duplicate_max_score_default(self, monkeypatch):
        monkeypatch.delenv("WIKI_LINT_DUPLICATE_MAX_SCORE", raising=False)
        from anytype_llm_wiki.wiki.config import lint_duplicate_max_score
        assert lint_duplicate_max_score() == 0.85

    def test_bounded_float_rejects_out_of_range(self, monkeypatch):
        """_bounded_float guard: out-of-range [0,1] values fall back to default."""
        from anytype_llm_wiki.wiki.config import lint_duplicate_max_score
        monkeypatch.setenv("WIKI_LINT_DUPLICATE_MAX_SCORE", "1.5")
        assert lint_duplicate_max_score() == 0.85, "Value > 1.0 must fall back to default"
        monkeypatch.setenv("WIKI_LINT_DUPLICATE_MAX_SCORE", "-0.1")
        assert lint_duplicate_max_score() == 0.85, "Value < 0.0 must fall back to default"
        monkeypatch.setenv("WIKI_LINT_DUPLICATE_MAX_SCORE", "not_a_number")
        assert lint_duplicate_max_score() == 0.85, "Non-numeric must fall back to default"


# ---------------------------------------------------------------------------
# Section 3 — 32 CI-mocked backstop tests (spec Test Plan table)
# ---------------------------------------------------------------------------

class TestAsymmetricRelationCheck:
    """AC1/AC5: asymmetric_relation check — High severity (v0.7.2: was Critical;
    reranked below contradiction_unresolved, which is the user-visible defect)."""

    @respx.mock
    def test_asymmetric_relation_check_fires(self, monkeypatch):
        """Seed object A with wiki_relations=[B]; B has no reciprocal.
        backlinks is empty on A → fallback traversal fires → Critical finding.
        AC1/AC5/AC13.
        """
        obj_a = _make_entity("obj-a", name="Entity A", relations=["obj-b"], backlinks=[])
        obj_b = _make_entity("obj-b", name="Entity B", relations=[], backlinks=[])
        objects = [obj_a, obj_b]

        get_side_effect, register = _standard_mocks(
            objects=objects
        )
        register(obj_a)
        register(obj_b)

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint-log"}}))

        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=FAKE_SPACE_ID)

        findings = result.get("findings", [])
        asymmetric = [f for f in findings if f.get("check") == "asymmetric_relation"]
        assert len(asymmetric) >= 1, (
            f"Expected at least one asymmetric_relation finding; findings: {findings}"
        )
        assert asymmetric[0]["severity"] == "high", (
            f"asymmetric_relation must be High (v0.7.2); got {asymmetric[0]['severity']!r}"
        )

    @respx.mock
    def test_backlink_only_reverse_is_reciprocal(self, monkeypatch):
        """v0.7.2 regression (the 22-false-positive fix): a directed edge A->B
        written only on A's forward array is REACHABLE in reverse via the Anytype
        auto-backlink on B. Even though B has NO forward relation back to A, B's
        ``backlinks`` list contains A — so the edge is reciprocal and must NOT be
        flagged. This is the exact live-graph shape (e.g. Mac Mini M4 -> IronClaw)
        that the pre-v0.7.2 check false-flagged because it never read the target's
        backlinks.
        """
        # A -> B forward; B has no reverse FORWARD edge, but B.backlinks lists A
        # (Anytype's auto-reverse of the A->B write). A's own backlinks are empty.
        obj_a = _make_entity("obj-a", name="A", relations=["obj-b"], backlinks=[])
        obj_b = _make_entity("obj-b", name="B (hub)", relations=[], backlinks=["obj-a"])
        objects = [obj_a, obj_b]

        get_side_effect, register = _standard_mocks(objects=objects)
        register(obj_a)
        register(obj_b)

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}}))

        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=FAKE_SPACE_ID)

        asymmetric = [f for f in result.get("findings", []) if f.get("check") == "asymmetric_relation"]
        assert asymmetric == [], (
            "A backlink-reachable directed edge must NOT be flagged asymmetric; "
            f"got {asymmetric}"
        )

    @respx.mock
    def test_backlinks_in_properties_shape_is_reciprocal(self, monkeypatch):
        """Real-API shape guard (v0.7.2): live get_object serves backlinks as a
        PROPERTY (``properties[key='backlinks'].objects``) and leaves the top-level
        ``backlinks`` key ABSENT. A directed A->B whose reverse exists only as B's
        property-backlink must be recognized as reciprocal. Pre-v0.7.2,
        _backlinks_inbound read only the top-level key (None on the real API), so
        the backlink signal was dead and this false-flagged — the live-graph bug
        that fixtures (which used a top-level list) never exercised.
        """
        def ent(oid, name, relations, backlink_ids):
            return {
                "id": oid, "name": name, "type": {"key": "wiki_entity"},
                "properties": [
                    {"key": "wiki_description", "text": f"Description of {name}."},
                    {"key": "wiki_relations", "objects": relations},
                    {"key": "backlinks", "name": "Backlinks",
                     "format": "objects", "objects": backlink_ids},
                ],
                # Deliberately NO top-level "backlinks" key — mirrors the live API.
            }
        obj_a = ent("obj-a", "A", ["obj-b"], [])         # A -> B forward only
        obj_b = ent("obj-b", "B (hub)", [], ["obj-a"])   # reverse lives ONLY as B's property-backlink
        objects = [obj_a, obj_b]

        get_side_effect, register = _standard_mocks(objects=objects)
        register(obj_a)
        register(obj_b)

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}}))

        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=FAKE_SPACE_ID)

        asymmetric = [f for f in result.get("findings", []) if f.get("check") == "asymmetric_relation"]
        assert asymmetric == [], (
            "A property-shaped backlink must confirm reciprocity (the real-API shape); "
            f"got {asymmetric}"
        )

    @respx.mock
    def test_symmetric_relation_not_flagged_when_backlinks_polluted(self, monkeypatch):
        """Regression: a genuinely symmetric A<->B pair must NOT be flagged just
        because A's backlinks list is non-empty but happens to omit B.

        This reproduces the file-back citation-pollution case: provenance backlinks
        (e.g. query objects) crowd an entity's backlinks field, so the primary
        signal can't confirm a symmetric peer. The check must fall through to the
        symmetric-outbound signal rather than firing a false Critical.
        """
        # A->B and B->A are symmetric in wiki_relations, but A's backlinks lists
        # only an unrelated provenance object ("query-x"), not B.
        obj_a = _make_entity(
            "obj-a", name="Entity A", relations=["obj-b"], backlinks=["query-x"]
        )
        obj_b = _make_entity(
            "obj-b", name="Entity B", relations=["obj-a"], backlinks=["query-x"]
        )
        objects = [obj_a, obj_b]

        get_side_effect, register = _standard_mocks(objects=objects)
        register(obj_a)
        register(obj_b)

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(
            201, json={"object": {"id": "log-001", "name": "lint-log"}}
        ))

        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=FAKE_SPACE_ID)

        findings = result.get("findings", [])
        asymmetric = [f for f in findings if f.get("check") == "asymmetric_relation"]
        assert len(asymmetric) == 0, (
            f"A symmetric pair must not be flagged when backlinks omit the peer but "
            f"the symmetric outbound confirms reciprocity; got: {asymmetric}"
        )

    @respx.mock
    def test_asymmetric_still_fires_with_polluted_backlinks(self, monkeypatch):
        """False-negative guard for the OR-combine: a genuinely asymmetric edge
        whose source has a NON-empty backlinks list that omits the peer must still
        fire (backlinks present-but-incomplete must not suppress a real asymmetry).
        """
        # A -> B, but B has no outbound to A; A.backlinks is non-empty yet omits B.
        obj_a = _make_entity("obj-a", name="A", relations=["obj-b"], backlinks=["other-x"])
        obj_b = _make_entity("obj-b", name="B", relations=[], backlinks=["other-x"])
        objects = [obj_a, obj_b]

        get_side_effect, register = _standard_mocks(objects=objects)
        register(obj_a)
        register(obj_b)

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}}))

        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=FAKE_SPACE_ID)

        asymmetric = [f for f in result.get("findings", []) if f.get("check") == "asymmetric_relation"]
        assert any(f["object_id"] == "obj-a" and "obj-b" in f["detail"] for f in asymmetric), (
            f"A genuinely asymmetric A->B must still fire despite polluted backlinks; got {asymmetric}"
        )

    @respx.mock
    def test_stale_citation_edge_flagged_not_asymmetric(self, monkeypatch):
        """An entity whose wiki_relations points at a wiki_query object (a stale
        file-back citation edge) is flagged High `stale_citation_edge` and NOT
        double-reported as asymmetric_relation."""
        entity = _make_entity("obj-ent", name="Entity", relations=["q-1"], backlinks=[])
        query_obj = {
            "id": "q-1",
            "name": "Some question?",
            "type": {"key": "wiki_query"},
            "properties": [{"key": "wiki_answer", "text": "an answer"}],
            "backlinks": [],
        }
        objects = [entity, query_obj]

        get_side_effect, register = _standard_mocks(objects=objects)
        register(entity)
        register(query_obj)

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}}))

        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=FAKE_SPACE_ID)

        findings = result.get("findings", [])
        stale = [f for f in findings if f.get("check") == "stale_citation_edge"]
        asym = [
            f for f in findings
            if f.get("check") == "asymmetric_relation" and "q-1" in f.get("detail", "")
        ]
        assert len(stale) == 1, f"Expected one stale_citation_edge finding; got {findings}"
        assert stale[0]["severity"] == "high", stale[0]
        assert stale[0]["object_id"] == "obj-ent", stale[0]
        assert not asym, f"Stale citation edge must NOT also be flagged asymmetric; got {asym}"


    @respx.mock
    def test_new_file_back_shape_is_lint_clean(self, monkeypatch):
        """Integration guard (M5) for the original bug: the state the CURRENT
        wiki_query file-back produces — a Query object with wiki_drew_from -> entity,
        and the entity carrying only the auto-derived backlink (NO query id in its
        wiki_relations) — must yield ZERO asymmetric_relation and ZERO
        stale_citation_edge findings. Re-introducing the reverse write would put a
        query id back into wiki_relations and trip stale_citation_edge here."""
        entity = _make_entity("e-1", name="Cited Entity", relations=["e-2"], backlinks=["q-1", "e-2"])
        peer = _make_entity("e-2", name="Peer", relations=["e-1"], backlinks=["e-1"])
        query_obj = {
            "id": "q-1",
            "name": "What is the cited entity?",
            "type": {"key": "wiki_query"},
            "properties": [
                {"key": "wiki_answer", "text": "an answer"},
                {"key": "wiki_drew_from", "objects": ["e-1"]},
            ],
            "backlinks": [],
        }
        objects = [entity, peer, query_obj]

        get_side_effect, register = _standard_mocks(objects=objects)
        for o in objects:
            register(o)

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}}))

        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=FAKE_SPACE_ID)

        findings = result.get("findings", [])
        bad = [
            f for f in findings
            if f.get("check") in ("asymmetric_relation", "stale_citation_edge")
        ]
        assert not bad, (
            f"The current file-back shape must be lint-clean of asymmetric/stale "
            f"findings; got {bad}"
        )


class TestTitleDuplicateReason:
    """Unit tests for the embedding-independent title-duplicate heuristic."""

    def test_identical_title(self):
        from anytype_llm_wiki.wiki.lint import _title_duplicate_reason
        assert _title_duplicate_reason("axe dao", "axe dao") == "identical title"

    def test_token_subset_distinctive_flags(self):
        from anytype_llm_wiki.wiki.lint import _title_duplicate_reason
        assert _title_duplicate_reason("axe", "axe token") is not None

    def test_token_subset_stopword_only_does_not_flag(self):
        from anytype_llm_wiki.wiki.lint import _title_duplicate_reason
        # "the" carries no distinctive token → suppressed as noise.
        assert _title_duplicate_reason("the", "the project") is None

    def test_partial_overlap_does_not_flag(self):
        from anytype_llm_wiki.wiki.lint import _title_duplicate_reason
        # Neither is a subset of the other.
        assert _title_duplicate_reason("axe token", "axe coin") is None

    def test_empty_titles(self):
        from anytype_llm_wiki.wiki.lint import _title_duplicate_reason
        assert _title_duplicate_reason("", "axe") is None
        assert _title_duplicate_reason("axe", "") is None


class TestBacklinksD1:
    """AC1: D1 backlinks primary path and fallback behavior."""

    @respx.mock
    def test_backlinks_primary_no_traversal(self, monkeypatch):
        """Object A with backlinks=["B"] in get_object response — primary path used,
        no O(N) fallback traversal for inbound counts (AC1).

        We verify: when backlinks is non-empty on object A, asymmetric_relation does
        NOT fire for A based on inbound count alone. The traversal fallback is NOT entered
        because backlinks data is authoritative.
        """
        # A→B (outbound). B has backlinks=["obj-a"] meaning A→B is reciprocated.
        obj_a = _make_entity("obj-a", name="Entity A", relations=["obj-b"], backlinks=["obj-b"])
        obj_b = _make_entity("obj-b", name="Entity B", relations=["obj-a"], backlinks=["obj-a"])
        objects = [obj_a, obj_b]

        traversal_called = {"count": 0}
        original_list_objects = None

        get_side_effect, register = _standard_mocks(
            objects=objects
        )
        register(obj_a)
        register(obj_b)

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}}))

        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=FAKE_SPACE_ID)

        # With proper backlinks, no asymmetric_relation should fire for this pair
        findings = result.get("findings", [])
        asymmetric = [f for f in findings if f.get("check") == "asymmetric_relation"]
        assert len(asymmetric) == 0, (
            f"With backlinks populated on both sides, no asymmetric_relation should fire; "
            f"got: {asymmetric}"
        )

    @respx.mock
    def test_backlinks_malformed_falls_back(self, monkeypatch):
        """backlinks present but non-list (null, dict, scalar) → treated as absent,
        fallback traversal runs, no exception raised (SF10 / AC1).
        """
        # Provide three entities each with malformed backlinks; relations are symmetric
        # so no asymmetric_relation fires; the test just verifies no exception is raised.
        obj_a = _make_entity("obj-x1", name="X1", relations=["obj-x2"])
        obj_a["backlinks"] = None  # null / absent
        obj_b = _make_entity("obj-x2", name="X2", relations=["obj-x1"])
        obj_b["backlinks"] = {"invalid": "dict"}  # dict
        obj_c = _make_entity("obj-x3", name="X3", relations=[])
        obj_c["backlinks"] = 42  # scalar

        objects = [obj_a, obj_b, obj_c]
        get_side_effect, register = _standard_mocks(
            objects=objects
        )
        register(obj_a)
        register(obj_b)
        register(obj_c)

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}}))

        from anytype_llm_wiki.wiki.lint import wiki_lint
        # Must not raise — malformed backlinks fall back gracefully
        result = wiki_lint(space_id=FAKE_SPACE_ID)
        assert isinstance(result, dict), "wiki_lint must return a dict even with malformed backlinks"
        # Status must not be "error" (the malformed field shouldn't abort the run)
        assert result.get("status") in ("ok", "partial"), (
            f"Malformed backlinks must not abort the run; status={result.get('status')!r}"
        )


class TestPipelineOrphanCheck:
    """AC5: pipeline_orphan check — High severity."""

    @respx.mock
    def test_pipeline_orphan_check_fires(self, monkeypatch):
        """WikiLog with wiki_action=ingest and wiki_notes containing 'relation_rollback'
        near timestamp of a zero-relation object → finding check='pipeline_orphan', High.
        AC5/AC13.
        """
        from freezegun import freeze_time

        now_str = "2026-06-05T12:00:00+00:00"
        # WikiLog timestamp 60s before "now" — within 300s window
        log_ts = "2026-06-05T11:59:00+00:00"
        # Entity timestamp matches the WikiLog window
        entity_ts = "2026-06-05T11:59:30+00:00"

        failed_log = _make_wikilog(
            "wikilog-failed-001",
            wiki_action="ingest",
            wiki_notes="relation_rollback: entity not linked",
            wiki_timestamp=log_ts,
        )
        orphan_obj = _make_entity(
            "obj-pipeline-orphan",
            name="Orphan Entity",
            relations=[],
            backlinks=[],
        )
        # Add creation timestamp to orphan
        orphan_obj["created_date"] = entity_ts

        objects = [orphan_obj]

        get_side_effect, register = _standard_mocks(
            objects=objects
        )
        register(orphan_obj)

        def post_side_effect(request, **kwargs):
            try:
                payload = json.loads(request.content)
            except Exception:
                payload = {}
            if payload.get("type_key") == "wiki_log":
                return httpx.Response(201, json={"object": {"id": "log-new", "name": "lint-log"}})
            # search POST (WikiLog cross-ref)
            return httpx.Response(200, json=_make_search_response([failed_log]))

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(side_effect=post_side_effect)

        with freeze_time(now_str):
            from anytype_llm_wiki.wiki.lint import wiki_lint
            result = wiki_lint(space_id=FAKE_SPACE_ID)

        findings = result.get("findings", [])
        pipeline_orphan = [f for f in findings if f.get("check") == "pipeline_orphan"]
        assert len(pipeline_orphan) >= 1, (
            f"Expected pipeline_orphan finding; findings: {findings}"
        )
        assert pipeline_orphan[0]["severity"] == "high", (
            f"pipeline_orphan must be High; got {pipeline_orphan[0]['severity']!r}"
        )


class TestOrphanCheck:
    """AC1/AC5: orphan check — High severity with 7-day grace period (SF5)."""

    @respx.mock
    def test_orphan_check_fires_after_grace(self, monkeypatch):
        """Object with zero relations/backlinks whose linked wiki_source.wiki_ingested_at
        is > 7 days old → finding check='orphan', High.

        Age is seeded on the LINKED wiki_source (via wiki_sources), NOT on the entity
        itself (SF5/ADV-3). The entity carries no wiki_ingested_at.
        """
        from freezegun import freeze_time

        now_str = "2026-06-05T12:00:00+00:00"
        old_ts = "2026-05-28T12:00:00+00:00"  # 8 days old — past 7-day grace

        source_obj = _make_source("src-001", wiki_ingested_at=old_ts)
        orphan = _make_entity(
            "obj-orphan",
            name="Old Orphan",
            relations=[],
            backlinks=[],
            wiki_sources=["src-001"],
        )

        objects = [orphan]
        get_side_effect, register = _standard_mocks(
            objects=objects
        )
        register(orphan)
        register(source_obj)

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}}))

        with freeze_time(now_str):
            from anytype_llm_wiki.wiki.lint import wiki_lint
            result = wiki_lint(space_id=FAKE_SPACE_ID)

        findings = result.get("findings", [])
        orphan_findings = [f for f in findings if f.get("check") == "orphan"]
        assert len(orphan_findings) >= 1, (
            f"Expected orphan finding for object with source age > 7d; findings: {findings}"
        )
        assert orphan_findings[0]["severity"] == "high", (
            f"orphan must be High; got {orphan_findings[0]['severity']!r}"
        )

    @respx.mock
    def test_orphan_check_suppressed_within_grace(self, monkeypatch):
        """Object with zero relations/backlinks whose linked wiki_source.wiki_ingested_at
        is < 7 days old → NO orphan finding (within grace period).

        Age seeded on linked wiki_source, NOT on the entity itself (SF5).
        """
        from freezegun import freeze_time

        now_str = "2026-06-05T12:00:00+00:00"
        recent_ts = "2026-06-02T12:00:00+00:00"  # 3 days old — within 7-day grace

        source_obj = _make_source("src-002", wiki_ingested_at=recent_ts)
        new_orphan = _make_entity(
            "obj-new-orphan",
            name="New Orphan",
            relations=[],
            backlinks=[],
            wiki_sources=["src-002"],
        )

        objects = [new_orphan]
        get_side_effect, register = _standard_mocks(
            objects=objects
        )
        register(new_orphan)
        register(source_obj)

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}}))

        with freeze_time(now_str):
            from anytype_llm_wiki.wiki.lint import wiki_lint
            result = wiki_lint(space_id=FAKE_SPACE_ID)

        findings = result.get("findings", [])
        orphan_findings = [f for f in findings if f.get("check") == "orphan"]
        assert len(orphan_findings) == 0, (
            f"Orphan check must be suppressed within grace period; got: {orphan_findings}"
        )


class TestNeedsReviewChecks:
    """AC2/AC3/AC4/AC5: unreviewed_needs_review (High) and stale_needs_review (Medium)."""

    @respx.mock
    def test_unreviewed_needs_review_fires(self, monkeypatch):
        """wiki_entity with wiki_status=needs-review (any age) → finding
        check='unreviewed_needs_review', High (AC3/AC5).
        """
        entity = _make_entity(
            "obj-needs-review",
            name="Needs Review Entity",
            relations=["obj-other"],
            backlinks=["obj-other"],
            wiki_status="needs-review",
        )
        other = _make_entity("obj-other", name="Other", relations=["obj-needs-review"],
                             backlinks=["obj-needs-review"])
        objects = [entity, other]

        get_side_effect, register = _standard_mocks(
            objects=objects
        )
        register(entity)
        register(other)

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}}))

        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=FAKE_SPACE_ID)

        findings = result.get("findings", [])
        unreviewed = [f for f in findings if f.get("check") == "unreviewed_needs_review"]
        assert len(unreviewed) >= 1, (
            f"Expected unreviewed_needs_review finding; findings: {findings}"
        )
        assert unreviewed[0]["severity"] == "high", (
            f"unreviewed_needs_review must be High; got {unreviewed[0]['severity']!r}"
        )

    @respx.mock
    def test_stale_needs_review_fires(self, monkeypatch):
        """wiki_entity with wiki_status=needs-review AND linked source age > 30d →
        finding check='stale_needs_review', Medium.

        Age seeded on linked wiki_source (wiki_ingested_at), NOT on entity itself (SF5/ADV-3).
        """
        from freezegun import freeze_time

        now_str = "2026-06-05T12:00:00+00:00"
        old_ts = "2026-04-15T12:00:00+00:00"  # 51 days old — past 30-day cutoff

        source_obj = _make_source("src-stale-001", wiki_ingested_at=old_ts)
        entity = _make_entity(
            "obj-stale-needs-review",
            name="Stale Needs Review Entity",
            relations=["obj-other"],
            backlinks=["obj-other"],
            wiki_status="needs-review",
            wiki_sources=["src-stale-001"],
        )
        other = _make_entity("obj-other2", name="Other2",
                             relations=["obj-stale-needs-review"],
                             backlinks=["obj-stale-needs-review"])
        objects = [entity, other]

        get_side_effect, register = _standard_mocks(
            objects=objects
        )
        register(entity)
        register(other)
        register(source_obj)

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}}))

        with freeze_time(now_str):
            from anytype_llm_wiki.wiki.lint import wiki_lint
            result = wiki_lint(space_id=FAKE_SPACE_ID)

        findings = result.get("findings", [])
        stale_nr = [f for f in findings if f.get("check") == "stale_needs_review"]
        assert len(stale_nr) >= 1, (
            f"Expected stale_needs_review finding; findings: {findings}"
        )
        assert stale_nr[0]["severity"] == "medium", (
            f"stale_needs_review must be Medium; got {stale_nr[0]['severity']!r}"
        )

    @respx.mock
    def test_both_needs_review_checks_fire_on_aged_object(self, monkeypatch):
        """Aged needs-review object fires BOTH unreviewed_needs_review (High)
        AND stale_needs_review (Medium); both appear in findings[] and summary counts each.
        AC4/AC5 double-count rule.
        """
        from freezegun import freeze_time

        now_str = "2026-06-05T12:00:00+00:00"
        old_ts = "2026-04-01T12:00:00+00:00"  # 65 days — past both 7d orphan AND 30d stale grace

        source_obj = _make_source("src-double-001", wiki_ingested_at=old_ts)
        entity = _make_entity(
            "obj-double",
            name="Double Finding Entity",
            relations=["obj-ref"],
            backlinks=["obj-ref"],
            wiki_status="needs-review",
            wiki_sources=["src-double-001"],
        )
        ref = _make_entity("obj-ref", name="Ref", relations=["obj-double"],
                           backlinks=["obj-double"])
        objects = [entity, ref]

        get_side_effect, register = _standard_mocks(
            objects=objects
        )
        register(entity)
        register(ref)
        register(source_obj)

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}}))

        with freeze_time(now_str):
            from anytype_llm_wiki.wiki.lint import wiki_lint
            result = wiki_lint(space_id=FAKE_SPACE_ID)

        findings = result.get("findings", [])
        summary = result.get("summary", {})
        unreviewed = [f for f in findings if f.get("check") == "unreviewed_needs_review"]
        stale_nr = [f for f in findings if f.get("check") == "stale_needs_review"]

        assert len(unreviewed) >= 1, (
            f"Expected unreviewed_needs_review finding in double-count scenario; findings: {findings}"
        )
        assert len(stale_nr) >= 1, (
            f"Expected stale_needs_review finding in double-count scenario; findings: {findings}"
        )
        assert summary.get("high", 0) >= 1, (
            f"summary['high'] must count unreviewed_needs_review; summary: {summary}"
        )
        assert summary.get("medium", 0) >= 1, (
            f"summary['medium'] must count stale_needs_review; summary: {summary}"
        )

    @respx.mock
    def test_stale_stub_check_never_emitted(self, monkeypatch):
        """Full lint run with needs-review / reviewed / archived status values;
        assert no finding with check='stale_stub' is ever emitted (D2/AC2).
        """
        entity_nr = _make_entity("obj-nr", name="NR", relations=["obj-rv"],
                                 backlinks=["obj-rv"], wiki_status="needs-review")
        entity_rv = _make_entity("obj-rv", name="RV", relations=["obj-nr"],
                                 backlinks=["obj-nr"], wiki_status="reviewed")
        entity_ar = _make_entity("obj-ar", name="AR", relations=[], backlinks=[],
                                 wiki_status="archived")
        objects = [entity_nr, entity_rv, entity_ar]

        get_side_effect, register = _standard_mocks(
            objects=objects
        )
        for o in objects:
            register(o)

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}}))

        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=FAKE_SPACE_ID)

        findings = result.get("findings", [])
        stale_stub = [f for f in findings if f.get("check") == "stale_stub"]
        assert len(stale_stub) == 0, (
            f"stale_stub check must never be emitted (D2); got: {stale_stub}"
        )


class TestContradictionCheck:
    """AC3/AC4: contradiction_unresolved check — Critical severity (v0.7.2: reranked
    from High so semantic conflicts outrank structural checks), ACTIVE post-v0.6.0."""

    @respx.mock
    def test_contradiction_check_active(self, monkeypatch):
        """AC3: contradiction_unresolved fires as High finding with NO passive caveat in detail.

        v0.6.0 activates the contradiction check: lint.py removes the
        _PASSIVE_CONTRADICTION_NOTE constant and "(PASSIVE check — see #287)" suffix.
        This test FAILS until lint.py:429 strips the passive suffix (§3.7 change 3).

        Assertions:
          - finding fires for entity with wiki_contradictions set + null wiki_last_reviewed
          - finding severity == "high"
          - finding detail does NOT contain "PASSIVE" (new — FAILS now because current
            lint.py:429 appends "(PASSIVE check — see #287)")
          - report["notes"] does NOT contain the _PASSIVE_CONTRADICTION_NOTE string
        """
        # Pipeline-normal entity: no contradictions
        normal_entity = _make_entity(
            "obj-normal",
            name="Normal Entity",
            relations=["obj-conflict"],
            backlinks=["obj-conflict"],
            wiki_contradictions=[],
        )
        # Entity with contradictions set (as the pipeline now writes) and no last_reviewed
        conflict_entity = _make_entity(
            "obj-conflict",
            name="Conflict Entity",
            relations=["obj-normal"],
            backlinks=["obj-normal"],
            wiki_contradictions=["obj-ref-contradiction"],
            wiki_last_reviewed=None,
        )
        objects = [normal_entity, conflict_entity]

        get_side_effect, register = _standard_mocks(
            objects=objects
        )
        for o in objects:
            register(o)

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}}))

        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=FAKE_SPACE_ID)

        findings = result.get("findings", [])
        contradictions = [f for f in findings if f.get("check") == "contradiction_unresolved"]

        # Finding fires for conflict entity
        assert any(f.get("object_id") == "obj-conflict" for f in contradictions), (
            f"Expected contradiction_unresolved for obj-conflict; findings: {contradictions}"
        )
        # v0.7.2: severity reranked to Critical (above structural checks like
        # asymmetric_relation, which is High).
        assert all(f.get("severity") == "critical" for f in contradictions), (
            f"contradiction_unresolved must be Critical (v0.7.2); got "
            f"{[f.get('severity') for f in contradictions]}"
        )
        # Normal entity (no contradictions) does not fire
        assert not any(f.get("object_id") == "obj-normal" for f in contradictions), (
            f"Normal entity must not fire contradiction_unresolved; findings: {contradictions}"
        )

        # AC3 new assertion: finding detail must NOT contain "PASSIVE" — FAILS until
        # lint.py:429 is updated (§3.7 change 3).
        for finding in contradictions:
            detail = finding.get("detail", "")
            assert "PASSIVE" not in detail, (
                f"AC3: contradiction_unresolved detail must NOT contain 'PASSIVE' after v0.6.0 "
                f"activation (§3.7 change 3); got detail={detail!r}"
            )

        # AC3 new assertion: report notes must NOT carry the passive-note string
        notes = result.get("notes", [])
        assert not any("passive until v0.6.0" in str(n) for n in notes), (
            f"AC3: report notes must NOT contain passive-note string post-v0.6.0; notes: {notes}"
        )

    @respx.mock
    def test_contradiction_cleared_by_review(self, monkeypatch):
        """AC4: entity with wiki_contradictions set AND wiki_last_reviewed non-null
        → contradiction_unresolved finding does NOT fire.

        The predicate is (contradictions AND NOT last_reviewed). Setting
        wiki_last_reviewed suppresses the finding — operator marks it resolved.
        """
        reviewed_entity = _make_entity(
            "obj-reviewed",
            name="Reviewed Contradiction Entity",
            relations=["obj-peer"],
            backlinks=["obj-peer"],
            wiki_contradictions=["obj-peer"],
            wiki_last_reviewed="2026-06-05T00:00:00+00:00",
        )
        peer = _make_entity(
            "obj-peer",
            name="Peer Entity",
            relations=["obj-reviewed"],
            backlinks=["obj-reviewed"],
        )
        objects = [reviewed_entity, peer]

        get_side_effect, register = _standard_mocks(objects=objects)
        for o in objects:
            register(o)

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}}))

        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=FAKE_SPACE_ID)

        findings = result.get("findings", [])
        contradictions = [f for f in findings if f.get("check") == "contradiction_unresolved"]

        assert not any(f.get("object_id") == "obj-reviewed" for f in contradictions), (
            f"AC4: contradiction_unresolved must NOT fire when wiki_last_reviewed is set; "
            f"findings: {contradictions}"
        )


class TestStaleCheck:
    """AC5: stale check — Medium severity (SF5 age derivation)."""

    @respx.mock
    def test_stale_check_fires(self, monkeypatch):
        """Entity whose linked wiki_source has wiki_ingested_at such that
        last_modified < source.wiki_ingested_at - 90d → finding check='stale', Medium.

        Age seeded on linked wiki_source (SF5/ADV-3).
        """
        from freezegun import freeze_time

        now_str = "2026-06-05T12:00:00+00:00"
        # Source ingested 200 days ago; entity last modified 150 days ago
        # → last_modified (150d ago) < source_ingested_at (200d ago) - 90d
        # → 2026-06-05 - 150d = 2025-12-07  vs  2026-06-05 - 200d = 2025-11-17 - 90d = 2025-08-19
        # stale fires when: last_modified < (source_ingested_at - 90d)
        source_ingested_at = "2025-11-17T12:00:00+00:00"  # ~200d ago
        entity_last_modified = "2025-12-07T12:00:00+00:00"  # ~150d ago

        # Checking: entity_last_modified (2025-12-07) < source_ingested_at (2025-11-17) - 90d?
        # source_ingested_at - 90d = 2025-08-19
        # 2025-12-07 > 2025-08-19, so stale would NOT fire with this data.
        # Correct fixture: entity_last_modified < source_ingested_at - 90d
        # source_ingested_at = 2025-11-17; source_ingested_at - 90d = 2025-08-19
        # entity_last_modified must be < 2025-08-19, e.g. 2025-07-01
        source_ingested_at = "2025-11-17T12:00:00+00:00"
        entity_last_modified = "2025-07-01T12:00:00+00:00"  # < source_ingested_at - 90d

        source_obj = _make_source("src-stale-check", wiki_ingested_at=source_ingested_at)
        stale_entity = _make_entity(
            "obj-stale-entity",
            name="Stale Entity",
            relations=["obj-ref-stale"],
            backlinks=["obj-ref-stale"],
            wiki_sources=["src-stale-check"],
            last_modified=entity_last_modified,
        )
        ref = _make_entity("obj-ref-stale", name="Ref Stale",
                           relations=["obj-stale-entity"],
                           backlinks=["obj-stale-entity"])
        objects = [stale_entity, ref]

        get_side_effect, register = _standard_mocks(
            objects=objects
        )
        register(stale_entity)
        register(ref)
        register(source_obj)

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}}))

        with freeze_time(now_str):
            from anytype_llm_wiki.wiki.lint import wiki_lint
            result = wiki_lint(space_id=FAKE_SPACE_ID)

        findings = result.get("findings", [])
        stale_findings = [f for f in findings if f.get("check") == "stale"]
        assert len(stale_findings) >= 1, (
            f"Expected stale finding; findings: {findings}"
        )
        assert stale_findings[0]["severity"] == "medium", (
            f"stale must be Medium; got {stale_findings[0]['severity']!r}"
        )


class TestOversizedCheck:
    """AC5: oversized check — Low severity, char-count summary in detail (SF12)."""

    @respx.mock
    def test_oversized_check_fires(self, monkeypatch):
        """Description > 2000 chars → finding check='oversized', Low.
        Detail must be a char-count summary, not the raw body (SF12).
        """
        long_description = "X" * 3140
        oversized_entity = _make_entity(
            "obj-oversized",
            name="Oversized Entity",
            relations=["obj-ref-ov"],
            backlinks=["obj-ref-ov"],
            description=long_description,
        )
        ref = _make_entity("obj-ref-ov", name="Ref OV",
                           relations=["obj-oversized"],
                           backlinks=["obj-oversized"])
        objects = [oversized_entity, ref]

        get_side_effect, register = _standard_mocks(
            objects=objects
        )
        register(oversized_entity)
        register(ref)

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}}))

        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=FAKE_SPACE_ID)

        findings = result.get("findings", [])
        oversized = [f for f in findings if f.get("check") == "oversized"]
        assert len(oversized) >= 1, (
            f"Expected oversized finding; findings: {findings}"
        )
        assert oversized[0]["severity"] == "low", (
            f"oversized must be Low; got {oversized[0]['severity']!r}"
        )
        # Detail must be char-count summary, not the raw oversized body (SF12)
        detail = oversized[0].get("detail", "")
        assert "3140" in detail, (
            f"detail must contain char count 3140; got: {detail!r}"
        )
        assert long_description[:100] not in detail, (
            f"detail must NOT contain the raw oversized body; got: {detail!r}"
        )


class TestEmptyTypeCheck:
    """AC5: empty_type check — Informational severity."""

    @respx.mock
    def test_empty_type_check_fires(self, monkeypatch):
        """Space with zero wiki_concept objects → finding check='empty_type',
        severity Informational (visible only under severity_threshold='all').
        """
        # Only provide wiki_entity objects — wiki_concept count will be 0
        entity = _make_entity("obj-entity-only", name="Entity Only",
                              relations=[], backlinks=[])
        objects = [entity]

        get_side_effect, register = _standard_mocks(
            objects=objects
        )
        register(entity)

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}}))

        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=FAKE_SPACE_ID, severity_threshold="all")

        findings = result.get("findings", [])
        empty_type = [f for f in findings if f.get("check") == "empty_type"]
        assert len(empty_type) >= 1, (
            f"Expected empty_type finding when wiki_concept count=0; findings: {findings}"
        )
        assert empty_type[0]["severity"] == "informational", (
            f"empty_type must be Informational; got {empty_type[0]['severity']!r}"
        )


class TestDuplicateSweep:
    """AC8/AC16: duplicate sweep — Informational, opt-in only (CA-B1)."""

    @respx.mock
    def test_duplicate_sweep_fires_when_opted_in(self, monkeypatch):
        """semantic_search_core monkeypatched to return candidate with score 0.75
        (in [0.70, 0.85) band); include_duplicates=True → one entry in potential_duplicates[].
        AC8.
        """
        entity_a = _make_entity("obj-dup-a", name="Entity A Dup",
                                relations=[], backlinks=[])
        entity_b = _make_entity("obj-dup-b", name="Entity B Dup",
                                relations=[], backlinks=[])
        objects = [entity_a, entity_b]

        get_side_effect, register = _standard_mocks(
            objects=objects
        )
        register(entity_a)
        register(entity_b)

        def fake_semantic_search_core(query, space_id, types, limit=5):
            # Return entity_b as a candidate when called for entity_a's text
            return [
                {
                    "object_id": "obj-dup-b",
                    "type": "wiki_entity",
                    "score": 0.75,
                    "name": "Entity B Dup",
                }
            ]

        import anytype_llm_wiki.indexer as _idx_mod
        monkeypatch.setattr(_idx_mod, "semantic_search_core", fake_semantic_search_core)

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}}))

        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=FAKE_SPACE_ID, include_duplicates=True)

        potential_dups = result.get("potential_duplicates", [])
        assert len(potential_dups) >= 1, (
            f"Expected at least one potential_duplicate entry; got: {potential_dups}"
        )
        assert potential_dups[0]["similarity_score"] == 0.75, (
            f"Expected similarity_score=0.75; got {potential_dups[0]['similarity_score']!r}"
        )

    @respx.mock
    def test_title_duplicate_cross_kind_identical(self, monkeypatch):
        """Title-based pass flags an entity and a concept that share a normalized
        title — the cross-kind twin that type-scoped resolution never merges."""
        entity = _make_entity("obj-reg-entity", name="Capoeira Genealogy Registry",
                              relations=[], backlinks=[])
        concept = _make_concept("obj-reg-concept", name="capoeira genealogy registry",
                               relations=[], backlinks=[])
        objects = [entity, concept]

        get_side_effect, register = _standard_mocks(objects=objects)
        register(entity)
        register(concept)

        import anytype_llm_wiki.indexer as _idx_mod
        monkeypatch.setattr(
            _idx_mod, "semantic_search_core",
            lambda *a, **k: [],  # isolate the title-based pass from the vector pass
        )
        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}}))

        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=FAKE_SPACE_ID, include_duplicates=True)

        dups = result.get("potential_duplicates", [])
        pair = {"obj-reg-entity", "obj-reg-concept"}
        assert any({d["object_a"], d["object_b"]} == pair for d in dups), (
            f"Cross-kind identical-title twin must be flagged; got {dups}"
        )

    @respx.mock
    def test_title_duplicate_token_subset(self, monkeypatch):
        """Title-based pass flags 'AXE' vs 'AXE token' (abbreviation/expansion) —
        the false-negative the 0.92 fuzzy threshold and the vector sweep missed."""
        a = _make_entity("obj-axe", name="AXE", relations=[], backlinks=[])
        b = _make_entity("obj-axe-token", name="AXE token", relations=[], backlinks=[])
        objects = [a, b]

        get_side_effect, register = _standard_mocks(objects=objects)
        register(a)
        register(b)

        import anytype_llm_wiki.indexer as _idx_mod
        monkeypatch.setattr(_idx_mod, "semantic_search_core", lambda *a, **k: [])
        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}}))

        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=FAKE_SPACE_ID, include_duplicates=True)

        dups = result.get("potential_duplicates", [])
        pair = {"obj-axe", "obj-axe-token"}
        assert any({d["object_a"], d["object_b"]} == pair for d in dups), (
            f"Token-subset duplicate must be flagged; got {dups}"
        )

    @respx.mock
    def test_query_objects_excluded_from_duplicate_sweep(self, monkeypatch):
        """A wiki_query object that shares a title with an entity must NOT be
        flagged as a duplicate — Query objects are Q&A artifacts, not subjects."""
        entity = _make_entity("obj-foo", name="Foo", relations=[], backlinks=[])
        query_obj = {
            "id": "obj-foo-query",
            "name": "Foo",
            "type": {"key": "wiki_query"},
            "properties": [{"key": "wiki_answer", "text": "An answer mentioning Foo."}],
            "backlinks": [],
        }
        objects = [entity, query_obj]

        get_side_effect, register = _standard_mocks(objects=objects)
        register(entity)
        register(query_obj)

        import anytype_llm_wiki.indexer as _idx_mod
        # Even if the vector backend returned the query as a candidate, the scoped
        # sweep must exclude it. Return it to prove exclusion is by type, not luck.
        monkeypatch.setattr(
            _idx_mod, "semantic_search_core",
            lambda *a, **k: [{"object_id": "obj-foo-query", "type": "wiki_query",
                              "score": 0.78, "name": "Foo"}],
        )
        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}}))

        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=FAKE_SPACE_ID, include_duplicates=True)

        dups = result.get("potential_duplicates", [])
        assert not any(
            "obj-foo-query" in (d["object_a"], d["object_b"]) for d in dups
        ), f"Query objects must be excluded from the duplicate sweep; got {dups}"

    @respx.mock
    def test_duplicate_sweep_excludes_outside_band(self, monkeypatch):
        """include_duplicates=True; score 0.60 (below floor) and 0.95 (>= 0.85 upper bound)
        both excluded from potential_duplicates[]. AC8.
        """
        entity_a = _make_entity("obj-band-a", name="Band Entity A", relations=[], backlinks=[])
        entity_b = _make_entity("obj-band-b", name="Band Entity B", relations=[], backlinks=[])
        entity_c = _make_entity("obj-band-c", name="Band Entity C", relations=[], backlinks=[])
        objects = [entity_a, entity_b, entity_c]

        get_side_effect, register = _standard_mocks(
            objects=objects
        )
        for o in objects:
            register(o)

        def fake_semantic_search_core(query, space_id, types, limit=5):
            return [
                {"object_id": "obj-band-b", "type": "wiki_entity", "score": 0.60, "name": "B"},
                {"object_id": "obj-band-c", "type": "wiki_entity", "score": 0.95, "name": "C"},
            ]

        import anytype_llm_wiki.indexer as _idx_mod
        monkeypatch.setattr(_idx_mod, "semantic_search_core", fake_semantic_search_core)

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}}))

        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=FAKE_SPACE_ID, include_duplicates=True)

        potential_dups = result.get("potential_duplicates", [])
        assert len(potential_dups) == 0, (
            f"Scores outside [0.70, 0.85) must be excluded; potential_duplicates: {potential_dups}"
        )

    @respx.mock
    def test_duplicate_sweep_self_match_and_pair_dedup(self, monkeypatch):
        """include_duplicates=True; sweep returns object itself (excluded) AND
        a reciprocal pair A→B / B→A; pair appears exactly ONCE in potential_duplicates[].
        AC8 / SF8.
        """
        entity_a = _make_entity("obj-pair-a", name="Pair Entity A", relations=[], backlinks=[])
        entity_b = _make_entity("obj-pair-b", name="Pair Entity B", relations=[], backlinks=[])
        objects = [entity_a, entity_b]

        get_side_effect, register = _standard_mocks(
            objects=objects
        )
        register(entity_a)
        register(entity_b)

        def fake_semantic_search_core(query, space_id, types, limit=5):
            # Called once for A → returns A (self) + B (in-band); once for B → returns A (in-band)
            if "Pair Entity A" in query or query == "Description of Pair Entity A.":
                return [
                    {"object_id": "obj-pair-a", "type": "wiki_entity", "score": 0.80, "name": "A"},  # self
                    {"object_id": "obj-pair-b", "type": "wiki_entity", "score": 0.80, "name": "B"},
                ]
            else:
                return [
                    {"object_id": "obj-pair-a", "type": "wiki_entity", "score": 0.80, "name": "A"},
                ]

        import anytype_llm_wiki.indexer as _idx_mod
        monkeypatch.setattr(_idx_mod, "semantic_search_core", fake_semantic_search_core)

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}}))

        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=FAKE_SPACE_ID, include_duplicates=True)

        potential_dups = result.get("potential_duplicates", [])
        # Exactly one pair (A, B) — self-match excluded; reciprocal deduplicated
        assert len(potential_dups) == 1, (
            f"Expected exactly 1 deduplicated pair; got: {potential_dups}"
        )

    @respx.mock
    def test_duplicate_sweep_off_by_default(self, monkeypatch):
        """Default call wiki_lint(space) and wiki_lint(space, severity_threshold='all')
        with include_duplicates unset → semantic_search_core NEVER called,
        _qdrant() NEVER constructed, potential_duplicates[] empty. AC16/CA-B1.
        """
        entity = _make_entity("obj-default-dup", name="Default Entity",
                              relations=[], backlinks=[])
        objects = [entity]

        get_side_effect, register = _standard_mocks(
            objects=objects
        )
        register(entity)

        ssc_calls = []
        qdrant_calls = []

        def tracking_ssc(*args, **kwargs):
            ssc_calls.append((args, kwargs))
            return []

        def tracking_qdrant(*args, **kwargs):
            qdrant_calls.append((args, kwargs))
            return MagicMock()

        import anytype_llm_wiki.indexer as _idx_mod
        monkeypatch.setattr(_idx_mod, "semantic_search_core", tracking_ssc)
        monkeypatch.setattr(_idx_mod, "_qdrant", tracking_qdrant)

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}}))

        from anytype_llm_wiki.wiki.lint import wiki_lint

        # Default call
        result1 = wiki_lint(space_id=FAKE_SPACE_ID)
        assert len(ssc_calls) == 0, (
            f"semantic_search_core must NOT be called on default wiki_lint; calls: {ssc_calls}"
        )
        assert len(qdrant_calls) == 0, (
            f"_qdrant() must NOT be called on default wiki_lint; calls: {qdrant_calls}"
        )
        assert result1.get("potential_duplicates", []) == [], (
            f"potential_duplicates must be empty on default call; got: {result1.get('potential_duplicates')}"
        )

        # severity_threshold="all" still does not activate sweep
        get_side_effect2, register2 = _standard_mocks(
            objects=objects
        )
        register2(entity)
        respx.get().mock(side_effect=get_side_effect2)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-002", "name": "lint"}}))

        result2 = wiki_lint(space_id=FAKE_SPACE_ID, severity_threshold="all")
        assert len(ssc_calls) == 0, (
            f"semantic_search_core must NOT be called with severity_threshold='all' alone; "
            f"calls: {ssc_calls}"
        )
        assert result2.get("potential_duplicates", []) == [], (
            f"potential_duplicates must be empty with severity_threshold='all' alone; "
            f"got: {result2.get('potential_duplicates')}"
        )

    @respx.mock
    def test_duplicate_sweep_runs_regardless_of_threshold(self, monkeypatch):
        """include_duplicates=True, severity_threshold='high' → semantic_search_core IS called,
        potential_duplicates[] is populated (sweep ran), but no potential_duplicate entry
        in findings[] (Informational, filtered by 'high' threshold). AC7/AC16.
        """
        entity_a = _make_entity("obj-thresh-a", name="Thresh A", relations=[], backlinks=[])
        entity_b = _make_entity("obj-thresh-b", name="Thresh B", relations=[], backlinks=[])
        objects = [entity_a, entity_b]

        get_side_effect, register = _standard_mocks(
            objects=objects
        )
        register(entity_a)
        register(entity_b)

        ssc_called = []

        def fake_ssc(query, space_id, types, limit=5):
            ssc_called.append(query)
            return [
                {"object_id": "obj-thresh-b", "type": "wiki_entity", "score": 0.75, "name": "Thresh B"},
            ]

        import anytype_llm_wiki.indexer as _idx_mod
        monkeypatch.setattr(_idx_mod, "semantic_search_core", fake_ssc)

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}}))

        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=FAKE_SPACE_ID,
                           severity_threshold="high",
                           include_duplicates=True)

        assert len(ssc_called) > 0, (
            f"semantic_search_core MUST be called when include_duplicates=True; "
            f"ssc_called: {ssc_called}"
        )
        potential_dups = result.get("potential_duplicates", [])
        assert len(potential_dups) >= 1, (
            f"potential_duplicates[] must be populated even with severity_threshold='high'; "
            f"got: {potential_dups}"
        )
        findings = result.get("findings", [])
        dup_findings = [f for f in findings if f.get("check") == "potential_duplicate"]
        assert len(dup_findings) == 0, (
            f"potential_duplicate must NOT appear in findings[] with severity_threshold='high'; "
            f"got: {dup_findings}"
        )

    @respx.mock
    def test_duplicate_sweep_skipped_over_object_cap(self, monkeypatch):
        """Enumeration returns > WIKI_LINT_MAX_OBJECTS; include_duplicates=True →
        sweep skipped, lint_sweep_skipped_object_cap warning, High/Critical findings still produced.
        AC12/SF2.
        """
        # Set cap to 3 so we can exceed it with 5 objects
        monkeypatch.setenv("WIKI_LINT_MAX_OBJECTS", "3")

        # 4 objects — exceeds cap of 3
        objects = [
            _make_entity(f"obj-cap-{i}", name=f"Cap Entity {i}",
                         relations=[], backlinks=[])
            for i in range(4)
        ]
        # Add one with asymmetric relation to produce a Critical finding
        objects[0]["properties"].append({"key": "wiki_relations", "objects": ["obj-cap-1"]})

        ssc_called = []

        def tracking_ssc(*args, **kwargs):
            ssc_called.append(args)
            return []

        import anytype_llm_wiki.indexer as _idx_mod
        monkeypatch.setattr(_idx_mod, "semantic_search_core", tracking_ssc)

        get_side_effect, register = _standard_mocks(
            objects=objects
        )
        for o in objects:
            register(o)

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}}))

        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=FAKE_SPACE_ID, include_duplicates=True)

        assert len(ssc_called) == 0, (
            f"Sweep must be skipped above WIKI_LINT_MAX_OBJECTS=3; ssc_called: {ssc_called}"
        )
        warnings = result.get("warnings", [])
        cap_warning = [w for w in warnings if "lint_sweep_skipped_object_cap" in str(w)]
        assert len(cap_warning) >= 1, (
            f"Expected lint_sweep_skipped_object_cap warning; warnings: {warnings}"
        )


class TestSeverityThreshold:
    """AC7: severity_threshold filtering (SF7)."""

    @respx.mock
    def test_severity_threshold_high_filters_medium_low(self, monkeypatch):
        """severity_threshold='high' → findings[] only Critical+High;
        Informational excluded; summary matches. AC7.
        """
        # Entity with needs-review (High) + oversized description (Low)
        long_desc = "X" * 3000
        entity = _make_entity(
            "obj-multi-sev",
            name="Multi Severity",
            relations=["obj-ref-sev"],
            backlinks=["obj-ref-sev"],
            wiki_status="needs-review",
            description=long_desc,
        )
        ref = _make_entity("obj-ref-sev", name="Ref Sev",
                           relations=["obj-multi-sev"],
                           backlinks=["obj-multi-sev"])
        objects = [entity, ref]

        get_side_effect, register = _standard_mocks(
            objects=objects
        )
        register(entity)
        register(ref)

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}}))

        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=FAKE_SPACE_ID, severity_threshold="high")

        findings = result.get("findings", [])
        severities_in_findings = {f["severity"] for f in findings}
        # Must NOT contain medium, low, or informational
        assert "medium" not in severities_in_findings, (
            f"severity_threshold='high' must exclude medium; findings: {findings}"
        )
        assert "low" not in severities_in_findings, (
            f"severity_threshold='high' must exclude low; findings: {findings}"
        )
        assert "informational" not in severities_in_findings, (
            f"severity_threshold='high' must exclude informational; findings: {findings}"
        )

    @respx.mock
    def test_severity_threshold_low_excludes_informational(self, monkeypatch):
        """severity_threshold='low' (default include_duplicates=False) → Critical/High/Medium/Low
        retained; empty_type/potential_duplicate (informational) absent from findings[];
        potential_duplicates[] empty (no sweep on default path). AC7/SF7.
        """
        # Only entity objects — wiki_concept will be zero (empty_type = informational)
        entity = _make_entity("obj-low-thresh", name="Low Threshold Entity",
                              relations=[], backlinks=[])
        objects = [entity]

        get_side_effect, register = _standard_mocks(
            objects=objects
        )
        register(entity)

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}}))

        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=FAKE_SPACE_ID, severity_threshold="low")

        findings = result.get("findings", [])
        informational_findings = [f for f in findings if f.get("severity") == "informational"]
        assert len(informational_findings) == 0, (
            f"severity_threshold='low' must exclude informational findings; got: {informational_findings}"
        )
        assert result.get("potential_duplicates", []) == [], (
            f"potential_duplicates[] must be empty (sweep off by default); "
            f"got: {result.get('potential_duplicates')}"
        )


class TestPreChecks:
    """AC9/AC10: QA#25 schema gate (3 branches) and QA#30 patch-decision gate."""

    @respx.mock
    def test_pre_check_schema_outdated_fires_before_write(self, monkeypatch):
        """Mocked schema version older than '0.4.1' →
        '[CONFIG ERROR] wiki_schema_outdated: ...', status='error',
        error_category='config_error'; no POST to objects. AC9.
        """
        post_called = []

        def tracking_post(request, **kwargs):
            post_called.append(str(request.url))
            return httpx.Response(201, json={"object": {"id": "log-001"}})

        respx.get().mock(return_value=httpx.Response(200, json=_schema_outdated_response()))
        respx.post().mock(side_effect=tracking_post)

        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=FAKE_SPACE_ID)

        result_str = str(result)
        assert "[CONFIG ERROR] wiki_schema_outdated" in result_str, (
            f"Expected '[CONFIG ERROR] wiki_schema_outdated' in result; got: {result_str!r}"
        )
        assert result.get("status") == "error", (
            f"status must be 'error' on outdated schema; got {result.get('status')!r}"
        )
        assert result.get("error_category") == "config_error", (
            f"error_category must be 'config_error'; got {result.get('error_category')!r}"
        )
        # No POST to /objects (no WikiLog written)
        objects_posts = [u for u in post_called if "/objects" in u]
        assert len(objects_posts) == 0, (
            f"Must not POST /objects on schema error; posts: {post_called}"
        )

    @respx.mock
    def test_pre_check_schema_missing_aborts(self, monkeypatch):
        """_schema_version_from_objects returns None (empty space) →
        '[CONFIG ERROR] wiki_schema_missing: ...', status='error', no WikiLog POST.
        AC9/SF4.
        """
        post_called = []

        def tracking_post(request, **kwargs):
            post_called.append(str(request.url))
            return httpx.Response(201, json={"object": {"id": "log-001"}})

        # Empty data → _schema_version_from_objects returns None
        respx.get().mock(return_value=httpx.Response(200, json=_empty_list_response()))
        respx.post().mock(side_effect=tracking_post)

        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=FAKE_SPACE_ID)

        result_str = str(result)
        assert "[CONFIG ERROR] wiki_schema_missing" in result_str, (
            f"Expected '[CONFIG ERROR] wiki_schema_missing' in result; got: {result_str!r}"
        )
        assert result.get("status") == "error", (
            f"status must be 'error' on missing schema; got {result.get('status')!r}"
        )
        objects_posts = [u for u in post_called if "/objects" in u]
        assert len(objects_posts) == 0, (
            f"Must not POST /objects on missing schema; posts: {post_called}"
        )

    @respx.mock
    def test_pre_check_schema_newer_warns_and_continues(self, monkeypatch):
        """Live schema > code → lint continues, 'wiki_schema_newer' warning in warnings[],
        WikiLog still written. AC9/SF4.

        Uses URL-dispatched side_effect (like _standard_mocks) so the test is robust to
        implementation reordering of GET calls (properties/tags fetched before or after
        object enumeration pages, etc.).
        """
        post_called = []

        def tracking_post(request, **kwargs):
            post_called.append(str(request.url))
            return httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}})

        # URL-dispatched GET handler — order-independent, resilient to call-count changes.
        # First list_objects call gets newer-schema response; all subsequent get empty pages.
        _list_calls = [0]

        def get_side_effect(request, **kwargs):
            path = request.url.path
            url_str = str(request.url)

            # list_properties
            if "/properties" in path and "/tags" not in path:
                return httpx.Response(200, json=_make_properties_response())

            # list_tags for a property (property-scoped two-step tag resolution)
            if "/properties/" in path and "/tags" in path:
                parts = path.split("/")
                try:
                    prop_idx = parts.index("properties")
                    prop_id = parts[prop_idx + 1]
                except (ValueError, IndexError):
                    prop_id = "unknown"
                return httpx.Response(200, json=_make_tags_response(prop_id))

            # get_object: /v1/spaces/{sid}/objects/{oid}?format=md
            # (presence of "?" distinguishes single-object fetch from list; per wire contract
            #  AnytypeReadClient.get_object always appends ?format=md)
            if "/objects/" in path and "?" in url_str:
                oid = path.rstrip("/").split("/")[-1]
                return httpx.Response(200, json=_make_get_object_envelope(
                    _make_entity(oid, name=f"Object {oid}")
                ))

            # list_objects (paginated collection scan)
            if "/objects" in path and "/objects/" not in path:
                idx = _list_calls[0]
                _list_calls[0] += 1
                if idx == 0:
                    # First call: return newer-schema marker so the warn-and-continue path fires
                    return httpx.Response(200, json=_schema_newer_response())
                # All subsequent pages: empty (no wiki objects in this test)
                return httpx.Response(200, json=_empty_list_response())

            return httpx.Response(200, json=_empty_list_response())

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(side_effect=tracking_post)

        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=FAKE_SPACE_ID)

        warnings = result.get("warnings", [])
        assert any("wiki_schema_newer" in str(w) for w in warnings), (
            f"Expected 'wiki_schema_newer' warning when live > code; warnings: {warnings}"
        )
        assert result.get("status") in ("ok", "partial"), (
            f"status must be 'ok' or 'partial' when schema is newer; got {result.get('status')!r}"
        )
        wikilog_posts = [u for u in post_called if "/objects" in u]
        assert len(wikilog_posts) >= 1, (
            f"WikiLog must be written when schema is newer (warn-and-continue); posts: {post_called}"
        )


class TestStatusLifecycle:
    """AC11: WikiLog receipt + status lifecycle (SF6)."""

    @respx.mock
    def test_partial_status_on_get_object_failure(self, monkeypatch):
        """One get_object returns 5xx → that object skipped + in warnings[],
        lint continues, status='partial', WikiLog still written. AC11/SF6.
        """
        entity_good = _make_entity("obj-good", name="Good Entity",
                                   relations=[], backlinks=[])
        entity_bad = _make_entity("obj-bad", name="Bad Entity",
                                  relations=[], backlinks=[])
        objects = [entity_good, entity_bad]

        wikilog_posted = []

        # Single-page enumeration: schema marker + both objects in one data[] array.
        # The FAILURE is on the get_object call (5xx) for obj-bad, NOT on list_objects.
        # list_objects returns both objects so the check battery processes them, then
        # get_object for obj-bad returns 500, causing partial status.
        _list_page = {
            "data": [_schema_marker()] + objects,
            "pagination": {"has_more": False},
        }

        def get_side_effect(request, **kwargs):
            url_str = str(request.url)
            path = request.url.path

            if "/properties" in path and "/tags" not in path:
                return httpx.Response(200, json=_make_properties_response())
            if "/properties/" in path and "/tags" in path:
                return httpx.Response(200, json=_make_tags_response("prop-001"))
            # get_object for obj-bad: 5xx to trigger partial status
            if "/objects/obj-bad" in path and "?" in url_str:
                return httpx.Response(500, json={"error": "internal error"})
            # get_object for obj-good: success
            if "/objects/obj-good" in path and "?" in url_str:
                return httpx.Response(200, json=_make_get_object_envelope(entity_good))
            # list_objects: single combined page (spec-faithful single call)
            if "/objects" in path and "?" in url_str and "/objects/" not in path:
                return httpx.Response(200, json=_list_page)
            return httpx.Response(200, json=_empty_list_response())

        def post_side_effect(request, **kwargs):
            try:
                payload = json.loads(request.content)
            except Exception:
                payload = {}
            if payload.get("type_key") == "wiki_log":
                wikilog_posted.append(payload)
            return httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}})

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(side_effect=post_side_effect)

        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=FAKE_SPACE_ID)

        assert result.get("status") == "partial", (
            f"status must be 'partial' when get_object fails for one object; "
            f"got {result.get('status')!r}"
        )
        warnings = result.get("warnings", [])
        assert any("obj-bad" in str(w) for w in warnings), (
            f"Failed object 'obj-bad' must appear in warnings[]; warnings: {warnings}"
        )
        assert len(wikilog_posted) >= 1, (
            f"WikiLog must be written even on partial run; wikilog_posted: {wikilog_posted}"
        )

    @respx.mock
    def test_wikilog_receipt_written_on_clean_run(self, monkeypatch):
        """Clean run → exactly one POST with type_key='wiki_log' and wiki_action=lint;
        elapsed_ms >= 0. AC11/G1.
        """
        objects = []
        wikilog_payloads = []

        def post_side_effect(request, **kwargs):
            try:
                payload = json.loads(request.content)
            except Exception:
                payload = {}
            if payload.get("type_key") == "wiki_log":
                wikilog_payloads.append(payload)
                return httpx.Response(201, json={"object": {"id": "wikilog-clean", "name": "lint-log"}})
            return httpx.Response(201, json={"object": {"id": "other-obj"}})

        get_side_effect, register = _standard_mocks(
            objects=objects
        )

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(side_effect=post_side_effect)

        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=FAKE_SPACE_ID)

        # One WikiLog POST
        assert len(wikilog_payloads) == 1, (
            f"Expected exactly one wiki_log POST; got {len(wikilog_payloads)}: {wikilog_payloads}"
        )
        # elapsed_ms >= 0
        assert result.get("elapsed_ms", -1) >= 0, (
            f"elapsed_ms must be >= 0; got {result.get('elapsed_ms')!r}"
        )
        # wiki_log_id populated
        assert result.get("wiki_log_id") is not None, (
            f"wiki_log_id must be set on clean run; result: {result}"
        )
        # v0.6.0 post-activation (§3.7 change 2): the _PASSIVE_CONTRADICTION_NOTE is removed.
        # _empty_report().notes is now [] — the passive advisory is no longer emitted.
        # This assertion REPLACES the old CPO-6 "passive until v0.6.0" assertion.
        # FAILS until lint.py:172 is updated to return "notes": [] (§3.7 change 2).
        assert not any(
            f.get("check") == "contradiction_unresolved" for f in result.get("findings", [])
        ), "clean-run fixture must fire no contradiction findings (precondition)"
        notes = result.get("notes", [])
        assert notes == [], (
            f"post-v0.6.0: _empty_report notes must be empty [] — the passive-contradiction "
            f"note is removed (§3.7 change 2); got notes: {notes}"
        )


class TestObjectBudgetWarning:
    """AC12: object budget warning above 500 and sweep cap (SF2)."""

    @respx.mock
    def test_object_count_budget_warning_above_500(self, monkeypatch):
        """Enumeration returns 501 objects → 'lint_object_count_exceeded_budget: 501'
        in LintReport.warnings. AC12.
        """
        # Build 501 minimal objects
        objects = [
            _make_entity(f"obj-budget-{i}", name=f"Budget {i}",
                         relations=[], backlinks=[])
            for i in range(501)
        ]

        get_side_effect, register = _standard_mocks(
            objects=objects
        )
        for o in objects:
            register(o)

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}}))

        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=FAKE_SPACE_ID)

        warnings = result.get("warnings", [])
        budget_warnings = [w for w in warnings
                           if "lint_object_count_exceeded_budget" in str(w) and "501" in str(w)]
        assert len(budget_warnings) >= 1, (
            f"Expected 'lint_object_count_exceeded_budget: 501' in warnings; warnings: {warnings}"
        )


class TestTagResolution:
    """AC13: tag resolution uses property-scoped two-step (never space-level /tags)."""

    @respx.mock
    def test_tag_resolution_never_calls_space_level_tags(self, monkeypatch):
        """Negative assertion (QA ADV-2): register a distinct respx route for the
        space-level GET /v1/spaces/{space_id}/tags; run a full lint; assert that route's
        .called is False and resolution went through property-scoped two-step. AC13.
        """
        entity = _make_entity("obj-tag-res", name="Tag Res Entity",
                              relations=[], backlinks=[], wiki_status="needs-review")
        objects = [entity]

        # Register the space-level /tags route FIRST with a specific mock
        space_level_tags_route = respx.get(
            url=f"{ANYTYPE_BASE}/v1/spaces/{FAKE_SPACE_ID}/tags"
        ).mock(return_value=httpx.Response(404, json={"error": "not found"}))

        get_side_effect, register = _standard_mocks(
            objects=objects
        )
        register(entity)

        respx.get().mock(side_effect=get_side_effect)
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001", "name": "lint"}}))

        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=FAKE_SPACE_ID)

        assert space_level_tags_route.called is False, (
            f"Space-level GET /v1/spaces/{{space_id}}/tags must NEVER be called; "
            f"it was called — tag resolution bug (space-level /tags is 404). "
            f"Lint result: {result}"
        )
        # Verify the lint at least ran (to ensure the negative assertion is meaningful)
        assert isinstance(result, dict), "wiki_lint must return a dict"


class TestRegistration:
    """AC14: CLI + server registration."""

    def test_wiki_lint_registered_and_cli_routed(self):
        """wiki_lint in MCP tool registry (server.py) with include_duplicates parameter;
        'wiki-lint' in cli.SUBCOMMANDS with --include-duplicates flag routing to _cmd_lint.
        AC14.
        """
        import inspect

        # 1. CLI: wiki-lint in SUBCOMMANDS
        from anytype_llm_wiki.wiki import cli
        assert "wiki-lint" in cli.SUBCOMMANDS, (
            f"'wiki-lint' must be in cli.SUBCOMMANDS; got: {cli.SUBCOMMANDS}"
        )

        # 2. CLI: _cmd_lint must exist
        assert hasattr(cli, "_cmd_lint"), (
            "cli module must have a '_cmd_lint' function"
        )

        # 3. CLI: parser must include --include-duplicates
        parser = cli.build_parser()
        # Parse a wiki-lint invocation with --include-duplicates
        args = parser.parse_args(["wiki-lint", "--space-id", "test-space", "--include-duplicates"])
        assert getattr(args, "include_duplicates", None) is True, (
            f"'--include-duplicates' flag must set include_duplicates=True; got: {args}"
        )

        # 4. Server: wiki_lint registered as MCP tool
        from anytype_llm_wiki.server import mcp
        tool_names: set = set()
        if hasattr(mcp, "_tool_manager") and hasattr(mcp._tool_manager, "_tools"):
            tool_names = set(mcp._tool_manager._tools.keys())
        elif hasattr(mcp, "_tools"):
            tool_names = set(mcp._tools.keys())
        elif hasattr(mcp, "tools"):
            raw_tools = mcp.tools
            if callable(raw_tools):
                raw_tools = raw_tools()
            tool_names = {
                t if isinstance(t, str) else getattr(t, "name", str(t))
                for t in raw_tools
            }
        else:
            import asyncio
            try:
                loop = asyncio.new_event_loop()
                tools = loop.run_until_complete(mcp.list_tools())
                loop.close()
                tool_names = {t.name for t in tools}
            except Exception:
                pass

        assert "wiki_lint" in tool_names, (
            f"wiki_lint is not registered as an MCP tool; registered tools: {sorted(tool_names)}"
        )

        # 5. Server wiki_lint must accept include_duplicates parameter
        from anytype_llm_wiki.server import wiki_lint as _server_wiki_lint
        sig = inspect.signature(_server_wiki_lint)
        assert "include_duplicates" in sig.parameters, (
            f"server.wiki_lint must expose include_duplicates parameter; params: {list(sig.parameters)}"
        )


# ---------------------------------------------------------------------------
# Section 4 — Live smoke tests (skip-gated)
# ---------------------------------------------------------------------------

@pytest.mark.live
class TestLintLive:
    """Live smoke tests — skip-gated on ANYTYPE_SPACE_ID and ANYTYPE_BACKLINKED_OBJECT_ID."""

    def test_end_to_end_lint(self):
        """Live end-to-end lint against a real space. AC15."""
        space_id = os.environ.get("ANYTYPE_SPACE_ID")
        if not space_id:
            pytest.skip("ANYTYPE_SPACE_ID not set — live lint test skipped")
        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=space_id)
        assert result["status"] in ("ok", "partial")
        assert result["wiki_log_id"] is not None
        assert isinstance(result["findings"], list)
        assert isinstance(result["summary"], dict)

    def test_backlinks_field_shape_live(self):
        """ADV-1: confirm the live get_object backlinks shape the D1 primary
        path depends on (asserted from a session finding, not CI-covered).
        Impl task ONE is to confirm this against a real object before building
        the primary path; this smoke keeps that confirmation alive. AC15.
        """
        space_id = os.environ.get("ANYTYPE_SPACE_ID")
        if not space_id:
            pytest.skip("ANYTYPE_SPACE_ID not set — live backlinks smoke skipped")
        from anytype_llm_wiki.anytype_client import AnytypeReadClient
        # Pick any enumerable object with a known inbound relation in the test space.
        obj_id = os.environ.get("ANYTYPE_BACKLINKED_OBJECT_ID")
        if not obj_id:
            pytest.skip("ANYTYPE_BACKLINKED_OBJECT_ID not set — backlinks smoke skipped")
        obj = AnytypeReadClient().get_object(space_id, obj_id)
        # The D1 contract: `backlinks` is present and is a list (possibly empty),
        # each element parseable by _parse_relation_elements (id string or {"id": ...}).
        assert "backlinks" in obj, "get_object response lacks `backlinks` — D1 primary path assumption violated"
        assert isinstance(obj["backlinks"], list), f"backlinks is {type(obj['backlinks'])}, expected list"
