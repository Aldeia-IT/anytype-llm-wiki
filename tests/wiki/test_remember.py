"""Tests for wiki/remember.py — wiki_remember MCP tool (spec #289 v0.3.1).

These tests FAIL until src/anytype_llm_wiki/wiki/remember.py is implemented.
Covers: AC-R1 through AC-R31, AC-R-S1, AC-R-S2, addendum items 1-2.
"""

import json
import os
import sys
import pytest
import respx
import httpx
from unittest import mock
from unittest.mock import MagicMock, patch, call


ANYTYPE_BASE = "http://127.0.0.1:31012"
OLLAMA_BASE = "http://127.0.0.1:11434"
FAKE_SPACE_ID = "space-remember-test-001"
FAKE_API_KEY = "test-remember-key"
FAKE_API_VERSION = "2025-11-08"


# ---------------------------------------------------------------------------
# Module-level autouse fixture: set env for every test in this module.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def set_anytype_env(monkeypatch):
    monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
    monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
    monkeypatch.delenv("WIKI_EXTRACT_ENDPOINT", raising=False)
    monkeypatch.setenv("WIKI_EXTRACT_MODEL", "qwen2.5:7b")


# ---------------------------------------------------------------------------
# Helpers: canned response builders
# ---------------------------------------------------------------------------

def _schema_current_response():
    """Mock list_objects stamping the LIVE ``WIKI_SCHEMA_VERSION`` — matches the
    code version, so the schema pre-check passes (no outdated/newer abort).
    Version-agnostic: tracks schema bumps automatically (do NOT hardcode a
    literal here — that froze on every bump and forced mock edits)."""
    from anytype_llm_wiki.wiki.types_schema import WIKI_SCHEMA_VERSION
    return {
        "data": [
            {
                "id": "log-schema-001",
                "name": "bootstrap 2026-06-04",
                "type": {"key": "wiki_log"},
                "properties": [{"key": "wiki_schema_version", "text": WIKI_SCHEMA_VERSION}],
            }
        ],
        "pagination": {"has_more": False},
    }


def _schema_outdated_response():
    """Mock with a version guaranteed OLDER than code (AC-R11 outdated abort).
    Fixed low sentinel — never needs bumping."""
    return {
        "data": [
            {
                "id": "log-schema-old",
                "name": "bootstrap 2026-01-01",
                "type": {"key": "wiki_log"},
                "properties": [{"key": "wiki_schema_version", "text": "0.0.1"}],
            }
        ],
        "pagination": {"has_more": False},
    }


def _schema_newer_response():
    """Mock with a version guaranteed NEWER than code (AC-R11 wiki_schema_newer
    warning). Fixed high sentinel — never needs bumping."""
    return {
        "data": [
            {
                "id": "log-schema-new",
                "name": "bootstrap 2099-01-01",
                "type": {"key": "wiki_log"},
                "properties": [{"key": "wiki_schema_version", "text": "99.0.0"}],
            }
        ],
        "pagination": {"has_more": False},
    }


def _empty_search_response():
    return {"data": [], "pagination": {"has_more": False}}


def _single_entity_response(obj_id="entity-001", name="TestEntity"):
    return {
        "data": [
            {
                "id": obj_id,
                "name": name,
                "type": {"key": "wiki_entity"},
                "properties": [{"key": "wiki_facts", "text": "TestEntity supports Python."}],
            }
        ],
        "pagination": {"has_more": False},
    }


def _create_object_response(obj_id="new-obj-001", name="TestEntity"):
    return {"object": {"id": obj_id, "name": name, "spaceId": FAKE_SPACE_ID}}


def _wikilog_create_response():
    return {"object": {"id": "wikilog-r-001", "name": "remember TestEntity"}}


def _source_create_response():
    return {"object": {"id": "source-r-001", "name": "agent 2026-06-04"}}


def _tags_response(tags):
    """Return a list_tags response with the given list of tag dicts."""
    return {"data": [{"id": f"tag-{t}", "name": t} for t in tags]}


def _properties_response(props):
    """Return a list_properties response."""
    return {
        "data": [
            {"id": f"prop-{p}", "key": p, "typeKey": "text"}
            for p in props
        ]
    }


def _canned_extract_result(subjects=None):
    """Canned extraction result dict (mocks extract() return value)."""
    if subjects is None:
        subjects = [{"name": "TestEntity", "kind": "entity", "facts": "TestEntity supports Python."}]
    return {
        "entities": [s for s in subjects if s.get("kind") == "entity"],
        "concepts": [s for s in subjects if s.get("kind") == "concept"],
    }


def _canned_consolidate_result(
    consolidated_text="TestEntity supports Python.",
    changed=False,
    fact_actions=None,
    conflicts=None,
):
    if fact_actions is None:
        fact_actions = [{"fact": "TestEntity supports Python.", "action": "keep", "supersedes": None}]
    if conflicts is None:
        conflicts = []
    return {
        "consolidated_text": consolidated_text,
        "changed": changed,
        "fact_actions": fact_actions,
        "conflicts": conflicts,
    }


def _patch_decision_ok(monkeypatch, tmp_path):
    """Write a valid patch-decision.md and point ALDEIA_DIR at it."""
    pd_content = "patch: true\ndecision: apply\n"
    pd_file = tmp_path / "patch-decision.md"
    pd_file.write_text(pd_content)
    monkeypatch.setenv("ALDEIA_DIR", str(tmp_path))


# ---------------------------------------------------------------------------
# §10.2 — Idempotency Guard tests
# ---------------------------------------------------------------------------

class TestNormalizeForCompare:
    """Unit tests for _normalize_for_compare helper."""

    def test_normalize_for_compare_collapses_whitespace(self):
        """AC-R6/D3 — newlines, tabs, runs of spaces all collapse to single space."""
        from anytype_llm_wiki.wiki.remember import _normalize_for_compare
        text = "Hello\n\t  World\r\n  foo"
        result = _normalize_for_compare(text)
        assert result == "hello world foo", (
            f"_normalize_for_compare must collapse whitespace runs; got {result!r}"
        )

    def test_normalize_for_compare_lowercases(self):
        """AC-R6/D3 — upper/mixed case folds to lowercase."""
        from anytype_llm_wiki.wiki.remember import _normalize_for_compare
        result = _normalize_for_compare("HELLO World")
        assert result == "hello world", (
            f"_normalize_for_compare must lowercase; got {result!r}"
        )

    def test_normalize_for_compare_non_string_returns_empty(self):
        """D3 — non-string input returns empty string."""
        from anytype_llm_wiki.wiki.remember import _normalize_for_compare
        assert _normalize_for_compare(None) == ""
        assert _normalize_for_compare(42) == ""

    def test_normalize_for_compare_strips_leading_trailing(self):
        """D3 — leading/trailing whitespace stripped."""
        from anytype_llm_wiki.wiki.remember import _normalize_for_compare
        result = _normalize_for_compare("  hello  ")
        assert result == "hello"


class TestIdempotencyGate:
    """AC-R6 — double-gate: changed=False / normalized-equal → skip PATCH."""

    def test_idempotency_gate_llm_changed_false_skips_patch(self, monkeypatch, tmp_path):
        """AC-R6/AC-R2 — consolidate returns changed=False → no update_object; action=consolidated."""
        _patch_decision_ok(monkeypatch, tmp_path)
        existing_text = "TestEntity supports Python."
        consolidate_result = _canned_consolidate_result(
            consolidated_text=existing_text, changed=False
        )
        mock_consolidate = MagicMock(return_value=consolidate_result)
        mock_extract = MagicMock(return_value=_canned_extract_result())
        mock_update = MagicMock(return_value={"object": {"id": "entity-001"}})
        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_single_entity_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(201, json=_wikilog_create_response())
            )
            router.patch(
                f"/v1/spaces/{FAKE_SPACE_ID}/objects/entity-001"
            ).mock(return_value=httpx.Response(200, json={"object": {"id": "entity-001"}}))

            monkeypatch.setattr(
                "anytype_llm_wiki.wiki.remember.consolidate", mock_consolidate, raising=False
            )
            monkeypatch.setattr(
                "anytype_llm_wiki.wiki.remember.extract", mock_extract, raising=False
            )
            monkeypatch.setattr(
                "anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(
                space_id=FAKE_SPACE_ID,
                knowledge="TestEntity supports Python.",
            )

        assert result.get("status") in ("ok", "partial"), f"Unexpected status: {result}"
        objects = result.get("objects", [])
        assert objects, "Expected at least one per-object result"
        actions = [o.get("action") for o in objects]
        assert "consolidated" in actions, (
            f"changed=False must yield action=consolidated; got actions={actions}"
        )
        assert "updated" not in actions, (
            f"changed=False must NOT yield action=updated; got actions={actions}"
        )

    def test_idempotency_gate_normalized_equal_skips_patch(self, monkeypatch, tmp_path):
        """AC-R6/D3 — changed=True but normalized texts equal → action=consolidated; warn consolidated_despite_changed_flag."""
        _patch_decision_ok(monkeypatch, tmp_path)
        existing_text = "TestEntity supports Python."
        # changed=True but same text when normalized
        consolidate_result = _canned_consolidate_result(
            consolidated_text=existing_text + "  ",  # trailing space — normalizes equal
            changed=True,
        )
        mock_consolidate = MagicMock(return_value=consolidate_result)
        mock_extract = MagicMock(return_value=_canned_extract_result())
        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_single_entity_response(
                    name="TestEntity"
                ))
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(201, json=_wikilog_create_response())
            )

            monkeypatch.setattr(
                "anytype_llm_wiki.wiki.remember.consolidate", mock_consolidate, raising=False
            )
            monkeypatch.setattr(
                "anytype_llm_wiki.wiki.remember.extract", mock_extract, raising=False
            )
            monkeypatch.setattr(
                "anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(
                space_id=FAKE_SPACE_ID,
                knowledge="TestEntity supports Python.",
            )

        objects = result.get("objects", [])
        assert objects, "Expected at least one per-object result"
        actions = [o.get("action") for o in objects]
        assert "consolidated" in actions, (
            f"Normalized-equal must yield action=consolidated; got actions={actions}"
        )
        warnings = result.get("warnings", [])
        assert any("consolidated_despite_changed_flag" in str(w) for w in warnings), (
            f"normalized-equal must warn consolidated_despite_changed_flag; warnings={warnings}"
        )

    def test_idempotency_gate_real_change_issues_patch(self, monkeypatch, tmp_path):
        """AC-R3/AC-R4 — changed=True and normalized texts differ → PATCH issued; action=updated."""
        _patch_decision_ok(monkeypatch, tmp_path)
        old_text = "TestEntity supports Python."
        new_text = "TestEntity supports Python 3.12 and now has 8 GB RAM."
        consolidate_result = _canned_consolidate_result(
            consolidated_text=new_text, changed=True,
            fact_actions=[
                {"fact": "TestEntity supports Python.", "action": "keep", "supersedes": None},
                {"fact": "TestEntity now has 8 GB RAM.", "action": "add", "supersedes": None},
            ],
        )
        mock_consolidate = MagicMock(return_value=consolidate_result)
        mock_extract = MagicMock(return_value=_canned_extract_result())
        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)

        patched_calls = []

        def capture_patch(request, **kwargs):
            patched_calls.append(json.loads(request.content))
            return httpx.Response(200, json={"object": {"id": "entity-001"}})

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_single_entity_response(
                    name="TestEntity"
                ))
            )
            router.patch(
                f"/v1/spaces/{FAKE_SPACE_ID}/objects/entity-001"
            ).mock(side_effect=capture_patch)
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(201, json=_wikilog_create_response())
            )

            monkeypatch.setattr(
                "anytype_llm_wiki.wiki.remember.consolidate", mock_consolidate, raising=False
            )
            monkeypatch.setattr(
                "anytype_llm_wiki.wiki.remember.extract", mock_extract, raising=False
            )
            monkeypatch.setattr(
                "anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(
                space_id=FAKE_SPACE_ID,
                knowledge="TestEntity now has 8 GB RAM.",
            )

        objects = result.get("objects", [])
        assert objects, "Expected at least one per-object result"
        actions = [o.get("action") for o in objects]
        assert "updated" in actions, (
            f"Real change must yield action=updated; got actions={actions}"
        )
        assert patched_calls, "PATCH must be issued for a real change"

    def test_remember_twice_converges_no_op(self, monkeypatch, tmp_path):
        """AC-R6/B7 — call wiki_remember twice; call-1 action=created; call-2 action=consolidated;
        ZERO update_object on call-2; stable object_id.
        Uses a STATEFUL mock client that returns call-1 created object on call-2 search.
        """
        _patch_decision_ok(monkeypatch, tmp_path)

        # State shared across both calls
        state = {"created_object": None}
        fact_text = "TestEntity supports Python."

        def stateful_post(request, **kwargs):
            payload = json.loads(request.content)
            type_key = payload.get("type_key", "")
            if type_key == "wiki_entity":
                obj = {"id": "entity-stateful-001", "name": "TestEntity", "spaceId": FAKE_SPACE_ID}
                state["created_object"] = obj
                return httpx.Response(201, json={"object": obj})
            # Source or WikiLog
            return httpx.Response(201, json={"object": {"id": "misc-001", "name": "misc"}})

        def stateful_search(request, **kwargs):
            if state["created_object"] is not None:
                return httpx.Response(200, json={
                    "data": [{
                        "id": state["created_object"]["id"],
                        "name": state["created_object"]["name"],
                        "type": {"key": "wiki_entity"},
                        "properties": [{"key": "wiki_facts", "text": fact_text}],
                    }],
                    "pagination": {"has_more": False},
                })
            return httpx.Response(200, json=_empty_search_response())

        update_calls = []

        def capture_patch(request, **kwargs):
            update_calls.append(json.loads(request.content))
            return httpx.Response(200, json={"object": {"id": "entity-stateful-001"}})

        # consolidate returns same text both times → second call PATCH should be skipped
        mock_consolidate = MagicMock(return_value=_canned_consolidate_result(
            consolidated_text=fact_text, changed=False
        ))
        mock_extract = MagicMock(return_value=_canned_extract_result())
        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                side_effect=stateful_search
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                side_effect=stateful_post
            )
            router.patch(
                f"/v1/spaces/{FAKE_SPACE_ID}/objects/entity-stateful-001"
            ).mock(side_effect=capture_patch)

            monkeypatch.setattr(
                "anytype_llm_wiki.wiki.remember.consolidate", mock_consolidate, raising=False
            )
            monkeypatch.setattr(
                "anytype_llm_wiki.wiki.remember.extract", mock_extract, raising=False
            )
            monkeypatch.setattr(
                "anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember

            result1 = wiki_remember(space_id=FAKE_SPACE_ID, knowledge=fact_text)
            result2 = wiki_remember(space_id=FAKE_SPACE_ID, knowledge=fact_text)

        # Call 1 must create
        objects1 = result1.get("objects", [])
        assert objects1, "Call 1 must produce per-object results"
        assert any(o.get("action") == "created" for o in objects1), (
            f"Call 1 must produce action=created; got {[o.get('action') for o in objects1]}"
        )

        # Call 2 must consolidate (no-op)
        objects2 = result2.get("objects", [])
        assert objects2, "Call 2 must produce per-object results"
        actions2 = [o.get("action") for o in objects2]
        assert "consolidated" in actions2, (
            f"Call 2 must produce action=consolidated; got {actions2}"
        )
        assert "updated" not in actions2, (
            f"Call 2 must NOT produce action=updated on no-op; got {actions2}"
        )

        # Stable object_id
        id1 = objects1[0].get("object_id")
        id2 = objects2[0].get("object_id")
        assert id1 and id1 == id2, (
            f"object_id must be stable across both calls; call1={id1}, call2={id2}"
        )

        # ZERO update_object (PATCH) on call 2
        assert update_calls == [], (
            f"Call 2 must issue ZERO PATCH calls; got {len(update_calls)} patch(es)"
        )


# ---------------------------------------------------------------------------
# §10.3 — Conflict Flagging tests
# ---------------------------------------------------------------------------

class TestConflictFlagging:
    """AC-R5, AC-R15, AC-R28 — conflict detection, WikiLog notes, status-flag."""

    def _make_conflict_consolidate(self):
        return {
            "consolidated_text": (
                "TestEntity uses approach A. [CONFLICT: new claim says approach B]"
            ),
            "changed": True,
            "fact_actions": [
                {"fact": "TestEntity uses approach A.", "action": "conflict", "supersedes": None},
                {"fact": "TestEntity uses approach B.", "action": "conflict", "supersedes": None},
            ],
            "conflicts": [
                {
                    "existing_fact": "TestEntity uses approach A.",
                    "new_fact": "TestEntity uses approach B.",
                    "reason": "contradictory approaches",
                }
            ],
        }

    def _wire_standard_mocks(self, monkeypatch, tmp_path, consolidate_result=None, search_response=None):
        _patch_decision_ok(monkeypatch, tmp_path)
        if consolidate_result is None:
            consolidate_result = self._make_conflict_consolidate()
        if search_response is None:
            search_response = _single_entity_response(name="TestEntity")

        mock_consolidate = MagicMock(return_value=consolidate_result)
        mock_extract = MagicMock(return_value=_canned_extract_result())
        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr(
            "anytype_llm_wiki.wiki.remember.consolidate", mock_consolidate, raising=False
        )
        monkeypatch.setattr(
            "anytype_llm_wiki.wiki.remember.extract", mock_extract, raising=False
        )
        monkeypatch.setattr(
            "anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False
        )
        return mock_consolidate

    def test_conflict_sets_wiki_status_needs_review(self, monkeypatch, tmp_path):
        """AC-R5 — conflicts[] non-empty → update_object payload includes wiki_status needs-review."""
        self._wire_standard_mocks(monkeypatch, tmp_path)

        patch_payloads = []

        def capture_patch(request, **kwargs):
            patch_payloads.append(json.loads(request.content))
            return httpx.Response(200, json={"object": {"id": "entity-001"}})

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_single_entity_response())
            )
            router.patch(f"/v1/spaces/{FAKE_SPACE_ID}/objects/entity-001").mock(
                side_effect=capture_patch
            )
            # Properties + tags lookups
            router.get("/v1/spaces/space-remember-test-001/properties").mock(
                return_value=httpx.Response(200, json=_properties_response(["wiki_status"]))
            )
            router.get(
                url__regex=r".*/v1/spaces/space-remember-test-001/properties/[^/]+/tags(\?.*)?$"
            ).mock(
                return_value=httpx.Response(200, json=_tags_response(["needs-review", "reviewed"]))
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(201, json=_wikilog_create_response())
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(space_id=FAKE_SPACE_ID, knowledge="TestEntity uses approach B.")

        # At least one PATCH must contain wiki_status
        status_patches = [
            p for p in patch_payloads
            if any(
                prop.get("key") == "wiki_status"
                for prop in p.get("properties", [])
            )
        ]
        assert status_patches, (
            f"Conflict must trigger wiki_status PATCH; patches captured: {patch_payloads}"
        )
        # The wiki_status must be a select with tag id containing "needs-review" or "tag-needs-review"
        for prop in status_patches[0].get("properties", []):
            if prop.get("key") == "wiki_status":
                assert prop.get("select") is not None, (
                    f"wiki_status must use 'select' field; got {prop}"
                )

    def test_conflict_does_not_write_wiki_last_reviewed(self, monkeypatch, tmp_path):
        """AC-R5 — conflicted object PATCH does NOT include wiki_last_reviewed."""
        self._wire_standard_mocks(monkeypatch, tmp_path)

        patch_payloads = []

        def capture_patch(request, **kwargs):
            patch_payloads.append(json.loads(request.content))
            return httpx.Response(200, json={"object": {"id": "entity-001"}})

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_single_entity_response())
            )
            router.patch(f"/v1/spaces/{FAKE_SPACE_ID}/objects/entity-001").mock(
                side_effect=capture_patch
            )
            router.get("/v1/spaces/space-remember-test-001/properties").mock(
                return_value=httpx.Response(200, json=_properties_response(["wiki_status"]))
            )
            router.get(
                url__regex=r".*/v1/spaces/space-remember-test-001/properties/[^/]+/tags(\?.*)?$"
            ).mock(
                return_value=httpx.Response(200, json=_tags_response(["needs-review"]))
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(201, json=_wikilog_create_response())
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            wiki_remember(space_id=FAKE_SPACE_ID, knowledge="TestEntity uses approach B.")

        # No PATCH may contain wiki_last_reviewed when conflict
        for p in patch_payloads:
            keys = [prop.get("key") for prop in p.get("properties", [])]
            assert "wiki_last_reviewed" not in keys, (
                f"Conflict PATCH must NOT include wiki_last_reviewed; got {keys}"
            )

    def test_conflict_recorded_in_wikilog_notes(self, monkeypatch, tmp_path):
        """AC-R5 — WikiLog create_object payload includes 'conflicts_flagged: 1' in notes."""
        self._wire_standard_mocks(monkeypatch, tmp_path)

        create_payloads = []

        def capture_post(request, **kwargs):
            payload = json.loads(request.content)
            create_payloads.append(payload)
            type_key = payload.get("type_key", "")
            if type_key == "wiki_log":
                return httpx.Response(201, json=_wikilog_create_response())
            return httpx.Response(201, json=_source_create_response())

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_single_entity_response())
            )
            router.patch(f"/v1/spaces/{FAKE_SPACE_ID}/objects/entity-001").mock(
                return_value=httpx.Response(200, json={"object": {"id": "entity-001"}})
            )
            router.get("/v1/spaces/space-remember-test-001/properties").mock(
                return_value=httpx.Response(200, json=_properties_response(["wiki_status"]))
            )
            router.get(
                url__regex=r".*/v1/spaces/space-remember-test-001/properties/[^/]+/tags(\?.*)?$"
            ).mock(
                return_value=httpx.Response(200, json=_tags_response(["needs-review"]))
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                side_effect=capture_post
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            wiki_remember(space_id=FAKE_SPACE_ID, knowledge="TestEntity uses approach B.")

        # Find the WikiLog payload and check notes
        wikilog_payloads = [p for p in create_payloads if p.get("type_key") == "wiki_log"]
        assert wikilog_payloads, f"No wiki_log create found; payloads: {create_payloads}"
        wl = wikilog_payloads[0]
        props_str = str(wl.get("properties", []))
        assert "conflicts_flagged" in props_str, (
            f"WikiLog properties must mention conflicts_flagged; got {props_str}"
        )

    def test_conflict_in_result_dict(self, monkeypatch, tmp_path):
        """AC-R5 — per-object conflicts_flagged=1; top-level conflicts_flagged=1."""
        self._wire_standard_mocks(monkeypatch, tmp_path)

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_single_entity_response())
            )
            router.patch(f"/v1/spaces/{FAKE_SPACE_ID}/objects/entity-001").mock(
                return_value=httpx.Response(200, json={"object": {"id": "entity-001"}})
            )
            router.get("/v1/spaces/space-remember-test-001/properties").mock(
                return_value=httpx.Response(200, json=_properties_response(["wiki_status"]))
            )
            router.get(
                url__regex=r".*/v1/spaces/space-remember-test-001/properties/[^/]+/tags(\?.*)?$"
            ).mock(
                return_value=httpx.Response(200, json=_tags_response(["needs-review"]))
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(201, json=_wikilog_create_response())
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(space_id=FAKE_SPACE_ID, knowledge="TestEntity uses approach B.")

        assert result.get("conflicts_flagged") == 1, (
            f"Top-level conflicts_flagged must be 1; got {result.get('conflicts_flagged')}"
        )
        objects = result.get("objects", [])
        assert objects, "Expected per-object results"
        assert objects[0].get("conflicts_flagged") == 1, (
            f"Per-object conflicts_flagged must be 1; got {objects[0].get('conflicts_flagged')}"
        )

    def test_no_conflict_updates_wiki_last_reviewed(self, monkeypatch, tmp_path):
        """AC-R3/AC-R4 — no conflicts → PATCH includes wiki_last_reviewed."""
        _patch_decision_ok(monkeypatch, tmp_path)
        # No conflicts, real change
        consolidate_result = _canned_consolidate_result(
            consolidated_text="TestEntity supports Python 3.12.",
            changed=True,
            fact_actions=[{"fact": "TestEntity supports Python 3.12.", "action": "add", "supersedes": None}],
            conflicts=[],
        )
        mock_consolidate = MagicMock(return_value=consolidate_result)
        mock_extract = MagicMock(return_value=_canned_extract_result())
        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.consolidate", mock_consolidate, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.extract", mock_extract, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False)

        patch_payloads = []

        def capture_patch(request, **kwargs):
            patch_payloads.append(json.loads(request.content))
            return httpx.Response(200, json={"object": {"id": "entity-001"}})

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_single_entity_response())
            )
            router.patch(f"/v1/spaces/{FAKE_SPACE_ID}/objects/entity-001").mock(
                side_effect=capture_patch
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(201, json=_wikilog_create_response())
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            wiki_remember(space_id=FAKE_SPACE_ID, knowledge="TestEntity supports Python 3.12.")

        assert patch_payloads, "A real change must issue a PATCH"
        all_patch_keys = [
            prop.get("key")
            for p in patch_payloads
            for prop in p.get("properties", [])
        ]
        assert "wiki_last_reviewed" in all_patch_keys, (
            f"No-conflict PATCH must include wiki_last_reviewed; got keys: {all_patch_keys}"
        )

    def test_conflict_status_tag_absent_degrades(self, monkeypatch, tmp_path):
        """AC-R15 — tag lookup fails → wiki_status NOT written; warning present; write continues."""
        self._wire_standard_mocks(monkeypatch, tmp_path)

        patch_payloads = []

        def capture_patch(request, **kwargs):
            patch_payloads.append(json.loads(request.content))
            return httpx.Response(200, json={"object": {"id": "entity-001"}})

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_single_entity_response())
            )
            router.patch(f"/v1/spaces/{FAKE_SPACE_ID}/objects/entity-001").mock(
                side_effect=capture_patch
            )
            # Return no tags (absent needs-review)
            router.get("/v1/spaces/space-remember-test-001/properties").mock(
                return_value=httpx.Response(200, json=_properties_response(["wiki_status"]))
            )
            router.get(
                url__regex=r".*/v1/spaces/space-remember-test-001/properties/[^/]+/tags(\?.*)?$"
            ).mock(
                return_value=httpx.Response(200, json={"data": [], "pagination": {"has_more": False}})
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(201, json=_wikilog_create_response())
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(space_id=FAKE_SPACE_ID, knowledge="TestEntity uses approach B.")

        # wiki_status must NOT be in any PATCH
        for p in patch_payloads:
            keys = [prop.get("key") for prop in p.get("properties", [])]
            assert "wiki_status" not in keys, (
                f"wiki_status must not be written when tag absent; keys={keys}"
            )
        # Warning must be present
        warnings = result.get("warnings", [])
        assert any("wiki_status_tag_not_found" in str(w) for w in warnings), (
            f"Must warn wiki_status_tag_not_found; warnings={warnings}"
        )
        # Result must still report conflict
        assert result.get("conflicts_flagged", 0) >= 1, (
            f"Conflict must still appear in result even when tag absent; result={result}"
        )

    def test_conflict_never_silently_overwrites(self, monkeypatch, tmp_path):
        """AC-R5 — PATCH payload includes BOTH facts (existing + new) in consolidated_text."""
        self._wire_standard_mocks(monkeypatch, tmp_path)

        patch_payloads = []

        def capture_patch(request, **kwargs):
            patch_payloads.append(json.loads(request.content))
            return httpx.Response(200, json={"object": {"id": "entity-001"}})

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_single_entity_response())
            )
            router.patch(f"/v1/spaces/{FAKE_SPACE_ID}/objects/entity-001").mock(
                side_effect=capture_patch
            )
            router.get("/v1/spaces/space-remember-test-001/properties").mock(
                return_value=httpx.Response(200, json=_properties_response(["wiki_status"]))
            )
            router.get(
                url__regex=r".*/v1/spaces/space-remember-test-001/properties/[^/]+/tags(\?.*)?$"
            ).mock(
                return_value=httpx.Response(200, json=_tags_response(["needs-review"]))
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(201, json=_wikilog_create_response())
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            wiki_remember(space_id=FAKE_SPACE_ID, knowledge="TestEntity uses approach B.")

        # The wiki_facts payload must contain markers for BOTH facts
        all_fact_values = []
        for p in patch_payloads:
            for prop in p.get("properties", []):
                if prop.get("key") in ("wiki_facts", "wiki_definition"):
                    all_fact_values.append(prop.get("text", ""))

        assert all_fact_values, f"Expected wiki_facts PATCH; payloads: {patch_payloads}"
        combined = " ".join(all_fact_values)
        assert "approach A" in combined, (
            f"Existing fact 'approach A' must be in consolidated_text; got: {combined!r}"
        )
        assert "CONFLICT" in combined or "approach B" in combined, (
            f"New fact / conflict marker must appear in consolidated_text; got: {combined!r}"
        )

    def test_conflict_flag_when_patch_skipped(self, monkeypatch, tmp_path):
        """AC-R28/SF1 — already-needs-review entity; text normalizes equal → PATCH skipped;
        action=consolidated; but conflicts_flagged=N and WikiLog note still produced.
        """
        _patch_decision_ok(monkeypatch, tmp_path)
        existing_text = "TestEntity uses approach A. [CONFLICT: approach B]"
        # Consolidate returns same text (no change) + conflict still present
        consolidate_result = {
            "consolidated_text": existing_text,
            "changed": False,
            "fact_actions": [],
            "conflicts": [
                {
                    "existing_fact": "TestEntity uses approach A.",
                    "new_fact": "TestEntity uses approach B.",
                    "reason": "re-asserted contradiction",
                }
            ],
        }
        mock_consolidate = MagicMock(return_value=consolidate_result)
        mock_extract = MagicMock(return_value=_canned_extract_result())
        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.consolidate", mock_consolidate, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.extract", mock_extract, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False)

        text_patch_calls = []
        wikilog_payloads = []

        def capture_post(request, **kwargs):
            payload = json.loads(request.content)
            if payload.get("type_key") == "wiki_log":
                wikilog_payloads.append(payload)
                return httpx.Response(201, json=_wikilog_create_response())
            return httpx.Response(201, json=_source_create_response())

        def capture_patch(request, **kwargs):
            text_patch_calls.append(json.loads(request.content))
            return httpx.Response(200, json={"object": {"id": "entity-001"}})

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_single_entity_response(
                    name="TestEntity",
                ))
            )
            router.patch(f"/v1/spaces/{FAKE_SPACE_ID}/objects/entity-001").mock(
                side_effect=capture_patch
            )
            router.get("/v1/spaces/space-remember-test-001/properties").mock(
                return_value=httpx.Response(200, json=_properties_response(["wiki_status"]))
            )
            router.get(
                url__regex=r".*/v1/spaces/space-remember-test-001/properties/[^/]+/tags(\?.*)?$"
            ).mock(
                return_value=httpx.Response(200, json=_tags_response(["needs-review"]))
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                side_effect=capture_post
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(space_id=FAKE_SPACE_ID, knowledge="TestEntity uses approach B.")

        # Text PATCH must be skipped (changed=False → skip)
        text_patches = [
            p for p in text_patch_calls
            if any(
                prop.get("key") in ("wiki_facts", "wiki_definition")
                for prop in p.get("properties", [])
            )
        ]
        assert not text_patches, (
            f"Text PATCH must be skipped when normalized-equal; text patches: {text_patches}"
        )

        # action=consolidated
        objects = result.get("objects", [])
        assert objects, "Expected per-object result"
        assert any(o.get("action") == "consolidated" for o in objects), (
            f"action must be consolidated when PATCH skipped; got {[o.get('action') for o in objects]}"
        )

        # conflicts_flagged still reported
        assert result.get("conflicts_flagged", 0) >= 1, (
            f"conflicts_flagged must be N even when PATCH skipped; result={result}"
        )

        # WikiLog note still produced
        assert wikilog_payloads, "WikiLog must still be written"
        wikilog_str = str(wikilog_payloads[0].get("properties", []))
        assert "conflicts_flagged" in wikilog_str, (
            f"WikiLog must record conflicts_flagged; got {wikilog_str}"
        )

    def test_reassert_conflict_no_nested_markers(self, monkeypatch, tmp_path):
        """G4 — re-asserting a conflicted entity yields at most one [CONFLICT:] marker per pair."""
        _patch_decision_ok(monkeypatch, tmp_path)
        # The consolidated text from the LLM (what consolidate() returns)
        consolidated_text = (
            "TestEntity uses approach A. [CONFLICT: new claim says approach B]"
        )
        # Only ONE [CONFLICT marker — not doubled
        assert consolidated_text.count("[CONFLICT") == 1, "Test setup error"

        consolidate_result = {
            "consolidated_text": consolidated_text,
            "changed": True,
            "fact_actions": [],
            "conflicts": [
                {
                    "existing_fact": "TestEntity uses approach A.",
                    "new_fact": "approach B",
                    "reason": "contradiction",
                }
            ],
        }
        mock_consolidate = MagicMock(return_value=consolidate_result)
        mock_extract = MagicMock(return_value=_canned_extract_result())
        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.consolidate", mock_consolidate, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.extract", mock_extract, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False)

        patch_payloads = []

        def capture_patch(request, **kwargs):
            patch_payloads.append(json.loads(request.content))
            return httpx.Response(200, json={"object": {"id": "entity-001"}})

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_single_entity_response())
            )
            router.patch(f"/v1/spaces/{FAKE_SPACE_ID}/objects/entity-001").mock(
                side_effect=capture_patch
            )
            router.get("/v1/spaces/space-remember-test-001/properties").mock(
                return_value=httpx.Response(200, json=_properties_response(["wiki_status"]))
            )
            router.get(
                url__regex=r".*/v1/spaces/space-remember-test-001/properties/[^/]+/tags(\?.*)?$"
            ).mock(
                return_value=httpx.Response(200, json=_tags_response(["needs-review"]))
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(201, json=_wikilog_create_response())
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            wiki_remember(space_id=FAKE_SPACE_ID, knowledge="TestEntity uses approach B.")

        # The written text must not double the [CONFLICT marker
        all_fact_values = [
            prop.get("text", "")
            for p in patch_payloads
            for prop in p.get("properties", [])
            if prop.get("key") in ("wiki_facts", "wiki_definition")
        ]
        for v in all_fact_values:
            count = v.count("[CONFLICT")
            assert count <= 1, (
                f"Re-asserted conflict must not create nested [CONFLICT markers; "
                f"count={count}, text={v!r}"
            )

    def test_consolidated_text_sanitized_on_write(self, monkeypatch, tmp_path):
        """AC-R27/B1 — consolidated_text with control/bidi codepoint → wiki_facts written
        equals sanitize_property_value(consolidated_text), not raw LLM output.
        """
        from anytype_llm_wiki.wiki.extraction import sanitize_property_value
        _patch_decision_ok(monkeypatch, tmp_path)

        # Include a zero-width non-joiner (bidi/control codepoint U+200C)
        raw_text = "TestEntity‌ supports Python."
        sanitized = sanitize_property_value(raw_text)
        assert sanitized != raw_text, (
            "Test setup: sanitize_property_value must strip the control codepoint"
        )

        consolidate_result = _canned_consolidate_result(
            consolidated_text=raw_text, changed=True,
        )
        mock_consolidate = MagicMock(return_value=consolidate_result)
        mock_extract = MagicMock(return_value=_canned_extract_result())
        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.consolidate", mock_consolidate, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.extract", mock_extract, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False)

        patch_payloads = []

        def capture_patch(request, **kwargs):
            patch_payloads.append(json.loads(request.content))
            return httpx.Response(200, json={"object": {"id": "entity-001"}})

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_single_entity_response())
            )
            router.patch(f"/v1/spaces/{FAKE_SPACE_ID}/objects/entity-001").mock(
                side_effect=capture_patch
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(201, json=_wikilog_create_response())
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            wiki_remember(space_id=FAKE_SPACE_ID, knowledge="TestEntity supports Python.")

        fact_values = [
            prop.get("text", "")
            for p in patch_payloads
            for prop in p.get("properties", [])
            if prop.get("key") in ("wiki_facts", "wiki_definition")
        ]
        assert fact_values, f"Expected wiki_facts PATCH; payloads: {patch_payloads}"
        for val in fact_values:
            assert val == sanitized, (
                f"wiki_facts must equal sanitize_property_value(consolidated_text) byte-for-byte; "
                f"expected {sanitized!r}, got {val!r}"
            )

    def test_unknown_fact_action_dropped(self, monkeypatch, tmp_path):
        """AC-R27/B1 — fact_actions entry with unknown action is ignored; no spurious status."""
        _patch_decision_ok(monkeypatch, tmp_path)
        consolidate_result = {
            "consolidated_text": "TestEntity supports Python.",
            "changed": True,
            "fact_actions": [
                {"fact": "TestEntity supports Python.", "action": "frobnicate", "supersedes": None},
            ],
            "conflicts": [],
        }
        mock_consolidate = MagicMock(return_value=consolidate_result)
        mock_extract = MagicMock(return_value=_canned_extract_result())
        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.consolidate", mock_consolidate, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.extract", mock_extract, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False)

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_single_entity_response())
            )
            router.patch(f"/v1/spaces/{FAKE_SPACE_ID}/objects/entity-001").mock(
                return_value=httpx.Response(200, json={"object": {"id": "entity-001"}})
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(201, json=_wikilog_create_response())
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(space_id=FAKE_SPACE_ID, knowledge="TestEntity supports Python.")

        # Unknown action must not cause conflicts_flagged to go up
        assert result.get("conflicts_flagged", 0) == 0, (
            f"Unknown fact_action must not flag conflicts; got conflicts_flagged={result.get('conflicts_flagged')}"
        )
        # Status must still be ok/partial (not error)
        assert result.get("status") in ("ok", "partial"), (
            f"Unknown fact_action must not abort; got status={result.get('status')}"
        )


# ---------------------------------------------------------------------------
# §10.4 — Core Pipeline tests
# ---------------------------------------------------------------------------

class TestCorePipeline:
    """AC-R1, AC-R8, AC-R9, AC-R10, AC-R11, AC-R12, AC-R13 — core orchestration."""

    def _base_mocks(self, monkeypatch, tmp_path, extract_result=None, consolidate_result=None):
        _patch_decision_ok(monkeypatch, tmp_path)
        if extract_result is None:
            extract_result = _canned_extract_result()
        if consolidate_result is None:
            consolidate_result = _canned_consolidate_result(changed=False)
        mock_extract = MagicMock(return_value=extract_result)
        mock_consolidate = MagicMock(return_value=consolidate_result)
        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.extract", mock_extract, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.consolidate", mock_consolidate, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False)
        return mock_extract, mock_consolidate

    def test_new_subject_creates_entity(self, monkeypatch, tmp_path):
        """AC-R1 — extraction yields new entity; create_object called; action=created; deeplink."""
        self._base_mocks(monkeypatch, tmp_path)

        create_payloads = []

        def capture_post(request, **kwargs):
            payload = json.loads(request.content)
            create_payloads.append(payload)
            type_key = payload.get("type_key", "")
            if type_key == "wiki_entity":
                return httpx.Response(201, json=_create_object_response(
                    obj_id="new-entity-001", name="TestEntity"
                ))
            if type_key == "wiki_log":
                return httpx.Response(201, json=_wikilog_create_response())
            return httpx.Response(201, json=_source_create_response())

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_empty_search_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                side_effect=capture_post
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(
                space_id=FAKE_SPACE_ID,
                knowledge="TestEntity supports Python.",
            )

        entity_creates = [p for p in create_payloads if p.get("type_key") == "wiki_entity"]
        assert entity_creates, (
            f"wiki_remember must call create_object for a new entity; payloads: {create_payloads}"
        )
        objects = result.get("objects", [])
        assert objects, "Expected per-object result"
        assert any(o.get("action") == "created" for o in objects), (
            f"New entity must have action=created; got {[o.get('action') for o in objects]}"
        )
        # Deeplink format
        for obj in objects:
            if obj.get("action") == "created":
                deeplink = obj.get("deeplink", "")
                assert deeplink.startswith("anytype://object/"), (
                    f"deeplink must start with anytype://object/; got {deeplink!r}"
                )
                assert FAKE_SPACE_ID in deeplink, (
                    f"deeplink must contain space_id; got {deeplink!r}"
                )

    def test_known_subject_consolidates(self, monkeypatch, tmp_path):
        """AC-R2 — resolve_entity returns update → consolidate called; update_object called."""
        self._base_mocks(
            monkeypatch, tmp_path,
            consolidate_result=_canned_consolidate_result(changed=True, consolidated_text="New text.")
        )

        update_calls = []

        def capture_patch(request, **kwargs):
            update_calls.append(json.loads(request.content))
            return httpx.Response(200, json={"object": {"id": "entity-001"}})

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_single_entity_response())
            )
            router.patch(f"/v1/spaces/{FAKE_SPACE_ID}/objects/entity-001").mock(
                side_effect=capture_patch
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(201, json=_wikilog_create_response())
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            wiki_remember(space_id=FAKE_SPACE_ID, knowledge="TestEntity has new facts.")

        assert update_calls, "Known subject with real change must call update_object (PATCH)"
        # wiki_facts must appear in the payload
        fact_keys = [
            prop.get("key")
            for p in update_calls
            for prop in p.get("properties", [])
        ]
        assert "wiki_facts" in fact_keys or "wiki_definition" in fact_keys, (
            f"update_object must contain wiki_facts/wiki_definition; keys: {fact_keys}"
        )

    def test_properties_only_no_body(self, monkeypatch, tmp_path):
        """AC-R8 — no body/markdown key in create_object or update_object payloads."""
        self._base_mocks(
            monkeypatch, tmp_path,
            consolidate_result=_canned_consolidate_result(changed=True, consolidated_text="New text.")
        )

        all_payloads = []

        def capture_any(request, **kwargs):
            payload = json.loads(request.content)
            all_payloads.append(payload)
            type_key = payload.get("type_key", "")
            if type_key == "wiki_entity":
                return httpx.Response(201, json=_create_object_response())
            if type_key == "wiki_log":
                return httpx.Response(201, json=_wikilog_create_response())
            return httpx.Response(201, json=_source_create_response())

        def capture_patch(request, **kwargs):
            all_payloads.append(json.loads(request.content))
            return httpx.Response(200, json={"object": {"id": "entity-001"}})

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_single_entity_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                side_effect=capture_any
            )
            router.patch(f"/v1/spaces/{FAKE_SPACE_ID}/objects/entity-001").mock(
                side_effect=capture_patch
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            wiki_remember(space_id=FAKE_SPACE_ID, knowledge="TestEntity has new facts.")

        for payload in all_payloads:
            assert "body" not in payload, (
                f"wiki_remember must not write body key; found in {payload}"
            )
            assert "markdown" not in payload, (
                f"wiki_remember must not write markdown key; found in {payload}"
            )

    def test_resolve_entity_ignores_wrong_type(self, monkeypatch, tmp_path):
        """AC-R9 — mixed-type search result; wrong-type same-name is NOT matched/updated."""
        self._base_mocks(monkeypatch, tmp_path)

        # Search returns ONLY a wiki_concept with name TestEntity (wrong type for entity extraction)
        wrong_type_response = {
            "data": [
                {
                    "id": "concept-999",
                    "name": "TestEntity",
                    "type": {"key": "wiki_concept"},  # wrong type
                    "properties": [{"key": "wiki_definition", "text": "A concept."}],
                }
            ],
            "pagination": {"has_more": False},
        }

        create_payloads = []

        def capture_post(request, **kwargs):
            payload = json.loads(request.content)
            create_payloads.append(payload)
            if payload.get("type_key") == "wiki_entity":
                return httpx.Response(201, json=_create_object_response())
            if payload.get("type_key") == "wiki_log":
                return httpx.Response(201, json=_wikilog_create_response())
            return httpx.Response(201, json=_source_create_response())

        update_calls = []

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=wrong_type_response)
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                side_effect=capture_post
            )
            router.patch(f"/v1/spaces/{FAKE_SPACE_ID}/objects/concept-999").mock(
                side_effect=lambda req, **kw: update_calls.append(json.loads(req.content))
                or httpx.Response(200, json={"object": {"id": "concept-999"}})
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(space_id=FAKE_SPACE_ID, knowledge="TestEntity supports Python.")

        # The wrong-type object must NOT be patched
        assert not update_calls, (
            f"Wrong-type object must NOT be updated; update_calls: {update_calls}"
        )

    def test_domain_tag_invalid_returns_config_error(self, monkeypatch, tmp_path):
        """AC-R10 — invalid domain_tags → [CONFIG ERROR] invalid_domain_hint before any write."""
        _patch_decision_ok(monkeypatch, tmp_path)
        mock_extract = MagicMock()
        mock_lock = MagicMock()
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.extract", mock_extract, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False)

        create_calls = []

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_empty_search_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                side_effect=lambda req, **kw: create_calls.append(json.loads(req.content))
                or httpx.Response(201, json={"object": {"id": "x"}})
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(
                space_id=FAKE_SPACE_ID,
                knowledge="Some knowledge.",
                domain_tags=["nonexistent_xyz_tag_999"],
            )

        result_str = str(result)
        assert "[CONFIG ERROR]" in result_str or "invalid_domain" in result_str, (
            f"Invalid domain_tag must return [CONFIG ERROR]; got {result_str}"
        )
        assert result.get("status") == "error", (
            f"Invalid domain_tag must return status=error; got {result.get('status')}"
        )
        # No writes must have happened
        mock_extract.assert_not_called()

    def test_schema_outdated_returns_config_error(self, monkeypatch, tmp_path):
        """AC-R11 — live version 0.3.0 with code at 0.3.1 → wiki_schema_outdated."""
        _patch_decision_ok(monkeypatch, tmp_path)

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_outdated_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_empty_search_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(201, json={"object": {"id": "x"}})
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(space_id=FAKE_SPACE_ID, knowledge="Some knowledge.")

        result_str = str(result)
        assert "wiki_schema_outdated" in result_str or "[CONFIG ERROR]" in result_str, (
            f"Outdated schema must return config error; got {result_str}"
        )
        assert result.get("status") == "error", f"Expected status=error; got {result}"

    def test_schema_newer_warns_and_continues(self, monkeypatch, tmp_path):
        """AC-R11 — live version 99.0.0 > code → wiki_schema_newer warning; proceed."""
        self._base_mocks(monkeypatch, tmp_path)

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_newer_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_empty_search_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(201, json=_wikilog_create_response())
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(space_id=FAKE_SPACE_ID, knowledge="TestEntity supports Python.")

        # Must NOT return error
        assert result.get("status") != "error", (
            f"Newer schema must not abort; got status={result.get('status')}"
        )
        warnings = result.get("warnings", [])
        assert any("wiki_schema_newer" in str(w) for w in warnings), (
            f"Must warn wiki_schema_newer; warnings={warnings}"
        )

    def test_wikilog_carries_remember_action(self, monkeypatch, tmp_path):
        """AC-R12 — WikiLog properties include wiki_action select = remember tag id."""
        self._base_mocks(monkeypatch, tmp_path)

        wikilog_payloads = []

        def capture_post(request, **kwargs):
            payload = json.loads(request.content)
            if payload.get("type_key") == "wiki_log":
                wikilog_payloads.append(payload)
                return httpx.Response(201, json=_wikilog_create_response())
            return httpx.Response(201, json=_source_create_response())

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_empty_search_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                side_effect=capture_post
            )
            # Action tag lookup
            router.get("/v1/spaces/space-remember-test-001/properties").mock(
                return_value=httpx.Response(200, json=_properties_response(["wiki_action"]))
            )
            router.get(
                url__regex=r".*/v1/spaces/space-remember-test-001/properties/[^/]+/tags(\?.*)?$"
            ).mock(
                return_value=httpx.Response(200, json=_tags_response(["remember", "ingest"]))
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            wiki_remember(space_id=FAKE_SPACE_ID, knowledge="TestEntity supports Python.")

        assert wikilog_payloads, "WikiLog must be created"
        props = wikilog_payloads[0].get("properties", [])
        action_props = [p for p in props if p.get("key") == "wiki_action"]
        assert action_props, (
            f"WikiLog must contain wiki_action property; props: {props}"
        )
        assert action_props[0].get("select") is not None, (
            f"wiki_action must use select field; got {action_props[0]}"
        )

    def test_wikilog_name_has_remember_prefix(self, monkeypatch, tmp_path):
        """AC-R12/B6 — WikiLog object name == f'remember {subject}'."""
        self._base_mocks(monkeypatch, tmp_path)

        wikilog_names = []

        def capture_post(request, **kwargs):
            payload = json.loads(request.content)
            if payload.get("type_key") == "wiki_log":
                wikilog_names.append(payload.get("name", ""))
                return httpx.Response(201, json=_wikilog_create_response())
            return httpx.Response(201, json=_source_create_response())

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_empty_search_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                side_effect=capture_post
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            wiki_remember(space_id=FAKE_SPACE_ID, knowledge="TestEntity supports Python.")

        assert wikilog_names, "WikiLog must be created"
        for name in wikilog_names:
            assert name.startswith("remember "), (
                f"WikiLog name must start with 'remember '; got {name!r}"
            )

    def test_wikilog_action_tag_absent_degrades(self, monkeypatch, tmp_path):
        """AC-R12 — tag lookup fails → WikiLog written without wiki_action; warning present."""
        self._base_mocks(monkeypatch, tmp_path)

        wikilog_payloads = []

        def capture_post(request, **kwargs):
            payload = json.loads(request.content)
            if payload.get("type_key") == "wiki_log":
                wikilog_payloads.append(payload)
                return httpx.Response(201, json=_wikilog_create_response())
            return httpx.Response(201, json=_source_create_response())

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_empty_search_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                side_effect=capture_post
            )
            # Tags lookup returns empty (action tag absent)
            router.get("/v1/spaces/space-remember-test-001/properties").mock(
                return_value=httpx.Response(200, json=_properties_response(["wiki_action"]))
            )
            router.get(
                url__regex=r".*/v1/spaces/space-remember-test-001/properties/[^/]+/tags(\?.*)?$"
            ).mock(
                return_value=httpx.Response(200, json={"data": [], "pagination": {"has_more": False}})
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(space_id=FAKE_SPACE_ID, knowledge="TestEntity supports Python.")

        assert wikilog_payloads, "WikiLog must still be created even without action tag"
        # wiki_action must NOT be in properties
        for p in wikilog_payloads:
            action_props = [pr for pr in p.get("properties", []) if pr.get("key") == "wiki_action"]
            assert not action_props, (
                f"WikiLog must not carry wiki_action when tag absent; props: {p.get('properties')}"
            )
        warnings = result.get("warnings", [])
        assert any("wiki_action_tag_not_found" in str(w) for w in warnings), (
            f"Must warn wiki_action_tag_not_found; warnings={warnings}"
        )

    def test_source_created_with_source_type(self, monkeypatch, tmp_path):
        """AC-R13 — Source object created; wiki_source_type select present when tag exists."""
        self._base_mocks(monkeypatch, tmp_path)

        source_payloads = []
        entity_ids = {"created": None}

        def capture_post(request, **kwargs):
            payload = json.loads(request.content)
            type_key = payload.get("type_key", "")
            if type_key == "wiki_entity":
                entity_ids["created"] = "entity-src-001"
                return httpx.Response(201, json=_create_object_response("entity-src-001", "TestEntity"))
            if type_key == "wiki_source":
                source_payloads.append(payload)
                return httpx.Response(201, json=_source_create_response())
            if type_key == "wiki_log":
                return httpx.Response(201, json=_wikilog_create_response())
            return httpx.Response(201, json={"object": {"id": "x", "name": "x"}})

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_empty_search_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                side_effect=capture_post
            )
            router.patch(f"/v1/spaces/{FAKE_SPACE_ID}/objects/entity-src-001").mock(
                return_value=httpx.Response(200, json={"object": {"id": "entity-src-001"}})
            )
            router.get("/v1/spaces/space-remember-test-001/properties").mock(
                return_value=httpx.Response(200, json=_properties_response(["wiki_source_type"]))
            )
            router.get(
                url__regex=r".*/v1/spaces/space-remember-test-001/properties/[^/]+/tags(\?.*)?$"
            ).mock(
                return_value=httpx.Response(200, json=_tags_response(["agent", "conversation"]))
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(
                space_id=FAKE_SPACE_ID,
                knowledge="TestEntity supports Python.",
                source="agent task output",
            )

        assert source_payloads, (
            f"Source object must be created when ≥1 entity written; payloads: {source_payloads}"
        )
        props = source_payloads[0].get("properties", [])
        source_type_props = [p for p in props if p.get("key") == "wiki_source_type"]
        assert source_type_props, (
            f"wiki_source_type must be present when tag found; props: {props}"
        )
        assert source_type_props[0].get("select") is not None, (
            f"wiki_source_type must use select; got {source_type_props[0]}"
        )

    def test_source_created_without_source_type_when_tag_absent(self, monkeypatch, tmp_path):
        """AC-R18 — Source created; no wiki_source_type; warning present when tag absent."""
        self._base_mocks(monkeypatch, tmp_path)

        source_payloads = []

        def capture_post(request, **kwargs):
            payload = json.loads(request.content)
            type_key = payload.get("type_key", "")
            if type_key == "wiki_entity":
                return httpx.Response(201, json=_create_object_response("entity-r-002", "TestEntity"))
            if type_key == "wiki_source":
                source_payloads.append(payload)
                return httpx.Response(201, json=_source_create_response())
            if type_key == "wiki_log":
                return httpx.Response(201, json=_wikilog_create_response())
            return httpx.Response(201, json={"object": {"id": "x", "name": "x"}})

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_empty_search_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                side_effect=capture_post
            )
            router.patch(f"/v1/spaces/{FAKE_SPACE_ID}/objects/entity-r-002").mock(
                return_value=httpx.Response(200, json={"object": {"id": "entity-r-002"}})
            )
            # Tags lookup returns empty (source_type tag absent)
            router.get("/v1/spaces/space-remember-test-001/properties").mock(
                return_value=httpx.Response(200, json=_properties_response(["wiki_source_type"]))
            )
            router.get(
                url__regex=r".*/v1/spaces/space-remember-test-001/properties/[^/]+/tags(\?.*)?$"
            ).mock(
                return_value=httpx.Response(200, json={"data": [], "pagination": {"has_more": False}})
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(space_id=FAKE_SPACE_ID, knowledge="TestEntity supports Python.")

        assert source_payloads, "Source must still be created even when source_type tag absent"
        # wiki_source_type must NOT be in properties
        for p in source_payloads:
            type_props = [pr for pr in p.get("properties", []) if pr.get("key") == "wiki_source_type"]
            assert not type_props, (
                f"wiki_source_type must not be written when tag absent; props: {p.get('properties')}"
            )
        warnings = result.get("warnings", [])
        assert any("wiki_source_type_tag_not_found" in str(w) for w in warnings), (
            f"Must warn wiki_source_type_tag_not_found; warnings={warnings}"
        )

    def test_source_linked_on_entity_via_wiki_sources(self, monkeypatch, tmp_path):
        """AC-R13 — update_object call includes wiki_sources: [source_id] for existing entity."""
        self._base_mocks(
            monkeypatch, tmp_path,
            consolidate_result=_canned_consolidate_result(changed=True, consolidated_text="Updated text.")
        )

        patch_payloads = []
        source_id = "source-link-001"

        def capture_post(request, **kwargs):
            payload = json.loads(request.content)
            if payload.get("type_key") == "wiki_source":
                return httpx.Response(201, json={"object": {"id": source_id, "name": "source"}})
            if payload.get("type_key") == "wiki_log":
                return httpx.Response(201, json=_wikilog_create_response())
            return httpx.Response(201, json={"object": {"id": "x", "name": "x"}})

        def capture_patch(request, **kwargs):
            patch_payloads.append(json.loads(request.content))
            return httpx.Response(200, json={"object": {"id": "entity-001"}})

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_single_entity_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                side_effect=capture_post
            )
            router.patch(f"/v1/spaces/{FAKE_SPACE_ID}/objects/entity-001").mock(
                side_effect=capture_patch
            )
            router.get("/v1/spaces/space-remember-test-001/properties").mock(
                return_value=httpx.Response(200, json=_properties_response(["wiki_source_type"]))
            )
            router.get(
                url__regex=r".*/v1/spaces/space-remember-test-001/properties/[^/]+/tags(\?.*)?$"
            ).mock(
                return_value=httpx.Response(200, json=_tags_response(["agent"]))
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            wiki_remember(space_id=FAKE_SPACE_ID, knowledge="TestEntity has more facts.")

        # Some patch must include wiki_sources with the source id
        all_sources_props = [
            prop
            for p in patch_payloads
            for prop in p.get("properties", [])
            if prop.get("key") == "wiki_sources"
        ]
        assert all_sources_props, (
            f"wiki_sources must be in PATCH; payloads: {patch_payloads}"
        )
        sources_vals = all_sources_props[0].get("objects", [])
        assert source_id in sources_vals, (
            f"wiki_sources must include source_id={source_id}; got {sources_vals}"
        )

    def test_subject_hint_used_when_extraction_yields_nothing(self, monkeypatch, tmp_path):
        """AC-R1/D9 — extraction empty + subject_hint → entity created with hint as title."""
        _patch_decision_ok(monkeypatch, tmp_path)
        # Extract returns nothing
        mock_extract = MagicMock(return_value={"entities": [], "concepts": []})
        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.extract", mock_extract, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False)

        create_payloads = []

        def capture_post(request, **kwargs):
            payload = json.loads(request.content)
            create_payloads.append(payload)
            return httpx.Response(201, json=_create_object_response("hint-entity-001", "HintSubject"))

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_empty_search_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                side_effect=capture_post
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(
                space_id=FAKE_SPACE_ID,
                knowledge="HintSubject does something interesting.",
                subject_hint="HintSubject",
            )

        entity_creates = [
            p for p in create_payloads if p.get("type_key") in ("wiki_entity", "wiki_concept")
        ]
        assert entity_creates, (
            f"subject_hint must trigger entity creation when extraction empty; payloads: {create_payloads}"
        )
        names = [p.get("name", "") for p in entity_creates]
        assert any("HintSubject" in n for n in names), (
            f"Created entity must use subject_hint as title; names: {names}"
        )

    def test_no_subjects_no_hint_returns_partial(self, monkeypatch, tmp_path):
        """D9 — extraction empty + no hint → status=partial; no objects created."""
        _patch_decision_ok(monkeypatch, tmp_path)
        mock_extract = MagicMock(return_value={"entities": [], "concepts": []})
        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.extract", mock_extract, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False)

        create_calls = []

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_empty_search_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                side_effect=lambda req, **kw: create_calls.append(json.loads(req.content))
                or httpx.Response(201, json={"object": {"id": "x", "name": "x"}})
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(space_id=FAKE_SPACE_ID, knowledge="Nothing specific.")

        entity_creates = [
            p for p in create_calls if p.get("type_key") in ("wiki_entity", "wiki_concept")
        ]
        assert not entity_creates, (
            f"No entity must be created when extraction empty + no hint; creates: {entity_creates}"
        )
        assert result.get("status") == "partial", (
            f"Empty extraction without hint must return status=partial; got {result.get('status')}"
        )
        warnings = result.get("warnings", [])
        assert any("no_subjects" in str(w) for w in warnings), (
            f"Must warn about no subjects; warnings={warnings}"
        )

    def test_kind_fallback_to_entity_for_subject_hint(self, monkeypatch, tmp_path):
        """D9 — kind=None + subject_hint + empty extraction → wiki_entity type used."""
        _patch_decision_ok(monkeypatch, tmp_path)
        mock_extract = MagicMock(return_value={"entities": [], "concepts": []})
        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.extract", mock_extract, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False)

        create_payloads = []

        def capture_post(request, **kwargs):
            payload = json.loads(request.content)
            create_payloads.append(payload)
            return httpx.Response(201, json=_create_object_response("entity-kind-001", "MyEntity"))

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_empty_search_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                side_effect=capture_post
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            wiki_remember(
                space_id=FAKE_SPACE_ID,
                knowledge="MyEntity does things.",
                subject_hint="MyEntity",
                kind=None,
            )

        entity_creates = [p for p in create_payloads if p.get("type_key") == "wiki_entity"]
        assert entity_creates, (
            f"kind=None + hint must create wiki_entity; payloads: {create_payloads}"
        )

    def test_kind_concept_fallback_creates_concept(self, monkeypatch, tmp_path):
        """D9/B5 — kind='concept' + subject_hint + empty extraction → wiki_concept created; wiki_definition."""
        _patch_decision_ok(monkeypatch, tmp_path)
        mock_extract = MagicMock(return_value={"entities": [], "concepts": []})
        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.extract", mock_extract, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False)

        create_payloads = []

        def capture_post(request, **kwargs):
            payload = json.loads(request.content)
            create_payloads.append(payload)
            type_key = payload.get("type_key", "")
            if type_key == "wiki_concept":
                return httpx.Response(201, json=_create_object_response("concept-kind-001", "MyConcept"))
            return httpx.Response(201, json={"object": {"id": "misc-001", "name": "misc"}})

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_empty_search_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                side_effect=capture_post
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            wiki_remember(
                space_id=FAKE_SPACE_ID,
                knowledge="MyConcept is about abstraction.",
                subject_hint="MyConcept",
                kind="concept",
            )

        concept_creates = [p for p in create_payloads if p.get("type_key") == "wiki_concept"]
        assert concept_creates, (
            f"kind='concept' + hint must create wiki_concept; payloads: {create_payloads}"
        )
        # wiki_definition must be in properties
        props = concept_creates[0].get("properties", [])
        definition_props = [p for p in props if p.get("key") == "wiki_definition"]
        assert definition_props, (
            f"wiki_concept must include wiki_definition property; props: {props}"
        )

    def test_ollama_not_pulled_aborts_before_source_creation(self, monkeypatch, tmp_path):
        """AC-R14 — extract() returns model_not_pulled → error returned; no source create_object."""
        _patch_decision_ok(monkeypatch, tmp_path)
        mock_extract = MagicMock(return_value="[CONFIG ERROR] ollama_model_not_pulled")
        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.extract", mock_extract, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False)

        create_calls = []

        def capture_post(request, **kwargs):
            payload = json.loads(request.content)
            create_calls.append(payload)
            return httpx.Response(201, json={"object": {"id": "x", "name": "x"}})

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_empty_search_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                side_effect=capture_post
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(space_id=FAKE_SPACE_ID, knowledge="Some knowledge.")

        result_str = str(result)
        assert "ollama_model_not_pulled" in result_str or "[CONFIG ERROR]" in result_str, (
            f"Model not pulled must return error; got {result_str}"
        )
        source_creates = [p for p in create_calls if p.get("type_key") == "wiki_source"]
        assert not source_creates, (
            f"Source must NOT be created when model_not_pulled; creates: {source_creates}"
        )

    def test_reindex_failure_is_nonfatal(self, monkeypatch, tmp_path):
        """AC-R16 — reindex raises → status ok/partial; warning present."""
        self._base_mocks(monkeypatch, tmp_path)

        def fail_reindex(*args, **kwargs):
            raise RuntimeError("Qdrant unreachable")

        monkeypatch.setattr(
            "anytype_llm_wiki.wiki.remember._maybe_reindex", fail_reindex, raising=False
        )

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_empty_search_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(201, json=_wikilog_create_response())
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(space_id=FAKE_SPACE_ID, knowledge="TestEntity supports Python.")

        assert result.get("status") in ("ok", "partial"), (
            f"Reindex failure must not abort; got status={result.get('status')}"
        )
        warnings = result.get("warnings", [])
        assert any("reindex_failed" in str(w) for w in warnings), (
            f"Must warn reindex_failed; warnings={warnings}"
        )

    def test_consolidation_degraded_skips_patch(self, monkeypatch, tmp_path):
        """AC-R17 — degraded consolidation → no update_object; action=consolidation_degraded; status=partial."""
        _patch_decision_ok(monkeypatch, tmp_path)
        degraded_result = {
            "consolidated_text": "TestEntity supports Python.",
            "changed": False,
            "fact_actions": [],
            "conflicts": [],
            "error": "consolidation_degraded: LLM timeout",
        }
        mock_consolidate = MagicMock(return_value=degraded_result)
        mock_extract = MagicMock(return_value=_canned_extract_result())
        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.consolidate", mock_consolidate, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.extract", mock_extract, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False)

        update_calls = []

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_single_entity_response())
            )
            router.patch(f"/v1/spaces/{FAKE_SPACE_ID}/objects/entity-001").mock(
                side_effect=lambda req, **kw: update_calls.append(json.loads(req.content))
                or httpx.Response(200, json={"object": {"id": "entity-001"}})
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(201, json=_wikilog_create_response())
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(space_id=FAKE_SPACE_ID, knowledge="TestEntity supports Python.")

        text_patches = [
            p for p in update_calls
            if any(
                pr.get("key") in ("wiki_facts", "wiki_definition")
                for pr in p.get("properties", [])
            )
        ]
        assert not text_patches, (
            f"Degraded consolidation must not issue wiki_facts PATCH; patches: {text_patches}"
        )
        objects = result.get("objects", [])
        assert objects, "Expected per-object result"
        actions = [o.get("action") for o in objects]
        assert "consolidation_degraded" in actions, (
            f"Degraded consolidation must yield action=consolidation_degraded; got {actions}"
        )
        assert result.get("status") == "partial", (
            f"Degraded consolidation must yield status=partial; got {result.get('status')}"
        )

    def test_total_degrade_creates_no_source(self, monkeypatch, tmp_path):
        """AC-R17/SF10 — zero objects written → no source create_object; source_object_id=None."""
        _patch_decision_ok(monkeypatch, tmp_path)
        degraded_result = {
            "consolidated_text": "TestEntity supports Python.",
            "changed": False,
            "fact_actions": [],
            "conflicts": [],
            "error": "consolidation_degraded: parse failure",
        }
        mock_consolidate = MagicMock(return_value=degraded_result)
        mock_extract = MagicMock(return_value=_canned_extract_result())
        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.consolidate", mock_consolidate, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.extract", mock_extract, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False)

        create_calls = []

        def capture_post(request, **kwargs):
            payload = json.loads(request.content)
            create_calls.append(payload)
            return httpx.Response(201, json={"object": {"id": "x", "name": "x"}})

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            # Existing entity found → consolidation attempted (and degrades)
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_single_entity_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                side_effect=capture_post
            )
            router.patch(f"/v1/spaces/{FAKE_SPACE_ID}/objects/entity-001").mock(
                return_value=httpx.Response(200, json={"object": {"id": "entity-001"}})
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(space_id=FAKE_SPACE_ID, knowledge="TestEntity supports Python.")

        source_creates = [p for p in create_calls if p.get("type_key") == "wiki_source"]
        assert not source_creates, (
            f"No source must be created when zero objects written (total degrade); creates: {source_creates}"
        )
        assert result.get("source_object_id") is None, (
            f"source_object_id must be None on total degrade; got {result.get('source_object_id')}"
        )

    def test_one_subject_write_fails_others_succeed(self, monkeypatch, tmp_path):
        """SF11 — one per-object write raises; that object action=error; others succeed; status=partial."""
        _patch_decision_ok(monkeypatch, tmp_path)
        # Extract returns two entities
        mock_extract = MagicMock(return_value={
            "entities": [
                {"name": "GoodEntity", "kind": "entity", "facts": "Good facts."},
                {"name": "BadEntity", "kind": "entity", "facts": "Bad facts."},
            ],
            "concepts": [],
        })
        mock_consolidate = MagicMock(return_value=_canned_consolidate_result(changed=False))
        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.extract", mock_extract, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.consolidate", mock_consolidate, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False)

        post_count = {"n": 0}

        def selective_post(request, **kwargs):
            payload = json.loads(request.content)
            type_key = payload.get("type_key", "")
            if type_key == "wiki_entity":
                post_count["n"] += 1
                name = payload.get("name", "")
                if "Bad" in name:
                    return httpx.Response(500, json={"error": "server error"})
                return httpx.Response(201, json=_create_object_response(
                    f"entity-{post_count['n']}", name
                ))
            if type_key == "wiki_log":
                return httpx.Response(201, json=_wikilog_create_response())
            return httpx.Response(201, json=_source_create_response())

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_empty_search_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                side_effect=selective_post
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(space_id=FAKE_SPACE_ID, knowledge="GoodEntity and BadEntity.")

        objects = result.get("objects", [])
        actions = [o.get("action") for o in objects]
        assert "error" in actions, f"Failed object must have action=error; got {actions}"
        # At least one must succeed
        assert any(a in ("created", "updated", "consolidated") for a in actions), (
            f"At least one subject must succeed; got actions={actions}"
        )
        assert result.get("status") == "partial", (
            f"One-failed must yield status=partial; got {result.get('status')}"
        )
        # Error object must have error key
        error_objects = [o for o in objects if o.get("action") == "error"]
        for eo in error_objects:
            assert "error" in eo, f"Error-action object must have 'error' key; got {eo}"

    def test_ambiguous_subject_skips_and_warns(self, monkeypatch, tmp_path):
        """AC-R29/B9 — >1 same-name same-type candidates → action=error; no update_object; status=partial;
        co-resident unambiguous subject still writes.

        The search mock is SUBJECT-AWARE: AmbigEntity returns 2 same-type same-name
        rows (ambiguous), while ClearEntity returns exactly 1 distinct row (unambiguous).
        This proves both that the ambiguous subject is skipped AND that the unambiguous
        co-resident subject is still processed (writes its update/create).
        """
        _patch_decision_ok(monkeypatch, tmp_path)
        mock_extract = MagicMock(return_value={
            "entities": [
                {"name": "AmbigEntity", "kind": "entity", "facts": "Facts."},
                {"name": "ClearEntity", "kind": "entity", "facts": "Clear facts."},
            ],
            "concepts": [],
        })
        # changed=True so the impl will issue a PATCH for ClearEntity, proving the write
        mock_consolidate = MagicMock(return_value=_canned_consolidate_result(changed=True))
        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.extract", mock_extract, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.consolidate", mock_consolidate, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False)

        # Separate capture lists: ambiguous candidates vs the unambiguous ClearEntity
        ambig_update_calls = []
        clear_update_calls = []

        def search_side_effect(request, **kwargs):
            """Subject-aware search mock.

            Inspects the request body (POST) or URL query params (GET) for the
            subject name being resolved, so each subject sees a distinct result set:
            - "AmbigEntity" → 2 same-name same-type rows (triggers ambiguity handling)
            - "ClearEntity"  → 1 distinct row (unambiguous; proceeds to consolidate)
            - anything else  → empty (new object)
            """
            # Support both POST body ({"query": "..."}) and GET query param (?query=...)
            query_text = ""
            try:
                body = json.loads(request.content)
                query_text = body.get("query", "")
            except Exception:
                pass
            if not query_text:
                from urllib.parse import urlparse, parse_qs
                parsed = urlparse(str(request.url))
                params = parse_qs(parsed.query)
                query_text = params.get("query", [""])[0]

            if "AmbigEntity" in query_text:
                return httpx.Response(200, json={
                    "data": [
                        {"id": "ambig-1", "name": "AmbigEntity", "type": {"key": "wiki_entity"},
                         "properties": [{"key": "wiki_facts", "text": "Facts."}]},
                        {"id": "ambig-2", "name": "AmbigEntity", "type": {"key": "wiki_entity"},
                         "properties": [{"key": "wiki_facts", "text": "Facts v2."}]},
                    ],
                    "pagination": {"has_more": False},
                })
            if "ClearEntity" in query_text:
                return httpx.Response(200, json={
                    "data": [
                        {"id": "clear-001", "name": "ClearEntity", "type": {"key": "wiki_entity"},
                         "properties": [{"key": "wiki_facts", "text": "Old clear facts."}]},
                    ],
                    "pagination": {"has_more": False},
                })
            return httpx.Response(200, json={"data": [], "pagination": {"has_more": False}})

        def capture_post(request, **kwargs):
            payload = json.loads(request.content)
            if payload.get("type_key") == "wiki_entity":
                return httpx.Response(201, json=_create_object_response("clear-001", payload.get("name", "")))
            if payload.get("type_key") == "wiki_log":
                return httpx.Response(201, json=_wikilog_create_response())
            return httpx.Response(201, json=_source_create_response())

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                side_effect=search_side_effect
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                side_effect=capture_post
            )
            # Ambiguous-candidate patches — must NOT be called
            router.patch(f"/v1/spaces/{FAKE_SPACE_ID}/objects/ambig-1").mock(
                side_effect=lambda req, **kw: ambig_update_calls.append(json.loads(req.content))
                or httpx.Response(200, json={"object": {"id": "ambig-1"}})
            )
            router.patch(f"/v1/spaces/{FAKE_SPACE_ID}/objects/ambig-2").mock(
                side_effect=lambda req, **kw: ambig_update_calls.append(json.loads(req.content))
                or httpx.Response(200, json={"object": {"id": "ambig-2"}})
            )
            # Unambiguous ClearEntity patch — MUST be called exactly once
            router.patch(f"/v1/spaces/{FAKE_SPACE_ID}/objects/clear-001").mock(
                side_effect=lambda req, **kw: clear_update_calls.append(json.loads(req.content))
                or httpx.Response(200, json={"object": {"id": "clear-001"}})
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(
                space_id=FAKE_SPACE_ID,
                knowledge="AmbigEntity and ClearEntity facts.",
            )

        # Ambiguous subject must NOT be updated
        assert not ambig_update_calls, (
            f"Ambiguous subject must NOT trigger update_object; ambig_update_calls: {ambig_update_calls}"
        )

        # Unambiguous co-resident subject (ClearEntity) MUST produce exactly one write
        assert len(clear_update_calls) == 1, (
            f"Unambiguous co-resident ClearEntity must produce exactly 1 write (update_object); "
            f"got {len(clear_update_calls)} write(s): {clear_update_calls}"
        )

        objects = result.get("objects", [])
        error_objects = [o for o in objects if o.get("action") == "error"]
        assert error_objects, (
            f"Ambiguous subject must produce action=error per-object; got {objects}"
        )
        for eo in error_objects:
            assert eo.get("error") == "ambiguous_subject", (
                f"error key must be 'ambiguous_subject'; got {eo.get('error')!r}"
            )

        warnings = result.get("warnings", [])
        assert any("ambiguous_subject" in str(w) for w in warnings), (
            f"Must warn ambiguous_subject; warnings={warnings}"
        )
        assert result.get("status") == "partial", (
            f"Ambiguous subject must yield status=partial; got {result.get('status')}"
        )

    def test_all_subjects_processed_no_cap(self, monkeypatch, tmp_path):
        """No-drop guarantee: >8 extracted subjects are ALL processed — no fixed
        subject cap, no subject_cap_exceeded warning, no cap-induced partial."""
        _patch_decision_ok(monkeypatch, tmp_path)
        # Extract returns 10 entities (>8)
        entities = [
            {"name": f"Entity{i}", "kind": "entity", "facts": f"Facts about Entity{i}."}
            for i in range(10)
        ]
        mock_extract = MagicMock(return_value={"entities": entities, "concepts": []})
        mock_consolidate = MagicMock(return_value=_canned_consolidate_result(changed=False))
        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.extract", mock_extract, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.consolidate", mock_consolidate, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False)

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            # Return empty search → all entities are new (action=created, no consolidation needed)
            # But we want consolidation, so return one existing entity for all searches
            entity_count = {"n": 0}

            def search_side(request, **kwargs):
                entity_count["n"] += 1
                # Return existing entity for first 10 searches so consolidation is attempted
                return httpx.Response(200, json={
                    "data": [{
                        "id": f"entity-{entity_count['n']:03d}",
                        "name": f"Entity{entity_count['n'] - 1}",
                        "type": {"key": "wiki_entity"},
                        "properties": [{"key": "wiki_facts", "text": "Old facts."}],
                    }],
                    "pagination": {"has_more": False},
                })

            router.post("/v1/spaces/space-remember-test-001/search").mock(
                side_effect=search_side
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(201, json=_wikilog_create_response())
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(
                space_id=FAKE_SPACE_ID,
                knowledge=" ".join(f"Entity{i} does things." for i in range(10)),
            )

        # All 10 subjects must be processed — the cap (which dropped >8) is gone.
        assert len(result.get("objects", [])) == 10, (
            f"All 10 subjects must be processed; got {len(result.get('objects', []))} "
            f"objects: {result.get('objects')}"
        )
        warnings = result.get("warnings", [])
        assert not any("subject_cap_exceeded" in str(w) for w in warnings), (
            f"subject_cap_exceeded must NOT be warned anymore; warnings={warnings}"
        )

    def test_interrupted_drain_resumes_pending_subjects(self, monkeypatch, tmp_path):
        """No-loss across interruption: a drain that crashes mid-way leaves its
        subjects in the durable work-log; the next run folds them back in and
        finishes them. Nothing is dropped."""
        _patch_decision_ok(monkeypatch, tmp_path)
        from anytype_llm_wiki.wiki import worklog

        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr(
            "anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False
        )
        # Keep the test hermetic — no live qdrant/indexer reindex on the success phase.
        monkeypatch.setattr(
            "anytype_llm_wiki.wiki.remember._maybe_reindex",
            lambda *a, **k: None, raising=False,
        )

        entities = [
            {"name": "Xeno", "kind": "entity", "facts": "about Xeno"},
            {"name": "Yara", "kind": "entity", "facts": "about Yara"},
        ]
        monkeypatch.setattr(
            "anytype_llm_wiki.wiki.remember.extract",
            MagicMock(return_value={"entities": entities, "concepts": []}),
            raising=False,
        )

        # ---- Phase 1: crash mid-drain (resolve_entity raises an uncaught error) ----
        monkeypatch.setattr(
            "anytype_llm_wiki.wiki.remember.resolve_entity",
            MagicMock(side_effect=RuntimeError("simulated crash")),
            raising=False,
        )
        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(201, json=_wikilog_create_response())
            )
            from anytype_llm_wiki.wiki.remember import wiki_remember
            wiki_remember(space_id=FAKE_SPACE_ID, knowledge="Xeno and Yara exist.")

        pending = worklog.load_pending(FAKE_SPACE_ID)
        assert sorted(p["name"] for p in pending) == ["Xeno", "Yara"], (
            f"Both subjects must survive the crash in the durable log; got {pending}"
        )

        # ---- Phase 2: a fresh run resumes and finishes the pending subjects ----
        # New extraction is empty, so the ONLY work is the resumed pending pair.
        monkeypatch.setattr(
            "anytype_llm_wiki.wiki.remember.extract",
            MagicMock(return_value={"entities": [], "concepts": []}),
            raising=False,
        )
        monkeypatch.setattr(
            "anytype_llm_wiki.wiki.remember.resolve_entity",
            MagicMock(return_value={"action": "create"}),
            raising=False,
        )
        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(201, json=_wikilog_create_response())
            )
            result = wiki_remember(
                space_id=FAKE_SPACE_ID, knowledge="(nothing new to extract)"
            )

        # In the queue-submit model, resuming pending subjects IS the normal drain
        # path — the next holder simply drains whatever's in the log.
        processed = {o["title"] for o in result.get("objects", [])}
        assert processed == {"Xeno", "Yara"}, (
            f"Both pending subjects must be processed on resume; got {processed}"
        )
        assert worklog.load_pending(FAKE_SPACE_ID) == [], (
            "Work-log must be drained (and compacted) after a successful resume"
        )

    def test_worklog_failure_degrades_without_dropping_subjects(self, monkeypatch, tmp_path):
        """Degraded mode (M4): when the durable work-log itself fails (OSError on
        begin), every subject is STILL processed in-process — never dropped — and
        the run only warns that crash-resume isn't guaranteed."""
        _patch_decision_ok(monkeypatch, tmp_path)

        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr(
            "anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False
        )
        monkeypatch.setattr(
            "anytype_llm_wiki.wiki.remember._maybe_reindex", lambda *a, **k: None, raising=False
        )
        entities = [
            {"name": f"Deg{i}", "kind": "entity", "facts": f"facts {i}"} for i in range(5)
        ]
        monkeypatch.setattr(
            "anytype_llm_wiki.wiki.remember.extract",
            MagicMock(return_value={"entities": entities, "concepts": []}), raising=False,
        )
        monkeypatch.setattr(
            "anytype_llm_wiki.wiki.remember.resolve_entity",
            MagicMock(return_value={"action": "create"}), raising=False,
        )
        # The work-log is unavailable: begin raises OSError.
        import anytype_llm_wiki.wiki.remember as _rmod
        monkeypatch.setattr(
            _rmod.worklog, "begin",
            MagicMock(side_effect=OSError("disk full")), raising=False,
        )

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(201, json=_wikilog_create_response())
            )
            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(space_id=FAKE_SPACE_ID, knowledge="five degraded subjects")

        # All 5 subjects processed despite the work-log being down — NO drop.
        assert len(result.get("objects", [])) == 5, (
            f"Degraded work-log must not drop subjects; got {result.get('objects')}"
        )
        assert any("worklog_begin_failed" in str(w) for w in result.get("warnings", [])), (
            f"Degraded run must warn worklog_begin_failed; warnings={result.get('warnings')}"
        )

    def test_errored_subject_marked_done_does_not_resume_forever(self, monkeypatch, tmp_path):
        """A subject whose write hits a deterministic, caught API error (M4) is
        marked done and does NOT linger in the work-log to be retried forever."""
        _patch_decision_ok(monkeypatch, tmp_path)
        from anytype_llm_wiki.wiki import worklog

        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr(
            "anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False
        )
        monkeypatch.setattr(
            "anytype_llm_wiki.wiki.remember._maybe_reindex", lambda *a, **k: None, raising=False
        )
        monkeypatch.setattr(
            "anytype_llm_wiki.wiki.remember.extract",
            MagicMock(return_value={"entities": [
                {"name": "Boom", "kind": "entity", "facts": "f"}], "concepts": []}),
            raising=False,
        )
        # resolve_entity raises a CAUGHT error (ValueError) → per-subject error path.
        monkeypatch.setattr(
            "anytype_llm_wiki.wiki.remember.resolve_entity",
            MagicMock(side_effect=ValueError("deterministic API error")), raising=False,
        )

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(201, json=_wikilog_create_response())
            )
            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(space_id=FAKE_SPACE_ID, knowledge="boom")

        assert result.get("status") == "partial", result
        assert any(o.get("action") == "error" for o in result.get("objects", [])), result
        # The errored subject must be marked done + compacted away — not resumed.
        assert worklog.load_pending(FAKE_SPACE_ID) == [], (
            "A deterministically-erroring subject must be marked done, not left pending"
        )

    def test_drain_until_dry_sweeps_concurrent_append(self, monkeypatch, tmp_path):
        """The holder's drain-until-dry sweeps up a subject appended to the work-log
        by another PID *during* the drain — the guarantee that a contender's queued
        work is applied by the current holder, not left for a future submit."""
        _patch_decision_ok(monkeypatch, tmp_path)
        from anytype_llm_wiki.wiki import worklog

        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember._maybe_reindex", lambda *a, **k: None, raising=False)
        monkeypatch.setattr(
            "anytype_llm_wiki.wiki.remember.extract",
            MagicMock(return_value={"entities": [
                {"name": "First", "kind": "entity", "facts": "f"}], "concepts": []}),
            raising=False,
        )

        # Simulate another PID appending to the work-log mid-drain: on the first
        # resolve_entity call, append a second batch, then behave normally.
        injected = {"done": False}

        def resolve_side_effect(client, space_id, type_key, name):
            if not injected["done"]:
                injected["done"] = True
                worklog.begin(space_id, [{"name": "LateArrival", "kind": "entity", "facts": "g"}],
                              meta={"relations": [], "source": None, "subject": "late"})
            return {"action": "create"}

        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.resolve_entity", resolve_side_effect, raising=False)

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(201, json=_wikilog_create_response())
            )
            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(space_id=FAKE_SPACE_ID, knowledge="first")

        titles = {o["title"] for o in result.get("objects", [])}
        assert titles == {"First", "LateArrival"}, (
            f"drain-until-dry must sweep up the concurrently-appended subject; got {titles}"
        )
        assert worklog.load_pending(FAKE_SPACE_ID) == [], "work-log must be fully drained"

    def test_drain_pending_applies_queued_leftovers(self, monkeypatch, tmp_path):
        """The wiki-drain backstop (remember.drain_pending) applies subjects left in
        the work-log by a queued/crashed submit that nobody drained."""
        _patch_decision_ok(monkeypatch, tmp_path)
        from anytype_llm_wiki.wiki import remember, worklog

        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr(remember, "space_ingest_lock", mock_lock, raising=False)
        monkeypatch.setattr(remember, "_maybe_reindex", lambda *a, **k: None, raising=False)
        monkeypatch.setattr(remember, "resolve_entity", lambda *a, **k: {"action": "create"}, raising=False)

        # A queued/crashed submit: subjects durable in the log, never drained.
        worklog.begin(FAKE_SPACE_ID,
                      [{"name": "Orphan1", "kind": "entity", "facts": "f"},
                       {"name": "Orphan2", "kind": "entity", "facts": "g"}],
                      meta={"relations": [], "source": None, "subject": "orphans"})

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(201, json=_wikilog_create_response())
            )
            result = remember.drain_pending(space_id=FAKE_SPACE_ID)

        titles = {o["title"] for o in result.get("objects", [])}
        assert titles == {"Orphan1", "Orphan2"}, (
            f"wiki-drain must apply queued leftovers; got {titles}"
        )
        assert worklog.load_pending(FAKE_SPACE_ID) == [], "leftovers must be drained + compacted"

    def test_source_type_conversation_branch(self, monkeypatch, tmp_path):
        """AC-R13/B4 — source containing 'conversation' → wiki_source_type = conversation tag."""
        self._base_mocks(monkeypatch, tmp_path)

        source_payloads = []

        def capture_post(request, **kwargs):
            payload = json.loads(request.content)
            if payload.get("type_key") == "wiki_entity":
                return httpx.Response(201, json=_create_object_response("conv-ent-001", "TestEntity"))
            if payload.get("type_key") == "wiki_source":
                source_payloads.append(payload)
                return httpx.Response(201, json=_source_create_response())
            if payload.get("type_key") == "wiki_log":
                return httpx.Response(201, json=_wikilog_create_response())
            return httpx.Response(201, json={"object": {"id": "x", "name": "x"}})

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_empty_search_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                side_effect=capture_post
            )
            router.patch(f"/v1/spaces/{FAKE_SPACE_ID}/objects/conv-ent-001").mock(
                return_value=httpx.Response(200, json={"object": {"id": "conv-ent-001"}})
            )
            router.get("/v1/spaces/space-remember-test-001/properties").mock(
                return_value=httpx.Response(200, json=_properties_response(["wiki_source_type"]))
            )
            router.get(
                url__regex=r".*/v1/spaces/space-remember-test-001/properties/[^/]+/tags(\?.*)?$"
            ).mock(
                return_value=httpx.Response(200, json=_tags_response(["agent", "conversation", "document"]))
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            wiki_remember(
                space_id=FAKE_SPACE_ID,
                knowledge="TestEntity supports Python.",
                source="user conversation about TestEntity",
            )

        assert source_payloads, "Source must be created"
        props = source_payloads[0].get("properties", [])
        source_type_props = [p for p in props if p.get("key") == "wiki_source_type"]
        assert source_type_props, f"wiki_source_type must be present; props: {props}"
        # The select value must point to the conversation tag
        select_val = source_type_props[0].get("select", "")
        assert "conversation" in str(select_val), (
            f"Source type must be conversation tag when source contains 'conversation'; got {select_val!r}"
        )

    def test_source_type_agent_branch(self, monkeypatch, tmp_path):
        """AC-R13/B4 — source=None → wiki_source_type = agent tag."""
        self._base_mocks(monkeypatch, tmp_path)

        source_payloads = []

        def capture_post(request, **kwargs):
            payload = json.loads(request.content)
            if payload.get("type_key") == "wiki_entity":
                return httpx.Response(201, json=_create_object_response("agent-ent-001", "TestEntity"))
            if payload.get("type_key") == "wiki_source":
                source_payloads.append(payload)
                return httpx.Response(201, json=_source_create_response())
            if payload.get("type_key") == "wiki_log":
                return httpx.Response(201, json=_wikilog_create_response())
            return httpx.Response(201, json={"object": {"id": "x", "name": "x"}})

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_empty_search_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                side_effect=capture_post
            )
            router.patch(f"/v1/spaces/{FAKE_SPACE_ID}/objects/agent-ent-001").mock(
                return_value=httpx.Response(200, json={"object": {"id": "agent-ent-001"}})
            )
            router.get("/v1/spaces/space-remember-test-001/properties").mock(
                return_value=httpx.Response(200, json=_properties_response(["wiki_source_type"]))
            )
            router.get(
                url__regex=r".*/v1/spaces/space-remember-test-001/properties/[^/]+/tags(\?.*)?$"
            ).mock(
                return_value=httpx.Response(200, json=_tags_response(["agent", "conversation", "document"]))
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            wiki_remember(
                space_id=FAKE_SPACE_ID,
                knowledge="TestEntity supports Python.",
                source=None,  # None → agent branch
            )

        assert source_payloads, "Source must be created"
        props = source_payloads[0].get("properties", [])
        source_type_props = [p for p in props if p.get("key") == "wiki_source_type"]
        assert source_type_props, f"wiki_source_type must be present; props: {props}"
        select_val = source_type_props[0].get("select", "")
        assert "agent" in str(select_val), (
            f"Source type must be agent tag when source=None; got {select_val!r}"
        )

    def test_relations_wired_from_caller_param(self, monkeypatch, tmp_path):
        """AC-R1 — relations param → _write_bidirectional_relations called; per-object relations_created populated."""
        _patch_decision_ok(monkeypatch, tmp_path)
        mock_extract = MagicMock(return_value=_canned_extract_result())
        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.extract", mock_extract, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False)

        mock_write_rels = MagicMock(return_value=(1, []))  # (count, rollback_notes)
        monkeypatch.setattr(
            "anytype_llm_wiki.wiki.remember._write_bidirectional_relations",
            mock_write_rels, raising=False
        )

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_empty_search_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(201, json=_create_object_response("e-rel-001", "TestEntity"))
            )
            router.patch(f"/v1/spaces/{FAKE_SPACE_ID}/objects/e-rel-001").mock(
                return_value=httpx.Response(200, json={"object": {"id": "e-rel-001"}})
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(
                space_id=FAKE_SPACE_ID,
                knowledge="TestEntity supports Python.",
                relations=[{"from": "TestEntity", "to": "OtherEntity", "label": "uses"}],
            )

        assert mock_write_rels.called, "_write_bidirectional_relations must be called when relations passed"
        objects = result.get("objects", [])
        assert objects, "Expected per-object result"
        total_relations = result.get("relations_created", -1)
        assert total_relations >= 0, f"relations_created must be present; got {total_relations}"

    def test_relation_endpoint_wrong_type_not_wired(self, monkeypatch, tmp_path):
        """AC-R31/SF5 — same-name wrong-type endpoint not selected; unresolved endpoint → warning."""
        _patch_decision_ok(monkeypatch, tmp_path)
        mock_extract = MagicMock(return_value=_canned_extract_result())
        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.extract", mock_extract, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False)

        # Mock _write_bidirectional_relations to simulate 0 relations (endpoint unresolved)
        mock_write_rels = MagicMock(return_value=(0, ["relation_endpoint_unresolved: WrongTypeObj"]))
        monkeypatch.setattr(
            "anytype_llm_wiki.wiki.remember._write_bidirectional_relations",
            mock_write_rels, raising=False
        )

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_empty_search_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(201, json=_create_object_response("e-wt-001", "TestEntity"))
            )
            router.patch(f"/v1/spaces/{FAKE_SPACE_ID}/objects/e-wt-001").mock(
                return_value=httpx.Response(200, json={"object": {"id": "e-wt-001"}})
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(
                space_id=FAKE_SPACE_ID,
                knowledge="TestEntity supports Python.",
                relations=[{"from": "TestEntity", "to": "WrongTypeObj", "label": "refs"}],
            )

        # relations_created must be 0 (endpoint unresolved)
        assert result.get("relations_created", -1) == 0, (
            f"Unresolved endpoint must yield relations_created=0; got {result.get('relations_created')}"
        )

    def test_deeplink_in_result(self, monkeypatch, tmp_path):
        """AC-R1 — per-object deeplink = anytype://object/{space_id}/{object_id}."""
        self._base_mocks(monkeypatch, tmp_path)

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_empty_search_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(201, json=_create_object_response("deeplink-001", "TestEntity"))
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(space_id=FAKE_SPACE_ID, knowledge="TestEntity supports Python.")

        objects = result.get("objects", [])
        assert objects, "Expected per-object result"
        for obj in objects:
            deeplink = obj.get("deeplink", "")
            if obj.get("object_id"):
                expected = f"anytype://object/{FAKE_SPACE_ID}/{obj['object_id']}"
                assert deeplink == expected, (
                    f"deeplink must be anytype://object/space_id/object_id; "
                    f"expected {expected!r}, got {deeplink!r}"
                )


# ---------------------------------------------------------------------------
# §10.5 — Hard Gate Tests (Must Drive Real Entry Point)
# ---------------------------------------------------------------------------

class TestHardGates:
    """AC-R-S1, AC-R-S2, AC-R25, AC-R26 — gates driving real wiki_remember entry point."""

    def test_empty_knowledge_rejected_before_lock(self, monkeypatch, tmp_path):
        """AC-R25/B8 — empty/whitespace knowledge → [CONFIG ERROR] empty_knowledge;
        space_ingest_lock + extract + create_object NEVER called.
        """
        _patch_decision_ok(monkeypatch, tmp_path)
        mock_lock = MagicMock()
        mock_extract = MagicMock()
        create_calls = []

        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.extract", mock_extract, raising=False)

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_empty_search_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                side_effect=lambda req, **kw: create_calls.append(json.loads(req.content))
                or httpx.Response(201, json={"object": {"id": "x", "name": "x"}})
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember

            for bad_knowledge in ("", "   ", "\n\t\r"):
                result = wiki_remember(space_id=FAKE_SPACE_ID, knowledge=bad_knowledge)
                result_str = str(result)
                assert "empty_knowledge" in result_str or "[CONFIG ERROR]" in result_str, (
                    f"Empty knowledge must return [CONFIG ERROR] empty_knowledge; got {result_str}"
                )
                assert result.get("status") == "error", (
                    f"Empty knowledge must return status=error; got {result.get('status')}"
                )

        mock_lock.assert_not_called()
        mock_extract.assert_not_called()
        assert not create_calls, (
            f"create_object must NOT be called for empty knowledge; calls: {create_calls}"
        )

    def test_oversize_knowledge_rejected_before_lock(self, monkeypatch, tmp_path):
        """AC-R26/B2 — len(knowledge)>32000 → [DATA ERROR] knowledge_too_large; no lock, no extract."""
        _patch_decision_ok(monkeypatch, tmp_path)
        mock_lock = MagicMock()
        mock_extract = MagicMock()
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.extract", mock_extract, raising=False)

        oversized = "x" * 32_001

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False):
            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(space_id=FAKE_SPACE_ID, knowledge=oversized)

        result_str = str(result)
        assert "knowledge_too_large" in result_str or "[DATA ERROR]" in result_str, (
            f"Oversize knowledge must return [DATA ERROR] knowledge_too_large; got {result_str}"
        )
        assert result.get("status") == "error", (
            f"Oversize knowledge must return status=error; got {result.get('status')}"
        )
        mock_lock.assert_not_called()
        mock_extract.assert_not_called()

    def test_space_lock_held_queues_for_drain(self, monkeypatch, tmp_path):
        """Queue-submit model: when the per-space lock is held by another writer,
        wiki_remember does NOT fail — it durably appends its subjects to the
        work-log (lock-free) and returns `queued_for_drain`. The current holder's
        drain-until-dry will apply them. Nothing is lost."""
        _patch_decision_ok(monkeypatch, tmp_path)
        from anytype_llm_wiki.wiki import worklog

        # Lock is permanently held → every acquire attempt is rejected.
        def lock_raises(space_id, source_ref):
            raise RuntimeError("[DATA ERROR] ingest_in_progress: space-remember-test-001")

        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.space_ingest_lock", lock_raises, raising=False)
        # Speed: no real sleeps between retries.
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.time.sleep", lambda *_: None, raising=False)
        monkeypatch.setattr(
            "anytype_llm_wiki.wiki.remember.extract",
            MagicMock(return_value={"entities": [
                {"name": "Held1", "kind": "entity", "facts": "f1"},
                {"name": "Held2", "kind": "entity", "facts": "f2"}], "concepts": []}),
            raising=False,
        )

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(space_id=FAKE_SPACE_ID, knowledge="Some knowledge here.")

        # Not an error — queued, durable, to be drained by the holder.
        assert result.get("status") == "ok", result
        assert result.get("queued") == 2, result
        assert any("queued_for_drain" in str(w) for w in result.get("warnings", [])), result
        # The subjects are durably in the work-log despite never getting the lock.
        pending = {p["name"] for p in worklog.load_pending(FAKE_SPACE_ID)}
        assert pending == {"Held1", "Held2"}, (
            f"Subjects must be durably queued even when the lock is held; got {pending}"
        )

    def test_consent_banner_fires_on_live_path(self, monkeypatch, tmp_path):
        """AC-R-S1 (HARD GATE) — real wiki_remember entry with non-local WIKI_EXTRACT_ENDPOINT
        and no ack file; consent check fires BEFORE any non-local HTTP call.
        """
        _patch_decision_ok(monkeypatch, tmp_path)
        # Set a non-local endpoint
        non_local = "https://api.example.com/v1/ollama"
        monkeypatch.setenv("WIKI_EXTRACT_ENDPOINT", non_local)

        call_order = []

        def mock_consent(endpoint):
            call_order.append(("consent", endpoint))
            # Simulates: writes ack file, returns
            ack_dir = tmp_path / "ack"
            ack_dir.mkdir(exist_ok=True)
            import hashlib
            ack_name = hashlib.sha256(endpoint.encode()).hexdigest()[:8]
            (ack_dir / ack_name).write_text("acked")
            return True

        def mock_extract(*args, **kwargs):
            call_order.append(("extract", args[0] if args else None))
            return _canned_extract_result()

        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)

        monkeypatch.setattr(
            "anytype_llm_wiki.wiki.remember.check_remote_endpoint_consent",
            mock_consent, raising=False
        )
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.extract", mock_extract, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False)

        consolidate_result = _canned_consolidate_result(changed=False)
        mock_consolidate = MagicMock(return_value=consolidate_result)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.consolidate", mock_consolidate, raising=False)

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_empty_search_response())
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(201, json=_wikilog_create_response())
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            wiki_remember(space_id=FAKE_SPACE_ID, knowledge="TestEntity supports Python.")

        # Consent must have been called
        consent_calls = [c for c in call_order if c[0] == "consent"]
        assert consent_calls, (
            f"check_remote_endpoint_consent must be called on non-local endpoint; order={call_order}"
        )

        # Consent must fire BEFORE extract (the first non-local transmit)
        extract_calls = [c for c in call_order if c[0] == "extract"]
        if extract_calls:
            consent_idx = next(i for i, c in enumerate(call_order) if c[0] == "consent")
            extract_idx = next(i for i, c in enumerate(call_order) if c[0] == "extract")
            assert consent_idx < extract_idx, (
                f"Consent must fire BEFORE extract; order={call_order}"
            )


# ---------------------------------------------------------------------------
# Addendum item 1: Supersede recorded in WikiLog notes
# ---------------------------------------------------------------------------

class TestSupersede:
    """Addendum item 1 — supersede fact_action produces WikiLog notes with removed prior text."""

    def test_supersede_recorded_in_wikilog_notes(self, monkeypatch, tmp_path):
        """Addendum item 1 — fact_action action='supersede' → WikiLog notes contain superseded text."""
        _patch_decision_ok(monkeypatch, tmp_path)
        superseded_text = "TestEntity has 4 GB RAM."
        new_text = "TestEntity has 8 GB RAM."
        consolidate_result = {
            "consolidated_text": new_text,
            "changed": True,
            "fact_actions": [
                {
                    "fact": new_text,
                    "action": "supersede",
                    "supersedes": superseded_text,
                }
            ],
            "conflicts": [],
        }
        mock_consolidate = MagicMock(return_value=consolidate_result)
        mock_extract = MagicMock(return_value=_canned_extract_result())
        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.consolidate", mock_consolidate, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.extract", mock_extract, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False)

        wikilog_payloads = []

        def capture_post(request, **kwargs):
            payload = json.loads(request.content)
            if payload.get("type_key") == "wiki_log":
                wikilog_payloads.append(payload)
                return httpx.Response(201, json=_wikilog_create_response())
            return httpx.Response(201, json=_source_create_response())

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_single_entity_response())
            )
            router.patch(f"/v1/spaces/{FAKE_SPACE_ID}/objects/entity-001").mock(
                return_value=httpx.Response(200, json={"object": {"id": "entity-001"}})
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                side_effect=capture_post
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            wiki_remember(space_id=FAKE_SPACE_ID, knowledge="TestEntity has 8 GB RAM.")

        assert wikilog_payloads, "WikiLog must be created"
        wikilog_str = str(wikilog_payloads[0].get("properties", []))
        # The superseded old text must appear in the notes
        assert superseded_text in wikilog_str or "4 GB RAM" in wikilog_str, (
            f"WikiLog notes must contain superseded text '{superseded_text}'; "
            f"wikilog props: {wikilog_str}"
        )


# ---------------------------------------------------------------------------
# Addendum item 2: Conflict path surfaces sources_overwrite warning
# ---------------------------------------------------------------------------

class TestConflictSourcesOverwrite:
    """Addendum item 2 — conflict-flagged object yields sources_overwrite_on_conflict in warnings."""

    def test_conflict_path_surfaces_sources_overwrite(self, monkeypatch, tmp_path):
        """Addendum item 2 — conflict-flagged object yields sources_overwrite_on_conflict in result warnings."""
        _patch_decision_ok(monkeypatch, tmp_path)
        consolidate_result = {
            "consolidated_text": (
                "TestEntity uses approach A. [CONFLICT: approach B]"
            ),
            "changed": True,
            "fact_actions": [],
            "conflicts": [
                {
                    "existing_fact": "TestEntity uses approach A.",
                    "new_fact": "approach B",
                    "reason": "contradiction",
                }
            ],
        }
        mock_consolidate = MagicMock(return_value=consolidate_result)
        mock_extract = MagicMock(return_value=_canned_extract_result())
        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.consolidate", mock_consolidate, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.extract", mock_extract, raising=False)
        monkeypatch.setattr("anytype_llm_wiki.wiki.remember.space_ingest_lock", mock_lock, raising=False)

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post("/v1/spaces/space-remember-test-001/search").mock(
                return_value=httpx.Response(200, json=_single_entity_response())
            )
            router.patch(f"/v1/spaces/{FAKE_SPACE_ID}/objects/entity-001").mock(
                return_value=httpx.Response(200, json={"object": {"id": "entity-001"}})
            )
            router.get("/v1/spaces/space-remember-test-001/properties").mock(
                return_value=httpx.Response(200, json=_properties_response(["wiki_status"]))
            )
            router.get(
                url__regex=r".*/v1/spaces/space-remember-test-001/properties/[^/]+/tags(\?.*)?$"
            ).mock(
                return_value=httpx.Response(200, json=_tags_response(["needs-review"]))
            )
            router.post("/v1/spaces/space-remember-test-001/objects").mock(
                return_value=httpx.Response(201, json=_wikilog_create_response())
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            result = wiki_remember(space_id=FAKE_SPACE_ID, knowledge="TestEntity uses approach B.")

        warnings = result.get("warnings", [])
        assert any("sources_overwrite_on_conflict" in str(w) for w in warnings), (
            f"Conflict path must emit sources_overwrite_on_conflict warning; warnings={warnings}"
        )


# ---------------------------------------------------------------------------
# §10.7 — Live Smoke Test
# ---------------------------------------------------------------------------

@pytest.mark.live
class TestLiveWikiRemember:
    """AC-R24 — live end-to-end smoke test (skip unless live services available)."""

    def test_live_wiki_remember_end_to_end(self):
        """AC-R24 — @pytest.mark.live; narrate → create; re-narrate → no duplicate; search returns entity."""
        import os
        space_id = os.environ.get("WIKI_TEST_SPACE_ID")
        if not space_id:
            pytest.skip("WIKI_TEST_SPACE_ID not set — live-API test skipped")

        from anytype_llm_wiki.wiki.remember import wiki_remember

        subject = "LiveTestEntity_remember_smoke_289"
        knowledge1 = f"{subject} is a test entity created by the wiki_remember live smoke test."
        knowledge2 = f"{subject} is verified working in the live smoke test run."

        result1 = wiki_remember(space_id=space_id, knowledge=knowledge1)
        assert result1.get("status") in ("ok", "partial"), (
            f"First call must succeed; got {result1}"
        )
        objects1 = result1.get("objects", [])
        assert objects1, "First call must produce per-object results"
        assert any(o.get("action") == "created" for o in objects1), (
            f"First call must create entity; actions={[o.get('action') for o in objects1]}"
        )
        obj_id = objects1[0].get("object_id")
        assert obj_id, "First call must return object_id"

        result2 = wiki_remember(space_id=space_id, knowledge=knowledge2)
        assert result2.get("status") in ("ok", "partial"), (
            f"Second call must succeed; got {result2}"
        )
        objects2 = result2.get("objects", [])
        assert objects2, "Second call must produce per-object results"
        actions2 = [o.get("action") for o in objects2]
        assert any(a in ("consolidated", "updated") for a in actions2), (
            f"Second call must not create duplicate; actions={actions2}"
        )
        # Same object_id (no duplicate)
        obj_id2 = objects2[0].get("object_id")
        assert obj_id == obj_id2, (
            f"object_id must be stable (no duplicate entity); call1={obj_id}, call2={obj_id2}"
        )

        # top-level conflicts_flagged == sum of per-object
        top_cf = result2.get("conflicts_flagged", 0)
        per_obj_cf_sum = sum(o.get("conflicts_flagged", 0) for o in objects2)
        assert top_cf == per_obj_cf_sum, (
            f"conflicts_flagged must be sum of per-object; top={top_cf}, sum={per_obj_cf_sum}"
        )


# ---------------------------------------------------------------------------
# #336 — AC-P3: domain_tags threaded into meta (bug fix at remember.py:336)
# ---------------------------------------------------------------------------


class TestRememberDomainTagsInMeta:
    """#336 AC-P3: domain_tags passed to wiki_remember must be in the meta dict
    passed to worklog.begin (bug fix: domain_tags was NOT in meta before #336).
    """

    def test_remember_domain_tags_in_meta(self, monkeypatch, tmp_path):
        """#336 AC-P3: wiki_remember(..., domain_tags=['ai', 'ml']) → meta['domain_tags'] == ['ai','ml']
        at the worklog.begin call site, AND the value survives JSON round-trip.

        SF7: assert against the REAL seam (worklog.begin meta), not _apply_batch,
        so JSON serialization is exercised.
        """
        from anytype_llm_wiki.wiki import worklog
        from anytype_llm_wiki.wiki.remember import wiki_remember

        captured = {}

        original_begin = worklog.begin

        def spy_begin(space_id, subjects, meta=None):
            captured["meta"] = meta
            # Call the real begin so the rest of the pipeline can continue
            try:
                original_begin(space_id, subjects, meta=meta)
            except Exception:
                pass  # ignore worklog errors in this test

        monkeypatch.setattr(worklog, "begin", spy_begin)

        # Stub extraction to return one entity so the pipeline produces subjects
        import anytype_llm_wiki.wiki.remember as _rem_mod
        import anytype_llm_wiki.wiki.ingest as _ingest_mod
        from unittest.mock import MagicMock

        # Bypass domain taxonomy validation — both the ingest source and the remember import
        monkeypatch.setattr(
            _ingest_mod, "_domain_taxonomy", lambda client, space_id: {"ai", "ml"}, raising=False
        )
        monkeypatch.setattr(
            _rem_mod, "_domain_taxonomy", lambda client, space_id: {"ai", "ml"}, raising=False
        )

        mock_extract = MagicMock(return_value={
            "entities": [{"name": "TestEntity", "facts": "TestEntity is important."}],
            "concepts": [],
        })
        mock_consolidate = MagicMock(return_value={
            "consolidated_text": "TestEntity is important.", "changed": False,
            "fact_actions": [], "conflicts": [],
        })
        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)

        monkeypatch.setattr(_rem_mod, "extract", mock_extract, raising=False)
        monkeypatch.setattr(_rem_mod, "consolidate", mock_consolidate, raising=False)
        monkeypatch.setattr(_rem_mod, "space_ingest_lock", mock_lock, raising=False)
        monkeypatch.setattr(
            _rem_mod, "_maybe_reindex", lambda space_id, result: None, raising=False
        )

        # Patch ALDEIA_DIR for patch-decision check
        import os as _os
        aldeia_dir = _os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))),
            ".aldeia",
            "140-wiki-library-module-port-llm-wiki-pattern-onto-any",
        )
        monkeypatch.setenv("ALDEIA_DIR", aldeia_dir)

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get(f"/v1/spaces/{FAKE_SPACE_ID}/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post(f"/v1/spaces/{FAKE_SPACE_ID}/search").mock(
                return_value=httpx.Response(200, json=_empty_search_response())
            )
            router.post(f"/v1/spaces/{FAKE_SPACE_ID}/objects").mock(
                return_value=httpx.Response(201, json=_create_object_response())
            )

            wiki_remember(
                space_id=FAKE_SPACE_ID,
                knowledge="TestEntity is important.",
                domain_tags=["ai", "ml"],
            )

        assert "meta" in captured, (
            "worklog.begin must have been called with meta kwarg; captured nothing. "
            "Likely domain_tags is not threaded into meta (the AC-P3 bug)."
        )
        meta = captured["meta"]
        assert "domain_tags" in meta, (
            f"meta must contain 'domain_tags' key (bug fix: was missing before #336). "
            f"meta keys: {list(meta.keys())}"
        )
        assert meta["domain_tags"] == ["ai", "ml"], (
            f"meta['domain_tags'] must be ['ai','ml']; got {meta['domain_tags']!r}"
        )

        # JSON round-trip: worklog serializes meta as JSON; list[str] must survive
        import json as _json
        rt = _json.loads(_json.dumps(meta))
        assert rt["domain_tags"] == ["ai", "ml"], (
            f"domain_tags must survive JSON round-trip; got {rt['domain_tags']!r}"
        )


# ---------------------------------------------------------------------------
# #336 — AC-P4, AC-P5: domain_tags written on entity create/update (remember path)
# ---------------------------------------------------------------------------


class TestRememberWritesDomainTags:
    """#336 AC-P4, AC-P5: _apply_batch writes wiki_domain_tags on create and update."""

    def test_remember_writes_domain_tags_on_create(self, monkeypatch, tmp_path):
        """#336 AC-P4: wiki_remember with domain_tags → create_object props contain wiki_domain_tags.

        Monkeypatches _resolve_multi_select_tags to return deterministic ids.
        Also monkeypatches _domain_taxonomy so domain_hint validation passes
        (list_properties/list_tags aren't mocked via respx here).
        """
        import anytype_llm_wiki.wiki.remember as _rem_mod
        import anytype_llm_wiki.wiki.ingest as _ingest_mod
        from unittest.mock import MagicMock

        # Bypass domain taxonomy validation — both the ingest copy and the remember import
        monkeypatch.setattr(
            _ingest_mod, "_domain_taxonomy", lambda client, space_id: {"ai", "ml"}, raising=False
        )
        monkeypatch.setattr(
            _rem_mod, "_domain_taxonomy", lambda client, space_id: {"ai", "ml"}, raising=False
        )

        # Resolver stub
        def fake_resolve_multi(client, space_id, property_key, tag_names):
            return (["tag-id-1", "tag-id-2"], False)

        monkeypatch.setattr(
            _ingest_mod, "_resolve_multi_select_tags", fake_resolve_multi, raising=False
        )
        # remember.py imports from ingest — patch both to be safe
        monkeypatch.setattr(
            _rem_mod, "_resolve_multi_select_tags", fake_resolve_multi, raising=False
        )

        captured_create_props = []

        mock_extract = MagicMock(return_value={
            "entities": [{"name": "TestEntity", "facts": "TestEntity is important."}],
            "concepts": [],
        })
        mock_consolidate = MagicMock(return_value={
            "consolidated_text": "TestEntity is important.", "changed": False,
            "fact_actions": [], "conflicts": [],
        })
        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)

        monkeypatch.setattr(_rem_mod, "extract", mock_extract, raising=False)
        monkeypatch.setattr(_rem_mod, "consolidate", mock_consolidate, raising=False)
        monkeypatch.setattr(_rem_mod, "space_ingest_lock", mock_lock, raising=False)
        monkeypatch.setattr(
            _rem_mod, "_maybe_reindex", lambda space_id, result: None, raising=False
        )

        import os as _os
        aldeia_dir = _os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))),
            ".aldeia",
            "140-wiki-library-module-port-llm-wiki-pattern-onto-any",
        )
        monkeypatch.setenv("ALDEIA_DIR", aldeia_dir)

        def capture_create(request, **kwargs):
            import json as _json
            try:
                payload = _json.loads(request.content)
            except Exception:
                payload = {}
            if payload.get("type_key") in ("wiki_entity", "wiki_concept"):
                captured_create_props.append(payload.get("properties", []))
            return httpx.Response(201, json=_create_object_response())

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get(f"/v1/spaces/{FAKE_SPACE_ID}/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post(f"/v1/spaces/{FAKE_SPACE_ID}/search").mock(
                return_value=httpx.Response(200, json=_empty_search_response())
            )
            router.post(f"/v1/spaces/{FAKE_SPACE_ID}/objects").mock(
                side_effect=capture_create
            )

            from anytype_llm_wiki.wiki.remember import wiki_remember
            wiki_remember(
                space_id=FAKE_SPACE_ID,
                knowledge="TestEntity is important.",
                domain_tags=["ai", "ml"],
            )

        assert captured_create_props, (
            "Expected at least one entity/concept create_object call. "
            "Check that _domain_taxonomy is patched and extract/consolidate stubs are set."
        )
        found = any(
            any(
                isinstance(p, dict) and p.get("key") == "wiki_domain_tags"
                and isinstance(p.get("multi_select"), list)
                and len(p.get("multi_select")) > 0
                for p in props
            )
            for props in captured_create_props
        )
        assert found, (
            f"Expected wiki_domain_tags multi_select in create_object props (#336 AC-P4). "
            f"Captured: {captured_create_props}"
        )

    def test_remember_writes_domain_tags_on_update(self, monkeypatch, tmp_path):
        """#336 AC-P5: wiki_remember with domain_tags on existing entity →
        update_object (PATCH) props contain wiki_domain_tags (OD-C SET semantics).

        OD-C discriminator: existing entity has a pre-existing wiki_domain_tags value
        ("old-rem-id"). After update with domain_tags=["ai"], the PATCH must contain ONLY
        ["tag-id-1"] — old-rem-id must be absent. A MERGE impl produces both; SET replaces.
        """
        import anytype_llm_wiki.wiki.remember as _rem_mod
        import anytype_llm_wiki.wiki.ingest as _ingest_mod
        from unittest.mock import MagicMock

        # Bypass domain taxonomy validation
        monkeypatch.setattr(
            _ingest_mod, "_domain_taxonomy", lambda client, space_id: {"ai"}, raising=False
        )
        monkeypatch.setattr(
            _rem_mod, "_domain_taxonomy", lambda client, space_id: {"ai"}, raising=False
        )

        def fake_resolve_multi(client, space_id, property_key, tag_names):
            return (["tag-id-1"], False)

        monkeypatch.setattr(
            _ingest_mod, "_resolve_multi_select_tags", fake_resolve_multi, raising=False
        )
        monkeypatch.setattr(
            _rem_mod, "_resolve_multi_select_tags", fake_resolve_multi, raising=False
        )

        captured_update_props = []

        mock_extract = MagicMock(return_value={
            "entities": [{"name": "TestEntity", "facts": "Updated facts."}],
            "concepts": [],
        })
        mock_consolidate = MagicMock(return_value={
            "consolidated_text": "Updated facts.", "changed": True,
            "fact_actions": [{"fact": "Updated facts.", "action": "add", "supersedes": None}],
            "conflicts": [],
        })
        mock_lock = MagicMock()
        mock_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)

        monkeypatch.setattr(_rem_mod, "extract", mock_extract, raising=False)
        monkeypatch.setattr(_rem_mod, "consolidate", mock_consolidate, raising=False)
        monkeypatch.setattr(_rem_mod, "space_ingest_lock", mock_lock, raising=False)
        monkeypatch.setattr(
            _rem_mod, "_maybe_reindex", lambda space_id, result: None, raising=False
        )

        import os as _os
        aldeia_dir = _os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))),
            ".aldeia",
            "140-wiki-library-module-port-llm-wiki-pattern-onto-any",
        )
        monkeypatch.setenv("ALDEIA_DIR", aldeia_dir)

        def capture_patch(request, **kwargs):
            import json as _json
            try:
                payload = _json.loads(request.content)
            except Exception:
                payload = {}
            captured_update_props.append(payload.get("properties", []))
            return httpx.Response(200, json={"object": {"id": "entity-001"}})

        # Entity with pre-existing wiki_domain_tags (OD-C discriminator fixture)
        entity_with_existing_tags = {
            "data": [
                {
                    "id": "entity-001",
                    "name": "TestEntity",
                    "type": {"key": "wiki_entity"},
                    "properties": [
                        {"key": "wiki_facts", "text": "TestEntity supports Python."},
                        {
                            "key": "wiki_domain_tags",
                            "format": "multi_select",
                            "multi_select": [{"id": "old-rem-id", "name": "old-rem-tag"}],
                        },
                    ],
                }
            ],
            "pagination": {"has_more": False},
        }

        with respx.mock(base_url=ANYTYPE_BASE, assert_all_called=False) as router:
            router.get(f"/v1/spaces/{FAKE_SPACE_ID}/objects").mock(
                return_value=httpx.Response(200, json=_schema_current_response())
            )
            router.post(f"/v1/spaces/{FAKE_SPACE_ID}/search").mock(
                return_value=httpx.Response(200, json=entity_with_existing_tags)
            )
            router.post(f"/v1/spaces/{FAKE_SPACE_ID}/objects").mock(
                return_value=httpx.Response(201, json=_wikilog_create_response())
            )
            router.patch(
                f"/v1/spaces/{FAKE_SPACE_ID}/objects/entity-001"
            ).mock(side_effect=capture_patch)

            from anytype_llm_wiki.wiki.remember import wiki_remember
            wiki_remember(
                space_id=FAKE_SPACE_ID,
                knowledge="Updated facts about TestEntity.",
                domain_tags=["ai"],
            )

        assert captured_update_props, (
            "Expected at least one entity/concept update_object (PATCH) call. "
            "Check that _domain_taxonomy is patched and consolidate returns changed=True."
        )
        found = any(
            any(
                isinstance(p, dict) and p.get("key") == "wiki_domain_tags"
                and isinstance(p.get("multi_select"), list)
                and len(p.get("multi_select")) > 0
                for p in props
            )
            for props in captured_update_props
        )
        assert found, (
            f"Expected wiki_domain_tags multi_select in update_object (PATCH) props (#336 AC-P5, OD-C SET). "
            f"Captured: {captured_update_props}"
        )
        # OD-C SET check: "old-rem-id" (pre-existing) must NOT appear in any PATCH
        # A MERGE impl would include both "old-rem-id" and "tag-id-1"; SET replaces.
        old_tag_absent = all(
            all(
                not (isinstance(p, dict) and p.get("key") == "wiki_domain_tags"
                     and "old-rem-id" in (p.get("multi_select") or []))
                for p in props
            )
            for props in captured_update_props
        )
        assert old_tag_absent, (
            f"#336 AC-P5 OD-C FAIL: pre-existing 'old-rem-id' must NOT appear in PATCH props "
            f"(SET semantics replace, not MERGE). "
            f"Captured update props: {captured_update_props}"
        )


# ---------------------------------------------------------------------------
# #336 — AC-S-AGENT: agent source with no note produces a chunkable excerpt (SF2)
# ---------------------------------------------------------------------------


class TestAgentSourceNoNoteIsChunkable:
    """#336 AC-S-AGENT: _create_remember_source with empty source_note writes a non-empty
    stub excerpt (the name) so the source produces >= 1 chunk (D4b).
    """

    def test_remember_agent_source_no_note_is_chunkable(self, monkeypatch, tmp_path):
        """#336 AC-S-AGENT: when source_note=None, _create_remember_source must write a
        non-empty wiki_excerpt (stub = source name) so chunk_object produces >= 1 chunk.

        Arrange: call _create_remember_source with source_note=None.
        Assert (write): the wiki_excerpt prop value is NON-EMPTY.
        Assert (chunk): chunk_object on the written source shape produces >= 1 chunk.
        """
        from anytype_llm_wiki.wiki.remember import _create_remember_source
        from anytype_llm_wiki.chunker import chunk_object

        captured_excerpt = {"value": None}
        captured_name = {"value": None}

        class FakeClient:
            def create_object(self, space_id, type_key, name, properties):
                # Capture the excerpt that was written
                for p in properties:
                    if isinstance(p, dict) and p.get("key") == "wiki_excerpt":
                        captured_excerpt["value"] = p.get("text")
                captured_name["value"] = name
                return {"id": "source-agent-001"}

        result = {}
        _create_remember_source(
            client=FakeClient(),
            space_id="sp-1",
            source_note=None,   # no note → must produce non-empty stub excerpt
            result=result,
            source_type_tag_id=None,
        )

        # (1) The written excerpt must be non-empty (D4b — old code wrote "")
        assert captured_excerpt["value"], (
            f"_create_remember_source must write a NON-EMPTY wiki_excerpt when source_note=None. "
            f"Got excerpt={captured_excerpt['value']!r}. "
            f"This is the D4b/SF2 fix — the stub should be the source name."
        )

        # (2) chunk_object on the written source shape must produce >= 1 chunk
        source_obj = {
            "id": "source-agent-001",
            "space_id": "sp-1",
            "name": captured_name["value"] or "agent-source",
            "type": {"key": "wiki_source"},
            "markdown": "",
            "properties": [
                {"key": "wiki_excerpt", "text": captured_excerpt["value"]},
            ],
        }
        chunks = chunk_object(source_obj)
        assert chunks, (
            f"chunk_object on the agent source (no note) must produce >= 1 chunk "
            f"(so source_type=['agent'] filter is not inert). "
            f"Excerpt written: {captured_excerpt['value']!r}"
        )
