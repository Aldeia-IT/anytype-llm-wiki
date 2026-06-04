"""Tests for wiki/ingest.py — wiki_ingest MCP tool orchestration.

These tests FAIL until src/anytype_llm_wiki/wiki/ingest.py is implemented.
Covers: AC#1-5, AC#8-16 (master spec inherited ACs), AC-T1-T5 (wiki_action tags),
AC-L1 (no body key in update), AC-L2 (no type_key filter in search), AC-S1, AC-S2.
"""

import multiprocessing
import os
import sys
import time
import pytest
import respx
import httpx


# ---------------------------------------------------------------------------
# Module-level worker functions for multiprocessing.Process (AC#5).
# These MUST be at module scope so that macOS 'spawn'-mode pickling works.
# Locally-scoped (nested) functions cannot be pickled by the spawn method.
# ---------------------------------------------------------------------------

def _hold_lock_worker(q, space_id, lock_dir):
    """Module-level child-process target: acquire space_ingest_lock, signal parent, hold it.

    Accepts all state via args=(q, space_id, lock_dir) — no closure over test locals.
    The src/ directory is inserted into sys.path so the module is importable in the
    spawned child process regardless of whether it is installed in the child's env.
    """
    # Resolve src/ relative to this file's directory (tests/wiki/ -> ../../src)
    src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src")
    sys.path.insert(0, os.path.abspath(src_dir))
    os.environ["WIKI_LOCK_DIR"] = lock_dir
    from anytype_llm_wiki.wiki.util import space_ingest_lock  # noqa: PLC0415
    with space_ingest_lock(space_id, "http://example.com"):
        q.put("acquired")
        time.sleep(5)  # hold the lock while the parent tries to acquire

ANYTYPE_BASE = "http://127.0.0.1:31012"
FAKE_SPACE_ID = "space-ingest-test-001"
FAKE_SPACE_ID_2 = "space-ingest-test-002"
FAKE_API_KEY = "test-ingest-key"
FAKE_API_VERSION = "2025-11-08"


@pytest.fixture(autouse=True)
def set_anytype_env(monkeypatch):
    monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
    monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
    monkeypatch.delenv("WIKI_EXTRACT_ENDPOINT", raising=False)


def _make_schema_ok_response():
    """Return a mock list_objects response with a valid v0.3.0 schema marker."""
    return {
        "data": [
            {
                "id": "coll-wiki-001",
                "name": "Wiki",
                "type": {"key": "collection"},
                "properties": [
                    {"key": "wiki_schema_version", "text": "0.3.0"}
                ],
            }
        ],
        "pagination": {"has_more": False},
    }


class TestIngestImport:
    """wiki_ingest must be importable and callable."""

    def test_wiki_ingest_importable(self):
        """wiki_ingest must be importable from anytype_llm_wiki.wiki.ingest."""
        from anytype_llm_wiki.wiki.ingest import wiki_ingest  # noqa: F401

    def test_wiki_ingest_is_callable(self):
        """wiki_ingest must be callable."""
        from anytype_llm_wiki.wiki.ingest import wiki_ingest
        assert callable(wiki_ingest)

    def test_wiki_ingest_signature(self):
        """wiki_ingest must accept source, space_id, and optional domain_hint (§7.2)."""
        import inspect
        from anytype_llm_wiki.wiki.ingest import wiki_ingest
        sig = inspect.signature(wiki_ingest)
        params = list(sig.parameters.keys())
        assert "source" in params, "wiki_ingest must have 'source' parameter"
        assert "space_id" in params, "wiki_ingest must have 'space_id' parameter"
        assert "domain_hint" in params, "wiki_ingest must have 'domain_hint' parameter"


class TestPatchDecisionPreCheck:
    """AC#15: missing or malformed patch-decision.md → [CONFIG ERROR] patch_decision_missing_or_invalid.

    Canonical path: .aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/patch-decision.md
    There is NO #284 copy.
    """

    @respx.mock
    def test_missing_patch_decision_returns_config_error(self, monkeypatch, tmp_path):
        """AC#15: wiki_ingest with missing patch-decision.md (ALDEIA_DIR pointing to empty dir)
        returns [CONFIG ERROR] patch_decision_missing_or_invalid before any write.

        Covers: §9.1 AC#15. Canonical path is ONLY #140 parent dir.
        """
        monkeypatch.setenv("ALDEIA_DIR", str(tmp_path))  # no patch-decision.md here
        respx.get().mock(return_value=httpx.Response(200, json=_make_schema_ok_response()))
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "x"}}))

        from anytype_llm_wiki.wiki.ingest import wiki_ingest
        result = wiki_ingest(source="https://example.com/paper", space_id=FAKE_SPACE_ID)
        result_str = str(result)
        assert "patch_decision_missing_or_invalid" in result_str and "[CONFIG ERROR]" in result_str, (
            f"Expected [CONFIG ERROR] patch_decision_missing_or_invalid for missing "
            f"patch-decision.md, got: {result_str!r}"
        )

    @respx.mock
    def test_malformed_patch_decision_returns_config_error(self, monkeypatch, tmp_path):
        """AC#15: wiki_ingest with malformed patch-decision.md returns
        [CONFIG ERROR] patch_decision_missing_or_invalid.
        """
        patch_dir = tmp_path / "patch-decision.md"
        patch_dir.write_text("NOT_VALID_YAML_OR_JSON: !!python/object:os.system bad", encoding="utf-8")
        monkeypatch.setenv("ALDEIA_DIR", str(tmp_path))
        respx.get().mock(return_value=httpx.Response(200, json=_make_schema_ok_response()))
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "x"}}))

        from anytype_llm_wiki.wiki.ingest import wiki_ingest
        result = wiki_ingest(source="https://example.com/paper", space_id=FAKE_SPACE_ID)
        result_str = str(result)
        # Malformed patch-decision.md → config error
        # (The read_patch_decision function returns None for unparseable content)
        assert (
            "patch_decision_missing_or_invalid" in result_str
            or "[CONFIG ERROR]" in result_str
        ), (
            f"Expected [CONFIG ERROR] for malformed patch-decision.md: {result_str!r}"
        )


class TestSchemaCompatibilityCheck:
    """AC-M4: outdated schema (0.2.0 WikiLog, code is 0.3.0) → wiki_schema_outdated error."""

    @respx.mock
    def test_wiki_ingest_outdated_schema_returns_config_error(self, monkeypatch):
        """AC-M4: _read_schema_version returns '0.2.0', code is '0.3.0' →
        [CONFIG ERROR] wiki_schema_outdated (AC-M4, §9.3).
        """
        # Mock list_objects to return a WikiLog with version 0.2.0 and no collection marker
        outdated_response = {
            "data": [
                {
                    "id": "log-001",
                    "name": "bootstrap 2026-01-01",
                    "type": {"key": "wiki_log"},
                    "properties": [{"key": "wiki_schema_version", "text": "0.2.0"}],
                }
            ],
            "pagination": {"has_more": False},
        }
        respx.get().mock(return_value=httpx.Response(200, json=outdated_response))
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "x"}}))

        from anytype_llm_wiki.wiki.ingest import wiki_ingest
        result = wiki_ingest(source="https://example.com/paper", space_id=FAKE_SPACE_ID)
        result_str = str(result)
        assert "wiki_schema_outdated" in result_str or "[CONFIG ERROR]" in result_str, (
            f"Expected [CONFIG ERROR] wiki_schema_outdated for outdated schema, got: {result_str!r}"
        )


class TestDomainHintValidation:
    """AC#10: domain_hint not in space taxonomy → [CONFIG ERROR] invalid_domain_hint before fetch."""

    @respx.mock
    def test_invalid_domain_hint_returns_config_error(self, monkeypatch):
        """AC#10: domain_hint not in space taxonomy → [CONFIG ERROR] invalid_domain_hint before fetch.

        Covers: §9.1 AC#10.
        """
        respx.get().mock(return_value=httpx.Response(200, json=_make_schema_ok_response()))
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "x"}}))

        from anytype_llm_wiki.wiki.ingest import wiki_ingest
        result = wiki_ingest(
            source="https://example.com/paper",
            space_id=FAKE_SPACE_ID,
            domain_hint="not_a_real_domain_tag_xyz_999",
        )
        result_str = str(result)
        assert "invalid_domain_hint" in result_str or "[CONFIG ERROR]" in result_str, (
            f"Expected [CONFIG ERROR] invalid_domain_hint, got: {result_str!r}"
        )


class TestEmptySourceIngest:
    """AC#8 / §9.4 QA-A3: empty-source ingest returns full response shape including objects_skipped:[]."""

    @respx.mock
    def test_empty_source_response_shape(self, monkeypatch):
        """AC#8 (SF3 delta): empty-source ingest returns status:'ok', objects_created:[],
        objects_skipped:[], warnings:['empty_source'].

        The objects_skipped:[] field is the SF3-restored master AC#8 shape.
        Covers: §9.4 test_empty_source_response_shape, AC#8.
        """
        respx.get().mock(return_value=httpx.Response(200, json=_make_schema_ok_response()))
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "src-001"}}))

        from anytype_llm_wiki.wiki.ingest import wiki_ingest
        # Empty source: a markdown file with no useful content
        import tempfile, pathlib
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("   \n\n   \n")
            empty_file = f.name
        try:
            result = wiki_ingest(source=empty_file, space_id=FAKE_SPACE_ID)
        finally:
            os.unlink(empty_file)

        assert isinstance(result, dict), f"wiki_ingest must return a dict; got {type(result)}"
        assert result.get("status") == "ok", (
            f"Empty-source ingest must return status='ok'; got {result.get('status')!r}"
        )
        assert result.get("objects_created") == [], (
            f"Empty-source ingest must return objects_created=[]; got {result.get('objects_created')!r}"
        )
        # SF3 delta: objects_skipped must be present and be an empty list
        assert "objects_skipped" in result, (
            "Empty-source ingest result must include 'objects_skipped' key (SF3 delta, AC#8)"
        )
        assert result.get("objects_skipped") == [], (
            f"Empty-source ingest must return objects_skipped=[]; got {result.get('objects_skipped')!r}"
        )
        warnings = result.get("warnings", [])
        assert any("empty_source" in str(w) for w in warnings), (
            f"Empty-source ingest must include 'empty_source' in warnings; got: {warnings}"
        )


class TestPartialFailure:
    """AC#3: partial failure → WikiLog entry + coherent response + status:'partial'."""

    @respx.mock
    def test_partial_failure_returns_partial_status(self, monkeypatch, tmp_path):
        """AC#3: partial failure produces status:'partial', WikiLog entry, coherent response.

        Arrange: supply a markdown file with TWO entities so that the first create_object
        call succeeds (201) and the second entity-create raises a 500. The implementation
        must catch the per-entity failure, continue, and return:
          - result["status"] == "partial"
          - result contains "objects_created" and "objects_updated" keys
          - result contains a "warnings" key (partial failures reported there)
          - at least one WikiLog (type_key == "wiki_log") create_object call was made

        The WikiLog-create assertion spies on the POST calls and checks that at least one
        payload carried type_key="wiki_log". This gates the "WikiLog entry written" part
        of AC#3 without requiring a live client.

        Covers: §9.1 AC#3 partial-failure path.
        """
        call_count = {"objects": 0}
        wikilog_created = {"yes": False}

        def partial_post(request, **kwargs):
            import json as _json
            try:
                payload = _json.loads(request.content)
            except Exception:
                payload = {}

            # Track WikiLog creation
            if payload.get("type_key") == "wiki_log":
                wikilog_created["yes"] = True
                return httpx.Response(
                    201, json={"object": {"id": "wikilog-001", "name": "ingest log"}}
                )

            # First entity create succeeds; second entity create fails (partial failure)
            if payload.get("type_key") in (
                "wiki_entity", "wiki_concept", "wiki_comparison", "wiki_query"
            ):
                call_count["objects"] += 1
                if call_count["objects"] == 2:
                    return httpx.Response(500, json={"error": "internal server error"})
                return httpx.Response(
                    201,
                    json={"object": {"id": f"entity-{call_count['objects']}", "name": "Entity A"}},
                )

            # Default: all other creates succeed (source object, etc.)
            return httpx.Response(201, json={"object": {"id": "obj-default", "name": "x"}})

        # Markdown with two distinct named sections to produce two entity candidates
        md_content = (
            "# Entity Alpha\n\nFact: Alpha is the first entity in this partial-failure test.\n\n"
            "# Entity Beta\n\nFact: Beta is the second entity in this partial-failure test.\n"
        )
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, dir=str(tmp_path)
        ) as f:
            f.write(md_content)
            md_file = f.name

        respx.get().mock(return_value=httpx.Response(200, json=_make_schema_ok_response()))
        respx.post().mock(side_effect=partial_post)

        from anytype_llm_wiki.wiki.ingest import wiki_ingest
        result = wiki_ingest(source=md_file, space_id=FAKE_SPACE_ID)

        # AC#3 assertion 1: status must be "partial" (not "ok", not "error")
        assert result.get("status") == "partial", (
            f"AC#3: partial failure must produce status='partial'; got {result.get('status')!r}. "
            f"Full result: {result}"
        )
        # AC#3 assertion 2: coherent response shape
        assert "objects_created" in result, (
            f"AC#3: result must contain 'objects_created' key; got keys: {list(result.keys())}"
        )
        assert "objects_updated" in result, (
            f"AC#3: result must contain 'objects_updated' key; got keys: {list(result.keys())}"
        )
        assert "warnings" in result, (
            f"AC#3: result must contain 'warnings' key; got keys: {list(result.keys())}"
        )
        # AC#3 assertion 3: WikiLog entry written
        assert wikilog_created["yes"], (
            "AC#3: wiki_ingest must create a WikiLog (type_key='wiki_log') entry "
            "even when a partial failure occurs — no WikiLog POST detected"
        )


class TestReindexFailureWarning:
    """AC#9: post-ingest reindex_anytype failure → status:'ok', reindex_failed warning."""

    @respx.mock
    def test_reindex_failure_returns_ok_with_warning(self, monkeypatch):
        """AC#9: post-ingest reindex failure → status:'ok', 'reindex_failed' in warnings.

        Covers: §9.1 AC#9.
        """
        respx.get().mock(return_value=httpx.Response(200, json=_make_schema_ok_response()))
        respx.post().mock(return_value=httpx.Response(201, json={
            "object": {"id": "src-001", "name": "Source"}
        }))

        def fail_reindex(*args, **kwargs):
            raise RuntimeError("Qdrant is unreachable")

        monkeypatch.setattr(
            "anytype_llm_wiki.wiki.ingest.reindex_anytype",
            fail_reindex,
            raising=False,
        )

        from anytype_llm_wiki.wiki.ingest import wiki_ingest
        result = wiki_ingest(source="https://example.com/paper", space_id=FAKE_SPACE_ID)
        result_str = str(result)
        # Must still return ok (not error) even though reindex failed
        assert result.get("status") == "ok" or "ok" in result_str, (
            f"Expected status='ok' even when reindex fails; got: {result_str!r}"
        )
        warnings = result.get("warnings", [])
        assert any("reindex_failed" in str(w) for w in warnings), (
            f"Expected 'reindex_failed' warning when reindex fails; warnings: {warnings}"
        )


class TestBidirectionalRelationRollback:
    """AC#13 (v0.3.0): if either direction of a bidirectional relation fails, both are rolled back;
    WikiLog records relation_rollback event.
    """

    @respx.mock
    def test_bidi_relation_rollback_on_failure(self, monkeypatch, tmp_path):
        """AC#13: B-side of a property-based bidi relation fails → A-side reverted; relation_rollback logged.

        NOTE — UPDATED FROM THE STANDALONE-RELATION-OBJECT MODEL. The original
        approved test encoded relations as standalone ``wiki_relation``-typed
        objects with a DELETE-by-id rollback. That type does NOT exist in
        ``types_schema.WIKI_TYPES``; the master spec (§ingest step 6) and the
        verified native-backlinks model represent relations as BIDIRECTIONAL
        OBJECTS-FORMAT PROPERTY LINKS — ``wiki_relations`` on an Entity (and
        ``wiki_related`` on a Concept) set on BOTH sides. This test is rewritten
        to that property-based mechanism while preserving its intent: when one
        side of the bidirectional write fails, the succeeded side is rolled back
        and the WikiLog records ``relation_rollback``.

        Arrange: two heading entities (Alpha, Beta) are created → one A→B relation
        is derived. The A-side relation PATCH (on the Alpha object id) succeeds;
        the B-side relation PATCH (on the Beta object id) returns 500. This
        triggers the rollback path.

        Assertions:
          1. A rollback PATCH was issued against the A object id that reverts the
             link (the A-side property is PATCHed a SECOND time back to its prior
             empty objects list).
          2. A WikiLog POST payload's JSON contains "relation_rollback".

        Covers: §9.1 AC#13 (v0.3.0 bidi relation rollback, property-based).
        """
        import json as _json

        a_id = "entity-alpha-001"
        b_id = "entity-beta-001"
        wikilog_payloads: list[dict] = []
        # All relation PATCHes targeting the A object id, with their objects list.
        a_relation_patches: list[list] = []

        def mock_post(request, **kwargs):
            try:
                payload = _json.loads(request.content)
            except Exception:
                payload = {}

            if payload.get("type_key") == "wiki_log":
                wikilog_payloads.append(payload)
                return httpx.Response(201, json={"object": {"id": "wikilog-001", "name": "log"}})

            # Entity creates: first → Alpha, second → Beta. Source/others → src.
            type_key = payload.get("type_key")
            if type_key == "wiki_entity":
                name = payload.get("name", "")
                if "Alpha" in name:
                    return httpx.Response(201, json={"object": {"id": a_id, "name": name}})
                if "Beta" in name:
                    return httpx.Response(201, json={"object": {"id": b_id, "name": name}})
            return httpx.Response(201, json={"object": {"id": "src-001", "name": "src"}})

        def mock_patch(request, **kwargs):
            try:
                payload = _json.loads(request.content)
            except Exception:
                payload = {}
            url = str(request.url)
            # Extract the relation objects list (if this is a relation PATCH).
            rel_objects = None
            for prop in payload.get("properties", []) or []:
                if prop.get("key") in ("wiki_relations", "wiki_related"):
                    rel_objects = prop.get("objects")
            # A-side relation PATCH (on Alpha) — record and succeed.
            if a_id in url and rel_objects is not None:
                a_relation_patches.append(rel_objects)
                return httpx.Response(200, json={"object": {"id": a_id}})
            # B-side relation PATCH (on Beta) — fail to trigger rollback.
            if b_id in url and rel_objects is not None:
                return httpx.Response(500, json={"error": "relation patch failed"})
            return httpx.Response(200, json={"object": {"id": "patched"}})

        # Two heading entities → one derived A->B relation.
        md_content = (
            "# Entity Alpha\n\nFact: Alpha relates to Beta.\n\n"
            "# Entity Beta\n\nFact: Beta relates to Alpha.\n"
        )
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, dir=str(tmp_path)
        ) as f:
            f.write(md_content)
            md_file = f.name

        respx.get().mock(return_value=httpx.Response(200, json=_make_schema_ok_response()))
        respx.post().mock(side_effect=mock_post)
        respx.patch().mock(side_effect=mock_patch)

        from anytype_llm_wiki.wiki.ingest import wiki_ingest
        result = wiki_ingest(source=md_file, space_id=FAKE_SPACE_ID)

        # AC#13 assertion 1: result is a dict (basic sanity)
        assert isinstance(result, dict), (
            f"wiki_ingest must return a dict even on rollback; got {type(result)}"
        )

        # AC#13 assertion 2: the A-side relation was PATCHed twice — once to set
        # the link (objects == [b_id]) and once to revert it (objects == []).
        assert len(a_relation_patches) >= 2, (
            f"AC#13: A-side relation property must be PATCHed to set the link AND "
            f"a SECOND time to roll it back when the B-side fails. "
            f"A-side relation PATCHes captured: {a_relation_patches!r}"
        )
        assert b_id in (a_relation_patches[0] or []), (
            f"AC#13: first A-side relation PATCH must set the link to B; got "
            f"{a_relation_patches[0]!r}"
        )
        assert b_id not in (a_relation_patches[-1] or []), (
            f"AC#13: rollback PATCH must REMOVE B from A's relation property; "
            f"final A-side relation PATCH was {a_relation_patches[-1]!r}"
        )

        # AC#13 assertion 3: WikiLog records relation_rollback event
        wikilog_records_rollback = any(
            "relation_rollback" in _json.dumps(payload)
            for payload in wikilog_payloads
        )
        assert wikilog_records_rollback, (
            f"AC#13: WikiLog must record a 'relation_rollback' event when bidi rollback occurs. "
            f"WikiLog payloads captured: {wikilog_payloads!r}"
        )


class TestConcurrentIngestLock:
    """AC#5: concurrent ingest against same space → [DATA ERROR] ingest_in_progress.
    Concurrent call against different space succeeds.

    MUST use multiprocessing.Process (kernel-held flock). NOT threading.Thread.

    Worker functions (_hold_lock_worker) are defined at MODULE SCOPE (not nested inside
    test methods) so that macOS 'spawn'-mode multiprocessing can pickle them. Locally-scoped
    (closure) functions cannot be pickled by the spawn method, which would cause
    AttributeError at child.start() before any production code runs.
    """

    def test_concurrent_ingest_same_space_rejected(self, tmp_path, monkeypatch):
        """AC#5: concurrent ingest against the same space is rejected with
        [DATA ERROR] ingest_in_progress.

        Uses multiprocessing.Process (module-level _hold_lock_worker) to hold the flock
        in a child process — per Mem0 learning. A threading.Thread or asyncio mock does
        not exercise the kernel-held flock.
        """
        from anytype_llm_wiki.wiki.util import space_ingest_lock

        monkeypatch.setenv("WIKI_LOCK_DIR", str(tmp_path / "locks"))
        os.makedirs(str(tmp_path / "locks"), exist_ok=True)

        # Sentinel queue for deterministic handshake (Mem0 pattern)
        q: multiprocessing.Queue = multiprocessing.Queue()

        # Use the MODULE-LEVEL worker function (picklable on macOS spawn mode)
        child = multiprocessing.Process(
            target=_hold_lock_worker,
            args=(q, FAKE_SPACE_ID, str(tmp_path / "locks")),
            daemon=True,
        )
        child.start()
        try:
            # Wait for child to acquire the lock
            sentinel = q.get(timeout=5)
            assert sentinel == "acquired", f"Unexpected sentinel: {sentinel}"

            # Parent tries to acquire the same space's lock — must fail
            try:
                with space_ingest_lock(FAKE_SPACE_ID, "http://example.com"):
                    pytest.fail("Expected RuntimeError for concurrent ingest on same space")
            except RuntimeError as exc:
                assert "ingest_in_progress" in str(exc) and "[DATA ERROR]" in str(exc), (
                    f"Expected [DATA ERROR] ingest_in_progress, got: {exc!r}"
                )
        finally:
            child.terminate()
            child.join(timeout=2)

    def test_concurrent_ingest_different_space_succeeds(self, tmp_path, monkeypatch):
        """AC#5: concurrent ingest against a different space succeeds (different lock file).

        Covers: §9.1 AC#5 — different space does not interfere.
        Uses module-level _hold_lock_worker (picklable on macOS spawn mode).
        """
        monkeypatch.setenv("WIKI_LOCK_DIR", str(tmp_path / "locks"))
        os.makedirs(str(tmp_path / "locks"), exist_ok=True)

        from anytype_llm_wiki.wiki.util import space_ingest_lock

        q: multiprocessing.Queue = multiprocessing.Queue()

        # Use the MODULE-LEVEL worker function (picklable on macOS spawn mode)
        child = multiprocessing.Process(
            target=_hold_lock_worker,
            args=(q, FAKE_SPACE_ID, str(tmp_path / "locks")),
            daemon=True,
        )
        child.start()
        try:
            sentinel = q.get(timeout=5)
            assert sentinel == "acquired"
            # Different space — must succeed (different lock file)
            with space_ingest_lock(FAKE_SPACE_ID_2, "http://example.com"):
                pass  # No exception expected
        finally:
            child.terminate()
            child.join(timeout=2)


class TestDashFoldNormalization:
    """AC#6: normalize_title folds all 10 dash codepoints to ASCII hyphen."""

    @pytest.mark.parametrize("codepoint,char_name", [
        (0x2010, "HYPHEN"),
        (0x2011, "NON-BREAKING HYPHEN"),
        (0x2012, "FIGURE DASH"),
        (0x2013, "EN DASH"),
        (0x2014, "EM DASH"),
        (0x2212, "MINUS SIGN"),
        (0xFE63, "SMALL HYPHEN-MINUS"),
        (0xFF0D, "FULLWIDTH HYPHEN-MINUS"),
        (0x00AD, "SOFT HYPHEN"),
        (0x2015, "HORIZONTAL BAR"),
    ])
    def test_dash_fold_codepoints(self, codepoint: int, char_name: str):
        """AC#6: normalize_title must fold U+{codepoint:04X} ({char_name}) to ASCII hyphen.

        Covers: §9.1 AC#6 dash-fold table (10 codepoints).
        """
        from anytype_llm_wiki.wiki.util import normalize_title
        char = chr(codepoint)
        raw = f"Attention{char}is{char}All You Need"
        normalized = normalize_title(raw)
        assert "-" in normalized, (
            f"Expected ASCII hyphen after fold of U+{codepoint:04X} ({char_name}); "
            f"got: {normalized!r}"
        )
        assert char not in normalized, (
            f"U+{codepoint:04X} ({char_name}) must be folded out; still present in {normalized!r}"
        )

    def test_same_entity_different_dash_resolves_to_same(self):
        """AC#6: two entity names differing only in dash variant normalize to same key."""
        from anytype_llm_wiki.wiki.util import normalize_title
        name_em_dash = "GPT—Large Language Model"
        name_en_dash = "GPT–Large Language Model"
        name_ascii = "GPT-Large Language Model"
        assert normalize_title(name_em_dash) == normalize_title(name_ascii), (
            "EM DASH should fold to same key as ASCII hyphen"
        )
        assert normalize_title(name_en_dash) == normalize_title(name_ascii), (
            "EN DASH should fold to same key as ASCII hyphen"
        )


class TestBidiControlCharNamePolicy:
    """AC#16: bidi/control-char name policy + property-value sanitization.
    Names with U+FEFF/U+2028/U+2029/tag-chars → name_policy_rejected.
    Property values are also sanitized (SF2 delta).
    """

    @pytest.mark.parametrize("codepoint,char_name", [
        (0xFEFF, "BOM/ZWNBSP"),
        (0x2028, "LINE SEPARATOR"),
        (0x2029, "PARAGRAPH SEPARATOR"),
        (0xE0020, "TAG SPACE (U+E0020)"),
    ])
    def test_name_policy_rejects_bidi_control_chars(self, codepoint: int, char_name: str):
        """AC#16: entity/concept name containing bidi/control chars → name_policy_rejected.

        Covers: §9.1 AC#16.
        """
        from anytype_llm_wiki.wiki.extraction import sanitize_name
        bad_name = f"Good{chr(codepoint)}Name"
        result = sanitize_name(bad_name)
        assert result is None or chr(codepoint) not in (result or ""), (
            f"U+{codepoint:04X} ({char_name}) must be stripped from entity name; "
            f"sanitize_name returned: {result!r}"
        )

    def test_property_value_sanitized_strips_feff(self):
        """AC#16 delta (SF2): U+FEFF in property value is stripped by sanitizer.

        Property values (wiki_facts, wiki_description, etc.) are now an embedded
        retrievable surface — bidi/control-char sanitizer must apply to values too.
        """
        from anytype_llm_wiki.wiki.extraction import sanitize_property_value
        raw = "﻿Some fact about the entity"
        result = sanitize_property_value(raw)
        assert "﻿" not in result, (
            f"U+FEFF must be stripped from property value; sanitize_property_value returned: {result!r}"
        )
        assert "Some fact" in result, (
            f"Visible content must be preserved after sanitization: {result!r}"
        )

    def test_property_value_sanitized_strips_tag_chars(self):
        """AC#16 delta (SF2): Unicode tag characters (U+E0020–U+E007F) stripped from property values."""
        from anytype_llm_wiki.wiki.extraction import sanitize_property_value
        tag_char = "\U000E0020"  # TAG SPACE (first in the tag block)
        raw = f"Some {tag_char}fact with tag chars\U000E007F embedded"
        result = sanitize_property_value(raw)
        assert tag_char not in result, (
            f"Tag chars must be stripped from property value; got: {result!r}"
        )


class TestUpdatePathNoBodyKey:
    """AC-L1 (B4): update_object must NEVER include a body/markdown key in any update call."""

    @respx.mock
    def test_update_path_no_body_key(self, monkeypatch):
        """AC-L1: mock-spy update_object; assert no 'body'/'markdown' key in ANY update payload.

        The body PATCH is silently ignored (patch-decision.md verified fact).
        wiki_ingest must use properties-only PATCH on the update path.
        Covers: §9.5 test_update_path_no_body_key, AC-L1, B4.
        """
        update_payloads: list[dict] = []

        def capture_patch(request, **kwargs):
            import json as _json
            try:
                payload = _json.loads(request.content)
                update_payloads.append(payload)
            except Exception:
                pass
            return httpx.Response(200, json={"object": {"id": "existing-entity-001"}})

        # The headingless URL source names the candidate after the source URL.
        # Seed a search result whose name matches so resolve_entity returns
        # action="update" → the PATCH-capturing loop is NON-VACUOUS.
        source_url = "https://example.com/update-paper"

        def capture_post(request, **kwargs):
            import json as _json
            # /search → return a SEARCH-SHAPED response that matches the candidate.
            if "/search" in str(request.url):
                return httpx.Response(200, json={
                    "data": [
                        {
                            "id": "existing-entity-001",
                            "name": source_url,
                            "type": {"key": "wiki_entity"},
                            "properties": [{"key": "wiki_facts", "text": "old"}],
                        },
                    ],
                    "pagination": {"has_more": False},
                })
            # Non-search POST (Source create, etc.).
            return httpx.Response(201, json={"object": {"id": "src-001"}})

        respx.get().mock(return_value=httpx.Response(200, json=_make_schema_ok_response()))
        respx.post().mock(side_effect=capture_post)
        respx.patch().mock(side_effect=capture_patch)

        from anytype_llm_wiki.wiki.ingest import wiki_ingest
        wiki_ingest(source=source_url, space_id=FAKE_SPACE_ID)

        # Vacuous-loop guard (addendum item 3 / QA-ADV-1): the update path must
        # actually fire, otherwise the body/markdown assertions pass vacuously.
        assert update_payloads, "update path must fire (non-vacuous guard)"

        for payload in update_payloads:
            assert "body" not in payload, (
                f"AC-L1: 'body' key must not appear in any update_object payload; "
                f"found in: {payload}"
            )
            assert "markdown" not in payload, (
                f"AC-L1: 'markdown' key must not appear in any update_object payload; "
                f"found in: {payload}"
            )


class TestCreateWikiObjectEmptyBody:
    """AC-P7 create side / AC-L1: ingest-authored wiki objects created with no body content."""

    @respx.mock
    def test_create_wiki_object_empty_body(self, monkeypatch):
        """AC-P7 (create side) / AC-L1: wiki_ingest creates wiki_entity/wiki_concept/
        wiki_comparison/wiki_query objects with NO body content (empty-body invariant).

        Body content at create-time would go stale on first property PATCH (patch-decision.md).
        Covers: §9.5 test_create_wiki_object_empty_body, AC-P7, AC-L1.
        """
        create_payloads: list[dict] = []

        def capture_post(request, **kwargs):
            import json as _json
            path = str(request.url)
            if "objects" in path:
                try:
                    payload = _json.loads(request.content)
                    create_payloads.append(payload)
                except Exception:
                    pass
            return httpx.Response(201, json={"object": {"id": "new-obj-001", "name": "New Entity"}})

        respx.get().mock(return_value=httpx.Response(200, json=_make_schema_ok_response()))
        respx.post().mock(side_effect=capture_post)

        from anytype_llm_wiki.wiki.ingest import wiki_ingest
        wiki_ingest(source="https://example.com/new-paper", space_id=FAKE_SPACE_ID)

        wiki_type_keys = {"wiki_entity", "wiki_concept", "wiki_comparison", "wiki_query"}
        # Vacuous-loop guard (addendum item 3): the create path must actually fire,
        # otherwise the empty-body assertion below would pass without executing.
        assert any(p.get("type_key") in wiki_type_keys for p in create_payloads), (
            "AC-P7: expected at least one wiki object create_object call — the create "
            "path did not execute, so the empty-body assertion would pass vacuously"
        )
        for payload in create_payloads:
            if payload.get("type_key") in wiki_type_keys:
                assert not payload.get("body"), (
                    f"AC-P7/AC-L1: wiki object create_object must have empty body; "
                    f"found body={payload.get('body')!r} in create payload for "
                    f"type_key={payload.get('type_key')!r}"
                )
                assert not payload.get("markdown"), (
                    f"AC-L1: wiki object create_object must not include 'markdown' key; "
                    f"found in: {payload}"
                )


class TestResolveEntityIgnoresWrongType:
    """AC-L2 (B5/SF8): entity resolution ignores wrong-type objects; no type_key filter to search."""

    @respx.mock
    def test_resolve_entity_ignores_wrong_type(self, monkeypatch):
        """AC-L2: client.search returns mixed-type set incl. same-name wrong-type obj →
        wrong-type obj NOT matched/updated; no filter={'type_key':...} arg passed to search.

        filter_expression: no_op (verified in patch-decision.md) — type filtering MUST be
        client-side, NOT via API filter argument.
        Covers: §9.5 test_resolve_entity_ignores_wrong_type, AC-L2, B5/SF8.
        """
        search_payloads: list[dict] = []

        def capture_search(request, **kwargs):
            import json as _json
            try:
                payload = _json.loads(request.content)
                search_payloads.append(payload)
            except Exception:
                pass
            # Return mixed-type results: one right type, one wrong type, same name
            return httpx.Response(200, json={"data": [
                {
                    "id": "entity-correct-001",
                    "name": "Transformer Architecture",
                    "type": {"key": "wiki_entity"},
                    "properties": [],
                },
                {
                    "id": "note-wrong-type-002",
                    "name": "Transformer Architecture",  # same name, wrong type!
                    "type": {"key": "note"},
                    "properties": [],
                },
            ]})

        update_calls: list[str] = []

        def capture_patch(request, **kwargs):
            path = str(request.url)
            update_calls.append(path)
            return httpx.Response(200, json={"object": {"id": "entity-correct-001"}})

        respx.get().mock(return_value=httpx.Response(200, json=_make_schema_ok_response()))
        respx.post().mock(side_effect=capture_search)
        respx.patch().mock(side_effect=capture_patch)

        from anytype_llm_wiki.wiki.ingest import wiki_ingest
        wiki_ingest(source="https://example.com/transformer-paper", space_id=FAKE_SPACE_ID)

        # Assert: no filter={"type_key": ...} was passed to any search call
        for payload in search_payloads:
            if "filter" in payload:
                filter_val = payload["filter"]
                # A type_key FilterExpression is a no-op — must NOT be used
                assert "type_key" not in str(filter_val), (
                    f"AC-L2: filter={{'type_key':...}} must not be passed to client.search; "
                    f"search payload: {payload}"
                )

        # Assert: wrong-type object (note-wrong-type-002) was not updated
        for call_path in update_calls:
            assert "note-wrong-type-002" not in call_path, (
                f"AC-L2: wrong-type object 'note-wrong-type-002' must not be updated; "
                f"but found in update call: {call_path}"
            )


class TestWikiActionTagResolution:
    """AC-T4/T5: WikiLog carries wiki_action=ingest; tag resolution failure degrades gracefully."""

    @respx.mock
    def test_ingest_wikilog_carries_ingest_action(self, monkeypatch):
        """AC-T4: WikiLog written by wiki_ingest carries wiki_action=ingest
        (the ingest tag id in the select field).

        Covers: §9.4 test_ingest_wikilog_carries_ingest_action, AC-T4.
        """
        wikilog_payloads: list[dict] = []

        def capture_post(request, **kwargs):
            import json as _json
            path = str(request.url)
            try:
                payload = _json.loads(request.content)
                if payload.get("type_key") == "wiki_log":
                    wikilog_payloads.append(payload)
            except Exception:
                pass
            return httpx.Response(201, json={
                "object": {"id": f"obj-{len(wikilog_payloads)}", "name": "log"},
                "tag": {"id": "tag-ingest-001", "name": "ingest"},
            })

        def mock_get(request, **kwargs):
            path = str(request.url)
            if "tags" in path:
                return httpx.Response(200, json={
                    "data": [
                        {"id": "tag-ingest-001", "name": "ingest", "color": "blue"},
                        {"id": "tag-bootstrap-001", "name": "bootstrap", "color": "grey"},
                    ],
                    "pagination": {"has_more": False},
                })
            return httpx.Response(200, json=_make_schema_ok_response())

        respx.get().mock(side_effect=mock_get)
        respx.post().mock(side_effect=capture_post)

        from anytype_llm_wiki.wiki.ingest import wiki_ingest
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("   \n\n")
            empty_file = f.name
        try:
            wiki_ingest(source=empty_file, space_id=FAKE_SPACE_ID)
        finally:
            os.unlink(empty_file)

        assert len(wikilog_payloads) >= 1, (
            "Expected at least one WikiLog create_object call; got none"
        )
        wikilog_props_list = []
        for wl in wikilog_payloads:
            wikilog_props_list.extend(wl.get("properties", []))
        # Assert wiki_action select property with ingest tag id
        wiki_action_props = [
            p for p in wikilog_props_list
            if p.get("key") == "wiki_action" and p.get("select")
        ]
        assert len(wiki_action_props) >= 1, (
            f"AC-T4: WikiLog must carry wiki_action select with ingest tag id; "
            f"WikiLog properties: {wikilog_props_list}"
        )

    @respx.mock
    def test_ingest_action_tag_resolution_failure_writes_wikilog(self, monkeypatch):
        """AC-T5: list_tags raises → ingest completes, WikiLog written, wiki_action_tag_not_found
        in warnings.

        Tag-resolution failure must NOT abort ingest. WikiLog is always written (degraded).
        Covers: §9.4 test_ingest_action_tag_resolution_failure_writes_wikilog, AC-T5.
        """
        wikilog_created = {"yes": False}

        def mock_get_with_tags_error(request, **kwargs):
            path = str(request.url)
            if "tags" in path:
                raise httpx.NetworkError("simulated list_tags failure")
            return httpx.Response(200, json=_make_schema_ok_response())

        def capture_post(request, **kwargs):
            import json as _json
            try:
                payload = _json.loads(request.content)
                if payload.get("type_key") == "wiki_log":
                    wikilog_created["yes"] = True
            except Exception:
                pass
            return httpx.Response(201, json={"object": {"id": "obj-001", "name": "log"}})

        respx.get().mock(side_effect=mock_get_with_tags_error)
        respx.post().mock(side_effect=capture_post)

        from anytype_llm_wiki.wiki.ingest import wiki_ingest
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("   \n\n")
            empty_file = f.name
        try:
            result = wiki_ingest(source=empty_file, space_id=FAKE_SPACE_ID)
        finally:
            os.unlink(empty_file)

        # WikiLog must be written even when tag resolution fails
        assert wikilog_created["yes"], (
            "AC-T5: WikiLog must be written even when list_tags raises (degraded-but-written)"
        )
        # wiki_action_tag_not_found in warnings
        warnings = result.get("warnings", [])
        assert any("wiki_action_tag_not_found" in str(w) for w in warnings), (
            f"AC-T5: 'wiki_action_tag_not_found' must be in warnings when list_tags fails; "
            f"warnings: {warnings}"
        )


def _write_valid_patch_decision(tmp_path):
    """Write a patch-decision.md with the required keys and point ALDEIA_DIR at it."""
    (tmp_path / "patch-decision.md").write_text(
        "patch_body_updates: ignored\nimplementation_path: properties_only\n",
        encoding="utf-8",
    )


class TestIngestEntryPathAcquiresLock:
    """Addendum HARD GATE 2: wiki_ingest entry path MUST acquire space_ingest_lock.

    CI-runnable (no multiprocessing) — mock at the space_ingest_lock boundary so
    that acquisition raises, and assert wiki_ingest surfaces
    [DATA ERROR] ingest_in_progress.
    """

    @respx.mock
    def test_entry_path_rejects_when_lock_held(self, monkeypatch, tmp_path):
        _write_valid_patch_decision(tmp_path)
        monkeypatch.setenv("ALDEIA_DIR", str(tmp_path))
        respx.get().mock(return_value=httpx.Response(200, json=_make_schema_ok_response()))
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "x"}}))

        import anytype_llm_wiki.wiki.ingest as _ingest

        def fake_lock(space_id, source_ref=None):
            raise RuntimeError(
                "[DATA ERROR] ingest_in_progress: another ingest is running"
            )

        monkeypatch.setattr(_ingest, "space_ingest_lock", fake_lock)

        result = _ingest.wiki_ingest(source="https://example.com/x", space_id=FAKE_SPACE_ID)
        result_str = str(result)
        assert "ingest_in_progress" in result_str and "[DATA ERROR]" in result_str, (
            f"Entry path must acquire space_ingest_lock and surface ingest_in_progress; "
            f"got: {result_str!r}"
        )


class TestIngestEntryPathConsentBeforeOffMachine:
    """Addendum HARD GATE 1: the consent/ack check MUST sit on the real wiki_ingest
    path AHEAD of the first off-machine transmission.

    Spy on call ordering: the consent check must fire before any non-local HTTP
    call when WIKI_EXTRACT_ENDPOINT is non-local and no ack file exists.
    """

    @respx.mock
    def test_consent_fires_before_first_off_machine_call(self, monkeypatch, tmp_path):
        _write_valid_patch_decision(tmp_path)
        monkeypatch.setenv("ALDEIA_DIR", str(tmp_path))
        monkeypatch.setenv(
            "WIKI_EXTRACT_ENDPOINT", "https://api.openai.com/v1/chat/completions"
        )
        # Ack dir with no ack file → consent must fire.
        ack_dir = tmp_path / "acks"
        ack_dir.mkdir()
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

        respx.get().mock(return_value=httpx.Response(200, json=_make_schema_ok_response()))
        respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "src-001"}}))

        import anytype_llm_wiki.wiki.ingest as _ingest

        events: list[str] = []

        def spy_consent(*args, **kwargs):
            events.append("consent")
            # Do not actually emit/transmit; just record ordering.

        monkeypatch.setattr(_ingest, "check_remote_endpoint_consent", spy_consent)

        def spy_extract(*args, **kwargs):
            events.append("extract")  # the first off-machine transmission boundary
            return {"entities": [], "concepts": []}

        monkeypatch.setattr(_ingest, "extract", spy_extract)

        import tempfile, os as _os
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, dir=str(tmp_path)
        ) as f:
            f.write("# Some Heading\n\nSome body content for extraction.\n")
            md_file = f.name
        try:
            _ingest.wiki_ingest(source=md_file, space_id=FAKE_SPACE_ID)
        finally:
            _os.unlink(md_file)

        assert "consent" in events, "consent check must run on the wiki_ingest path"
        if "extract" in events:
            assert events.index("consent") < events.index("extract"), (
                f"consent must fire BEFORE the first off-machine transmission (extract); "
                f"order: {events}"
            )


# ---------------------------------------------------------------------------
# Live tests (@pytest.mark.live — skip when services unreachable)
# ---------------------------------------------------------------------------

@pytest.mark.live
class TestIngestCreateEndToEnd:
    """AC-P2 (create-side end-to-end retrieval) — @pytest.mark.live.

    Requires live Anytype + Qdrant + Ollama.
    """

    def test_create_side_named_entity_retrieval(self):
        """AC-P2 (QA-B1): create entity via wiki_ingest (empty body, wiki_facts populated) →
        auto-reindex → semantic_search on query matching facts returns that specific named entity.

        Assert by object_id/name TOP-K MEMBERSHIP (not loose substring scan — QA-ADV-2).
        This is the create-side end-to-end proof that the indexer property gap is closed.
        Non-skippable pre-tag gate (§10.1).

        Covers: §9.2 test_create_side_named_entity_retrieval, AC-P2.
        """
        import os
        space_id = os.environ.get("ANYTYPE_SPACE_ID")
        if not space_id:
            pytest.skip("ANYTYPE_SPACE_ID not set — live create-side retrieval test skipped")

        from anytype_llm_wiki.wiki.ingest import wiki_ingest
        from anytype_llm_wiki.server import semantic_search

        # Use a pinned fixture entity with a unique query string for reproducibility (QA-ADV-2)
        FIXTURE_ENTITY_NAME = "Attention Is All You Need Test Entity"
        FIXTURE_QUERY = "self-attention transformer architecture positional encoding"
        import tempfile, os as _os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(
                f"# {FIXTURE_ENTITY_NAME}\n\n"
                "The Transformer model introduces a self-attention mechanism for sequence-to-sequence tasks. "
                "It uses positional encoding and multi-head attention. Released 2017 by Vaswani et al."
            )
            fixture_file = f.name

        created_entity_id = None
        created_entity_name = None
        try:
            result = wiki_ingest(source=fixture_file, space_id=space_id)
            for obj in result.get("objects_created", []):
                if obj.get("name") == FIXTURE_ENTITY_NAME or FIXTURE_ENTITY_NAME in str(obj.get("name", "")):
                    created_entity_id = obj.get("object_id") or obj.get("id")
                    created_entity_name = obj.get("name")
                    break
        finally:
            _os.unlink(fixture_file)

        assert created_entity_id or created_entity_name, (
            f"AC-P2: wiki_ingest must create the fixture entity; result: {result}"
        )

        # semantic_search must return the entity in top-K results
        search_results = semantic_search(query=FIXTURE_QUERY, space_id=space_id)
        result_ids = [r.get("object_id") for r in search_results]
        result_names = [r.get("object_name") for r in search_results]

        # ONE coherent membership check (QA-ADV-2 — not a loose substring scan)
        entity_found = (
            (created_entity_id and created_entity_id in result_ids)
            or (created_entity_name and created_entity_name in result_names)
        )
        assert entity_found, (
            f"AC-P2: semantic_search must return the created entity in top-K results. "
            f"Entity id={created_entity_id!r}, name={created_entity_name!r}. "
            f"Top-K result ids: {result_ids[:10]!r}, names: {result_names[:10]!r}"
        )


@pytest.mark.live
class TestIngestUpdateEndToEnd:
    """AC-P7 (update-path end-to-end retrieval) — @pytest.mark.live.

    Requires live Anytype + Qdrant + Ollama. Non-skippable pre-tag gate.
    """

    def test_reingest_reembeds_updated_facts(self):
        """AC-P7 (B2/empty-body invariant + SF5 update path): re-ingesting an existing entity
        updates wiki_facts via property PATCH (empty body unchanged), and after reindex
        semantic_search returns the entity for a query matching the UPDATED facts.

        Also verifies create_object/update_object carry no body (ties AC-L1).

        Assert retrieval by object_id/name TOP-K MEMBERSHIP (QA-ADV-2).
        Verifies AC-P7 — the update-path end-to-end guard backed by V2 release-blocking gate.

        Covers: §9.2 test_reingest_reembeds_updated_facts, AC-P7.
        """
        import os
        space_id = os.environ.get("ANYTYPE_SPACE_ID")
        if not space_id:
            pytest.skip("ANYTYPE_SPACE_ID not set — live update-path retrieval test skipped")

        from anytype_llm_wiki.wiki.ingest import wiki_ingest
        from anytype_llm_wiki.server import semantic_search

        ENTITY_NAME = "BGE-M3 Test Entity For Update Path"
        INITIAL_QUERY = "dense retrieval embedding model"
        UPDATED_QUERY = "multi-lingual multi-functionality retrieval paradigm"
        import tempfile, os as _os

        # First ingest — create with initial facts
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(
                f"# {ENTITY_NAME}\n\n"
                "BGE-M3 is a dense retrieval embedding model for semantic search."
            )
            initial_file = f.name
        try:
            result1 = wiki_ingest(source=initial_file, space_id=space_id)
        finally:
            _os.unlink(initial_file)

        created_id = None
        for obj in result1.get("objects_created", []):
            if ENTITY_NAME in str(obj.get("name", "")):
                created_id = obj.get("object_id") or obj.get("id")
                break

        # Second ingest — update with different facts
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(
                f"# {ENTITY_NAME}\n\n"
                "BGE-M3 supports multi-lingual, multi-functionality, and multi-granularity retrieval paradigm."
            )
            updated_file = f.name
        try:
            result2 = wiki_ingest(source=updated_file, space_id=space_id)
        finally:
            _os.unlink(updated_file)

        # After reindex, semantic_search on UPDATED query must return the entity
        search_results = semantic_search(query=UPDATED_QUERY, space_id=space_id)
        result_ids = [r.get("object_id") for r in search_results]
        result_names = [r.get("object_name") for r in search_results]

        # ONE coherent membership check (QA-ADV-2 — exact equality, no substring scan)
        entity_found = (
            (created_id and created_id in result_ids)
            or ENTITY_NAME in result_names
        )
        assert entity_found, (
            f"AC-P7: after update, semantic_search on updated facts must return the entity "
            f"in top-K results by exact id/name membership (QA-ADV-2). "
            f"Entity id={created_id!r}, name={ENTITY_NAME!r}. "
            f"Top-K result ids: {result_ids[:10]!r}, names: {result_names[:10]!r}"
        )


# ---------------------------------------------------------------------------
# Re-ingest idempotency (regression for the interactive live-review finding).
# Root causes fixed: (1) extraction now uses deterministic decoding so the same
# source yields the same entity titles; (2) Source objects are de-duplicated.
# Spec AC (v0.3.0 §functional ACs): "ingesting the same source twice → 0 created,
# >=1 updated". No end-to-end test covered this before; the prior live behavior
# produced a duplicate Source + near-duplicate entities.
# ---------------------------------------------------------------------------


class TestReingestIdempotency:
    @respx.mock
    def test_reingest_same_source_creates_zero_and_reuses_source(self, monkeypatch):
        monkeypatch.setenv("WIKI_AUTO_REINDEX", "false")  # keep the test offline/fast
        src = "https://example.com/idempotent-paper"
        store: dict = {}  # (normalized_name, type_key) -> {"id","name"}
        counter = {"n": 0}

        def on_get(request, **kwargs):
            # Both the schema read (list_objects) and the source fetch resolve here.
            return httpx.Response(200, json=_make_schema_ok_response())

        def on_post(request, **kwargs):
            import json as _json
            from anytype_llm_wiki.wiki.util import normalize_title
            url = str(request.url)
            if "/search" in url:
                q = normalize_title(_json.loads(request.content).get("query", ""))
                data = [
                    {"id": o["id"], "name": o["name"], "type": {"key": tk}, "properties": []}
                    for (n, tk), o in store.items() if n == q
                ]
                return httpx.Response(200, json={"data": data, "pagination": {"has_more": False}})
            if "/objects" in url:
                payload = _json.loads(request.content)
                name = payload.get("name", "")
                tk = payload.get("type_key", "")
                counter["n"] += 1
                oid = f"obj-{counter['n']}"
                store[(normalize_title(name), tk)] = {"id": oid, "name": name}
                return httpx.Response(201, json={"object": {"id": oid, "name": name}})
            # Ollama extraction endpoints → degrade (forces deterministic
            # heading-derived candidates only; no live model needed).
            return httpx.Response(200, json={"response": "not-json"})

        def on_patch(request, **kwargs):
            return httpx.Response(200, json={"object": {"id": "patched"}})

        respx.get().mock(side_effect=on_get)
        respx.post().mock(side_effect=on_post)
        respx.patch().mock(side_effect=on_patch)

        from anytype_llm_wiki.wiki.ingest import wiki_ingest
        r1 = wiki_ingest(source=src, space_id=FAKE_SPACE_ID)
        r2 = wiki_ingest(source=src, space_id=FAKE_SPACE_ID)

        assert r1["status"] == "ok", r1
        assert r1["objects_created"], "run 1 must create >=1 object (non-vacuous guard)"
        assert len(r2["objects_created"]) == 0, (
            f"re-ingest of the same source must create 0 objects; got {r2['objects_created']}"
        )
        assert r1["source_object_id"] and r1["source_object_id"] == r2["source_object_id"], (
            "re-ingest must reuse the same Source object (Source dedup)"
        )


class TestWriteWikilogRegressionGuards:
    """AC-R12b/B6, SF15 — regression guards for #284 shipped behavior (MUST PASS now)."""

    @respx.mock
    def test_write_wikilog_default_name_is_ingest(self, monkeypatch):
        """AC-R12b/B6: _write_wikilog with no action_name kwarg names object 'ingest {subject}'.

        Guards the current default behavior: name must be f"ingest {subject}".
        Must pass against the current source AND after the planned generalization
        that adds a defaulted action_name="ingest" parameter.
        """
        import json as _json

        captured_creates: list[dict] = []
        subject = "https://example.com/my-paper"

        def mock_post(request, **kwargs):
            try:
                payload = _json.loads(request.content)
                captured_creates.append(payload)
            except Exception:
                pass
            return httpx.Response(201, json={"object": {"id": "log-001", "name": f"ingest {subject}"}})

        respx.post().mock(side_effect=mock_post)

        from anytype_llm_wiki.wiki.ingest import _write_wikilog
        from anytype_llm_wiki.wiki.wiki_client import WikiClient

        client = WikiClient(base_url=ANYTYPE_BASE)
        _write_wikilog(
            client,
            FAKE_SPACE_ID,
            subject=subject,
            created=3,
            updated=1,
            notes="test notes",
            action_tag_id=None,
        )

        assert captured_creates, "_write_wikilog must call create_object (no POST captured)"
        names = [c.get("name", "") for c in captured_creates]
        assert any(n == f"ingest {subject}" for n in names), (
            f"AC-R12b/B6: _write_wikilog without action_name must name the object "
            f"'ingest {{subject}}'; captured names={names}"
        )

    @respx.mock
    def test_resolve_action_tag_default_is_ingest(self, monkeypatch):
        """SF15: _resolve_wiki_action_tag(client, space_id) with no action_name kwarg resolves
        the 'ingest' tag id from a mocked list_properties/list_tags response.

        Guards the shipped #284 path. Must pass now AND after the planned generalization
        that adds a defaulted action_name="ingest" param.
        """
        ingest_tag_id = "tag-ingest-fixed-001"

        def mock_get(request, **kwargs):
            path = str(request.url)
            # Check /tags before /properties: the tags URL is
            # /v1/spaces/{id}/properties/{prop_id}/tags — it contains both.
            if "/tags" in path:
                return httpx.Response(200, json={
                    "data": [
                        {"id": ingest_tag_id, "name": "ingest", "color": "blue"},
                        {"id": "tag-query-001", "name": "query", "color": "green"},
                    ],
                    "pagination": {"has_more": False},
                })
            if "/properties" in path:
                return httpx.Response(200, json={
                    "data": [
                        {"id": "prop-wiki-action", "key": "wiki_action",
                         "name": "Action", "format": "select"},
                    ],
                    "pagination": {"has_more": False},
                })
            return httpx.Response(200, json={"data": [], "pagination": {"has_more": False}})

        respx.get().mock(side_effect=mock_get)

        from anytype_llm_wiki.wiki.ingest import _resolve_wiki_action_tag
        from anytype_llm_wiki.wiki.wiki_client import WikiClient

        client = WikiClient(base_url=ANYTYPE_BASE)
        tag_id, degraded = _resolve_wiki_action_tag(client, FAKE_SPACE_ID)

        assert not degraded, (
            "SF15: _resolve_wiki_action_tag must not degrade when tags are reachable; "
            f"degraded={degraded}"
        )
        assert tag_id == ingest_tag_id, (
            f"SF15: _resolve_wiki_action_tag with no action_name must resolve the 'ingest' tag; "
            f"expected tag_id={ingest_tag_id!r}, got {tag_id!r}"
        )


class TestExtractionDeterministicOptions:
    @respx.mock
    def test_extract_sends_temperature_zero(self):
        import json as _json
        captured: list = []

        def on_post(request, **kwargs):
            captured.append(_json.loads(request.content))
            return httpx.Response(
                200, json={"response": _json.dumps({"entities": [], "concepts": []})}
            )

        respx.post().mock(side_effect=on_post)
        from anytype_llm_wiki.wiki.extraction import extract
        extract(markdown="# Topic\n\nSome text.", space_id=FAKE_SPACE_ID)
        assert captured, "extraction must call the Ollama endpoint"
        opts = captured[0].get("options") or {}
        assert opts.get("temperature") == 0, (
            f"extraction must use deterministic decoding (temperature 0); got options={opts!r}"
        )
