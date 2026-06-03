"""Tests for wiki/bootstrap.py — wiki_bootstrap MCP tool.

Covers AC #1-6, #8-9, #11, #13 (bootstrap-specific outdated-schema exception),
#14 (patch-decision scaffolding), #15 (credential scrubbing).

All Anytype HTTP calls are mocked with respx. Live-API test is skip-gated on
ANYTYPE_API_KEY being set in the environment.
"""

import os
import time
import pytest
import respx
import httpx

ANYTYPE_BASE = "http://127.0.0.1:31012"
FAKE_SPACE_ID = "space-bootstrap-001"
FAKE_MISSING_SPACE_ID = "space-does-not-exist"
FAKE_API_KEY = "test-bootstrap-key"
FAKE_API_VERSION = "2025-11-08"

# The six canonical type keys required by AC #1
CANONICAL_TYPE_KEYS = [
    "wiki_source",
    "wiki_entity",
    "wiki_concept",
    "wiki_comparison",
    "wiki_query",
    "wiki_log",
]

DEFAULT_DOMAIN_TAGS = [
    "wiki_ai-research",
    "wiki_infrastructure",
    "wiki_business",
    "wiki_engineering",
    "wiki_governance",
    "wiki_science",
    "wiki_other",
]


@pytest.fixture(autouse=True)
def set_anytype_env(monkeypatch):
    monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
    monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)


def _wiki_properties_payload():
    """All unique wiki property keys as list-properties rows (key + id + format).

    Mirrors the real ``GET /v1/spaces/{id}/properties`` shape so bootstrap can
    resolve ``wiki_domain_tags`` → property_id (required for tag creation).
    """
    from anytype_llm_wiki.wiki import types_schema

    seen: dict[str, dict] = {}
    for type_def in types_schema.WIKI_TYPES:
        for prop in type_def["properties"]:
            key = prop["property_key"]
            seen.setdefault(
                key,
                {
                    "object": "property",
                    "id": f"prop-{key}",
                    "key": key,
                    "name": prop["name"],
                    "format": prop["format"],
                },
            )
    return list(seen.values())


def _install_success_routes(existing_tags=None, existing_types=None, existing_objects=None):
    """Install URL-aware respx routes matching the real Anytype write contract.

    - ``GET .../tags``        → existing_tags (default: none)
    - ``GET .../properties``  → the full wiki property set (with ids)
    - ``GET .../types``       → existing_types (default: none)
    - ``GET .../objects``     → existing_objects (default: none)
    - ``POST .../tags``       → ``{"tag": {...}}``   (NOT the legacy ``option``)
    - ``POST .../types``      → ``{"type": {...}}``
    - ``POST .../objects``    → ``{"object": {...}}``
    - ``POST .../properties`` → ``{"property": {...}}``
    """
    existing_tags = existing_tags or []
    existing_types = existing_types or []
    existing_objects = existing_objects or []
    props = _wiki_properties_payload()

    def get_response(request, **kwargs):
        path = str(request.url).split("?")[0]
        if path.endswith("/tags"):
            data = existing_tags
        elif path.endswith("/properties"):
            data = props
        elif path.endswith("/types"):
            data = existing_types
        elif path.endswith("/objects"):
            data = existing_objects
        else:
            data = []
        return httpx.Response(200, json={"data": data, "pagination": {"has_more": False}})

    def post_response(request, **kwargs):
        path = str(request.url).split("?")[0]
        if path.endswith("/tags"):
            return httpx.Response(201, json={
                "tag": {"id": f"tag-{os.urandom(4).hex()}", "name": "x", "color": "blue"}
            })
        if path.endswith("/types"):
            return httpx.Response(201, json={
                "type": {"id": f"obj-{os.urandom(4).hex()}", "key": "wiki_source"}
            })
        if path.endswith("/objects"):
            return httpx.Response(201, json={
                "object": {"id": f"obj-{os.urandom(4).hex()}", "name": "Wiki"}
            })
        if path.endswith("/properties"):
            return httpx.Response(201, json={
                "property": {"id": f"prop-{os.urandom(4).hex()}", "key": "wiki_url"}
            })
        return httpx.Response(200, json={})

    respx.get().mock(side_effect=get_response)
    respx.post().mock(side_effect=post_response)


class TestBootstrapImport:
    def test_wiki_bootstrap_importable(self):
        """wiki_bootstrap must be importable from anytype_llm_wiki.wiki.bootstrap."""
        from anytype_llm_wiki.wiki.bootstrap import wiki_bootstrap  # noqa: F401

    def test_wiki_bootstrap_is_callable(self):
        from anytype_llm_wiki.wiki.bootstrap import wiki_bootstrap
        assert callable(wiki_bootstrap)


class TestBootstrapResult:
    """BootstrapResult must conform to the schema in spec §Type Schema."""

    @respx.mock
    def test_result_has_required_keys(self, monkeypatch):
        """wiki_bootstrap result must contain all required BootstrapResult keys."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        # Catch-all mock for all POST/GET on the Anytype base
        respx.post().mock(return_value=httpx.Response(200, json={
            "type": {"id": "t1", "key": "wiki_source"},
            "property": {"id": "p1", "key": "wiki_url"},
            "option": {"id": "o1", "name": "wiki_ai-research"},
            "object": {"id": "c1", "name": "Wiki"},
        }))
        respx.get().mock(return_value=httpx.Response(200, json={
            "data": [], "pagination": {"has_more": False}
        }))
        from anytype_llm_wiki.wiki.bootstrap import wiki_bootstrap
        result = wiki_bootstrap(space_id=FAKE_SPACE_ID)
        assert isinstance(result, dict), "wiki_bootstrap must return a dict"
        required_keys = [
            "space_id",
            "types_created",
            "types_skipped",
            "properties_created",
            "properties_skipped",
            "tags_created",
            "tags_skipped",
            "root_collection_id",
            "status",
        ]
        for key in required_keys:
            assert key in result, f"BootstrapResult missing key: {key!r}"

    @respx.mock
    def test_result_status_ok_on_success(self, monkeypatch):
        """wiki_bootstrap on a clean space must return status 'ok'."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        respx.post().mock(return_value=httpx.Response(200, json={
            "type": {"id": "t1", "key": "wiki_source"},
            "property": {"id": "p1", "key": "wiki_url"},
            "option": {"id": "o1", "name": "wiki_ai-research"},
            "object": {"id": "c1", "name": "Wiki"},
        }))
        respx.get().mock(return_value=httpx.Response(200, json={
            "data": [], "pagination": {"has_more": False}
        }))
        from anytype_llm_wiki.wiki.bootstrap import wiki_bootstrap
        result = wiki_bootstrap(space_id=FAKE_SPACE_ID)
        assert result["status"] == "ok", f"Expected status 'ok', got {result['status']!r}"

    @respx.mock
    def test_result_space_id_echoed(self, monkeypatch):
        """wiki_bootstrap result must echo back the space_id that was passed."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        respx.post().mock(return_value=httpx.Response(200, json={
            "type": {"id": "t1", "key": "wiki_source"},
            "property": {"id": "p1", "key": "wiki_url"},
            "option": {"id": "o1", "name": "wiki_ai-research"},
            "object": {"id": "c1", "name": "Wiki"},
        }))
        respx.get().mock(return_value=httpx.Response(200, json={
            "data": [], "pagination": {"has_more": False}
        }))
        from anytype_llm_wiki.wiki.bootstrap import wiki_bootstrap
        result = wiki_bootstrap(space_id=FAKE_SPACE_ID)
        assert result["space_id"] == FAKE_SPACE_ID


class TestBootstrapCreatesTypesAndProperties:
    """AC #1: wiki_bootstrap creates 6 Types with correct properties and root Collection."""

    @respx.mock
    def test_creates_six_types(self, monkeypatch):
        """First bootstrap on a clean space must create all 6 canonical wiki types."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)

        created_type_keys = []

        def capture_type(request, **kwargs):
            import json as _json
            try:
                body = _json.loads(request.content)
                created_type_keys.append(body.get("key", ""))
            except Exception:
                pass
            return httpx.Response(200, json={"type": {"id": "t1", "key": "wiki_source"}})

        respx.post().mock(side_effect=capture_type)
        respx.get().mock(return_value=httpx.Response(200, json={
            "data": [], "pagination": {"has_more": False}
        }))

        from anytype_llm_wiki.wiki.bootstrap import wiki_bootstrap
        result = wiki_bootstrap(space_id=FAKE_SPACE_ID)

        total_created_types = len(result.get("types_created", []))
        assert total_created_types == 6, (
            f"Expected 6 types_created, got {total_created_types}: {result.get('types_created')}"
        )

    @respx.mock
    def test_types_created_have_canonical_keys(self, monkeypatch):
        """types_created must contain exactly the 6 canonical type_key values."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        respx.post().mock(return_value=httpx.Response(200, json={
            "type": {"id": "t1", "key": "wiki_source"},
            "property": {"id": "p1", "key": "wiki_url"},
            "option": {"id": "o1", "name": "wiki_ai-research"},
            "object": {"id": "c1", "name": "Wiki"},
        }))
        respx.get().mock(return_value=httpx.Response(200, json={
            "data": [], "pagination": {"has_more": False}
        }))
        from anytype_llm_wiki.wiki.bootstrap import wiki_bootstrap
        result = wiki_bootstrap(space_id=FAKE_SPACE_ID)
        created_keys = {t["type_key"] for t in result.get("types_created", [])}
        for key in CANONICAL_TYPE_KEYS:
            assert key in created_keys, f"types_created missing canonical type_key: {key!r}"

    @respx.mock
    def test_creates_root_collection(self, monkeypatch):
        """wiki_bootstrap must create a root Collection and return its ID."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        respx.post().mock(return_value=httpx.Response(200, json={
            "type": {"id": "t1", "key": "wiki_source"},
            "property": {"id": "p1", "key": "wiki_url"},
            "option": {"id": "o1", "name": "wiki_ai-research"},
            "object": {"id": "coll-001", "name": "Wiki"},
        }))
        respx.get().mock(return_value=httpx.Response(200, json={
            "data": [], "pagination": {"has_more": False}
        }))
        from anytype_llm_wiki.wiki.bootstrap import wiki_bootstrap
        result = wiki_bootstrap(space_id=FAKE_SPACE_ID)
        assert result.get("root_collection_id"), (
            "root_collection_id must be set after successful bootstrap"
        )

    @respx.mock
    def test_creates_default_domain_tags(self, monkeypatch):
        """wiki_bootstrap on a clean space must create all 7 default domain tags."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        _install_success_routes()
        from anytype_llm_wiki.wiki.bootstrap import wiki_bootstrap
        result = wiki_bootstrap(space_id=FAKE_SPACE_ID)
        created_tags = {t["tag"] for t in result.get("tags_created", [])}
        for tag in DEFAULT_DOMAIN_TAGS:
            assert tag in created_tags, f"Default domain tag missing from tags_created: {tag!r}"

    @respx.mock
    def test_deeplinks_in_types_created(self, monkeypatch):
        """types_created entries must include deeplink fields."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        respx.post().mock(return_value=httpx.Response(200, json={
            "type": {"id": "t1", "key": "wiki_source"},
            "property": {"id": "p1", "key": "wiki_url"},
            "option": {"id": "o1", "name": "wiki_ai-research"},
            "object": {"id": "c1", "name": "Wiki"},
        }))
        respx.get().mock(return_value=httpx.Response(200, json={
            "data": [], "pagination": {"has_more": False}
        }))
        from anytype_llm_wiki.wiki.bootstrap import wiki_bootstrap
        result = wiki_bootstrap(space_id=FAKE_SPACE_ID)
        for type_entry in result.get("types_created", []):
            assert "deeplink" in type_entry, (
                f"types_created entry missing 'deeplink': {type_entry}"
            )


class TestBootstrapIdempotency:
    """AC #2: Second bootstrap on same space produces no duplicates; skipped arrays populated."""

    @respx.mock
    def test_second_call_populates_types_skipped(self, monkeypatch):
        """On re-bootstrap of an already-bootstrapped space, types_skipped must be populated."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        # Simulate existing types returned by GET (space already bootstrapped)
        existing_types = [
            {"id": f"t{i}", "key": key, "name": key.replace("wiki_", "")}
            for i, key in enumerate(CANONICAL_TYPE_KEYS)
        ]
        respx.get().mock(return_value=httpx.Response(200, json={
            "data": existing_types,
            "pagination": {"has_more": False}
        }))
        # POST should not be called if all types already exist
        respx.post().mock(return_value=httpx.Response(200, json={
            "type": {"id": "t_new", "key": "wiki_source"},
            "object": {"id": "c1", "name": "Wiki"},
        }))
        from anytype_llm_wiki.wiki.bootstrap import wiki_bootstrap
        result = wiki_bootstrap(space_id=FAKE_SPACE_ID)
        assert len(result.get("types_skipped", [])) > 0, (
            "types_skipped must be non-empty on re-bootstrap of existing space"
        )

    @respx.mock
    def test_second_call_skipped_entries_have_already_exists_reason(self, monkeypatch):
        """Skipped entries must have reason='already_exists'."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        existing_types = [
            {"id": f"t{i}", "key": key, "name": key}
            for i, key in enumerate(CANONICAL_TYPE_KEYS)
        ]
        respx.get().mock(return_value=httpx.Response(200, json={
            "data": existing_types, "pagination": {"has_more": False}
        }))
        respx.post().mock(return_value=httpx.Response(200, json={
            "object": {"id": "c1", "name": "Wiki"},
        }))
        from anytype_llm_wiki.wiki.bootstrap import wiki_bootstrap
        result = wiki_bootstrap(space_id=FAKE_SPACE_ID)
        for skipped in result.get("types_skipped", []):
            assert skipped.get("reason") == "already_exists", (
                f"types_skipped entry has wrong reason: {skipped}"
            )

    @respx.mock
    def test_second_call_creates_no_duplicate_types(self, monkeypatch):
        """Re-bootstrap must not create any type that already exists (types_created must be empty)."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        existing_types = [
            {"id": f"t{i}", "key": key, "name": key}
            for i, key in enumerate(CANONICAL_TYPE_KEYS)
        ]
        respx.get().mock(return_value=httpx.Response(200, json={
            "data": existing_types, "pagination": {"has_more": False}
        }))
        respx.post().mock(return_value=httpx.Response(200, json={
            "object": {"id": "c1", "name": "Wiki"},
        }))
        from anytype_llm_wiki.wiki.bootstrap import wiki_bootstrap
        result = wiki_bootstrap(space_id=FAKE_SPACE_ID)
        assert len(result.get("types_created", [])) == 0, (
            "Re-bootstrap must not create types that already exist"
        )


class TestBootstrapMissingSpace:
    """AC #3: wiki_bootstrap with missing space_id returns [CONFIG ERROR] with space_id echoed."""

    @respx.mock
    def test_missing_space_returns_config_error(self, monkeypatch):
        """wiki_bootstrap on a 404 space must return a result containing [CONFIG ERROR]."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        respx.get().mock(return_value=httpx.Response(404, json={
            "error": "space not found"
        }))
        respx.post().mock(return_value=httpx.Response(404, json={
            "error": "space not found"
        }))
        from anytype_llm_wiki.wiki.bootstrap import wiki_bootstrap
        result = wiki_bootstrap(space_id=FAKE_MISSING_SPACE_ID)
        # Spec line 733: wiki_bootstrap with missing space returns [CONFIG ERROR] with space_id echoed.
        # Must contain [CONFIG ERROR] — status=='error' alone is insufficient.
        if isinstance(result, dict):
            result_str = str(result)
            assert "[CONFIG ERROR]" in result_str, (
                f"Expected [CONFIG ERROR] in result for missing space, got: {result}"
            )
            assert FAKE_MISSING_SPACE_ID in result_str, (
                "space_id must be echoed in the error response"
            )

    @respx.mock
    def test_missing_space_echoes_space_id(self, monkeypatch):
        """Error response for missing space must include the space_id."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        respx.post(
            f"{ANYTYPE_BASE}/v1/spaces/{FAKE_MISSING_SPACE_ID}/types"
        ).mock(return_value=httpx.Response(404, json={"error": "space not found"}))
        respx.get().mock(return_value=httpx.Response(404, json={}))
        from anytype_llm_wiki.wiki.bootstrap import wiki_bootstrap
        try:
            result = wiki_bootstrap(space_id=FAKE_MISSING_SPACE_ID)
            result_str = str(result)
        except Exception as exc:
            result_str = str(exc)
        assert FAKE_MISSING_SPACE_ID in result_str, (
            f"Missing space_id {FAKE_MISSING_SPACE_ID!r} not echoed in error: {result_str}"
        )


class TestBootstrapUnreachable:
    """AC #4: Anytype unreachable → [API ERROR] with start instructions."""

    def test_unreachable_anytype_returns_api_error(self, monkeypatch):
        """When Anytype is unreachable (ConnectError), result must contain [API ERROR]."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", "http://127.0.0.1:19999")  # nothing listening
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        from anytype_llm_wiki.wiki.bootstrap import wiki_bootstrap
        try:
            result = wiki_bootstrap(space_id=FAKE_SPACE_ID)
            result_str = str(result)
        except Exception as exc:
            result_str = str(exc)
        assert "[API ERROR]" in result_str or "api_error" in result_str.lower(), (
            f"Expected [API ERROR] for unreachable Anytype, got: {result_str!r}"
        )


class TestBootstrapCustomDomainTags:
    """AC #5: custom domain_tags replaces defaults on first bootstrap; union-only on re-bootstrap."""

    @respx.mock
    def test_custom_domain_tags_on_first_bootstrap(self, monkeypatch):
        """First bootstrap with custom domain_tags must only create those tags (not defaults)."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        _install_success_routes()
        from anytype_llm_wiki.wiki.bootstrap import wiki_bootstrap
        result = wiki_bootstrap(space_id=FAKE_SPACE_ID, domain_tags=["a", "b"])
        created_tags = {t["tag"] for t in result.get("tags_created", [])}
        # Custom tags must be present
        assert "a" in created_tags
        assert "b" in created_tags
        # Default tags must NOT be present (custom replaces defaults on first bootstrap)
        for default_tag in DEFAULT_DOMAIN_TAGS:
            assert default_tag not in created_tags, (
                f"Default tag {default_tag!r} must not appear when custom domain_tags provided"
            )

    @respx.mock
    def test_rebootstrap_with_new_tags_is_union_only(self, monkeypatch):
        """Re-bootstrap with ['c'] when ['a','b'] exist must yield union ['a','b','c'].

        Asserts via a second bootstrap call, not manual state injection.
        Existing tags 'a' and 'b' are preserved; 'c' is added.
        """
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)

        existing_tags = [
            {"object": "tag", "id": "tag-a", "name": "a", "color": "blue"},
            {"object": "tag", "id": "tag-b", "name": "b", "color": "teal"},
        ]
        existing_types = [
            {"id": f"t{i}", "key": key, "name": key}
            for i, key in enumerate(CANONICAL_TYPE_KEYS)
        ]

        _install_success_routes(existing_tags=existing_tags, existing_types=existing_types)

        from anytype_llm_wiki.wiki.bootstrap import wiki_bootstrap
        result = wiki_bootstrap(space_id=FAKE_SPACE_ID, domain_tags=["c"])

        # 'a' and 'b' must appear in tags_skipped (already exist)
        skipped_tags = {t["tag"] for t in result.get("tags_skipped", [])}
        assert "a" in skipped_tags, "Existing tag 'a' must be skipped (not removed)"
        assert "b" in skipped_tags, "Existing tag 'b' must be skipped (not removed)"

        # 'c' must appear in tags_created
        created_tags = {t["tag"] for t in result.get("tags_created", [])}
        assert "c" in created_tags, "New tag 'c' must be in tags_created"


class TestBootstrapTiming:
    """AC #6: bootstrap with mocked Anytype must complete in under 150 seconds (5× the 30s target)."""

    @pytest.mark.timeout(150)
    @respx.mock
    def test_bootstrap_completes_within_timing_budget(self, monkeypatch):
        """wiki_bootstrap (mocked) must complete within 150 seconds (AC #6 CI timing check)."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        respx.post().mock(return_value=httpx.Response(200, json={
            "type": {"id": "t1", "key": "wiki_source"},
            "property": {"id": "p1", "key": "wiki_url"},
            "option": {"id": "o1", "name": "wiki_ai-research"},
            "object": {"id": "c1", "name": "Wiki"},
        }))
        respx.get().mock(return_value=httpx.Response(200, json={
            "data": [], "pagination": {"has_more": False}
        }))
        start = time.monotonic()
        from anytype_llm_wiki.wiki.bootstrap import wiki_bootstrap
        wiki_bootstrap(space_id=FAKE_SPACE_ID)
        elapsed = time.monotonic() - start
        assert elapsed < 150, f"wiki_bootstrap took {elapsed:.1f}s — exceeds 150s CI timing budget"


class TestBootstrapReadmePrivacyNotice:
    """AC #8: README must contain the verbatim privacy notice from the spec.

    Per post-test council R1 addendum item 5: the verbatim 10-bullet block —
    including the hosted-LLM ToS pass-through paragraph, the Qdrant/Ollama
    off-localhost embedding-inversion warning, the content-rights-and-PII
    paragraph, and the GDPR Art. 4(7) + LGPD Art. 5(VI) controller disclaimer —
    is structurally gated against a fixture file rather than via loose substring
    checks (which would pass on good-faith truncation).
    """

    def _readme_path(self):
        import pathlib
        return pathlib.Path(__file__).parent.parent.parent / "README.md"

    def test_readme_exists_and_is_readable(self):
        """README.md must exist and be readable (so a filesystem failure surfaces clearly)."""
        readme_path = self._readme_path()
        assert readme_path.exists(), f"README.md not found at {readme_path}"
        readme_text = readme_path.read_text(encoding="utf-8")
        assert readme_text, "README.md is empty or unreadable"

    def test_readme_contains_verbatim_privacy_notice(self):
        """README.md must contain the verbatim privacy-and-data-flow block (fixture-gated)."""
        from pathlib import Path
        readme_text = self._readme_path().read_text(encoding="utf-8")
        fixture = Path(__file__).parent / "fixtures" / "readme_privacy_notice_verbatim.md"
        assert fixture.read_text(encoding="utf-8") in readme_text, (
            "README.md does not contain the verbatim privacy-and-data-flow block "
            "from tests/wiki/fixtures/readme_privacy_notice_verbatim.md"
        )


class TestBootstrapInsufficientTokenScope:
    """AC #9: wiki_bootstrap with 403 on create-type returns [CONFIG ERROR] insufficient_token_scope."""

    @respx.mock
    def test_403_on_create_type_returns_config_error(self, monkeypatch):
        """A 403 from the types endpoint must trigger [CONFIG ERROR] insufficient_token_scope."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        respx.post(
            f"{ANYTYPE_BASE}/v1/spaces/{FAKE_SPACE_ID}/types"
        ).mock(return_value=httpx.Response(403, json={"error": "forbidden"}))
        respx.get().mock(return_value=httpx.Response(200, json={
            "data": [], "pagination": {"has_more": False}
        }))
        from anytype_llm_wiki.wiki.bootstrap import wiki_bootstrap
        try:
            result = wiki_bootstrap(space_id=FAKE_SPACE_ID)
            result_str = str(result)
        except Exception as exc:
            result_str = str(exc)
        assert "insufficient_token_scope" in result_str and "[CONFIG ERROR]" in result_str, (
            f"Expected [CONFIG ERROR] insufficient_token_scope, got: {result_str!r}"
        )

    @respx.mock
    def test_insufficient_scope_error_mentions_settings_api(self, monkeypatch):
        """The insufficient_token_scope error must mention 'Settings → API'."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        respx.post().mock(return_value=httpx.Response(403, json={"error": "forbidden"}))
        respx.get().mock(return_value=httpx.Response(200, json={
            "data": [], "pagination": {"has_more": False}
        }))
        from anytype_llm_wiki.wiki.bootstrap import wiki_bootstrap
        try:
            result = wiki_bootstrap(space_id=FAKE_SPACE_ID)
            result_str = str(result)
        except Exception as exc:
            result_str = str(exc)
        # The error must reference Settings → API so operators know where to go
        assert "Settings → API" in result_str, (
            f"Error must mention 'Settings → API': {result_str!r}"
        )


class TestBootstrapSchemaOutdated:
    """AC #13 bootstrap-specific exception: bootstrap on outdated schema proceeds with upgrade.

    wiki_bootstrap on an outdated schema must NOT return [CONFIG ERROR] wiki_schema_outdated.
    Instead it must log info, proceed, and return status='ok' with a schema_upgrade section.
    """

    @respx.mock
    def test_bootstrap_on_outdated_schema_returns_ok(self, monkeypatch):
        """wiki_bootstrap on a space with wiki_schema_version='0.1.0' must return status='ok'."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)

        # Simulate existing types (already bootstrapped with old schema)
        existing_types = [
            {"id": f"t{i}", "key": key, "name": key, "wiki_schema_version": "0.1.0"}
            for i, key in enumerate(CANONICAL_TYPE_KEYS)
        ]
        # Simulate collection with old schema version
        existing_collection = [
            {"id": "coll-001", "name": "Wiki", "wiki_schema_version": "0.1.0"}
        ]

        call_count = {"n": 0}

        def get_response(request, **kwargs):
            url_str = str(request.url)
            if "collections" in url_str or "objects" in url_str:
                return httpx.Response(200, json={
                    "data": existing_collection, "pagination": {"has_more": False}
                })
            return httpx.Response(200, json={
                "data": existing_types, "pagination": {"has_more": False}
            })

        respx.get().mock(side_effect=get_response)
        respx.post().mock(return_value=httpx.Response(200, json={
            "type": {"id": "t_new", "key": "wiki_source"},
            "property": {"id": "p_new", "key": "wiki_description"},
            "option": {"id": "o1", "name": "wiki_ai-research"},
            "object": {"id": "c1", "name": "Wiki"},
        }))
        respx.patch().mock(return_value=httpx.Response(200, json={
            "object": {"id": "coll-001", "name": "Wiki", "wiki_schema_version": "0.2.0"}
        }))

        from anytype_llm_wiki.wiki import types_schema as _ts
        from anytype_llm_wiki.wiki.bootstrap import wiki_bootstrap
        result = wiki_bootstrap(space_id=FAKE_SPACE_ID)
        assert result.get("status") == "ok", (
            f"wiki_bootstrap on outdated schema must return status='ok', got {result.get('status')!r}"
        )
        # Spec line 1604: must include a schema_upgrade section listing added properties.
        assert "schema_upgrade" in result, (
            f"wiki_bootstrap on outdated schema must include 'schema_upgrade' in result; got keys: {list(result.keys())}"
        )
        upgrade = result["schema_upgrade"]
        assert isinstance(upgrade, dict), (
            f"schema_upgrade must be a dict, got {type(upgrade)!r}"
        )
        # Must record from-version (the old schema seeded in the mock) and to-version (current)
        assert "from" in upgrade, (
            f"schema_upgrade missing 'from' key: {upgrade}"
        )
        assert "to" in upgrade, (
            f"schema_upgrade missing 'to' key: {upgrade}"
        )
        assert upgrade["from"] == "0.1.0", (
            f"schema_upgrade['from'] must be '0.1.0' (version seeded by mock), got {upgrade['from']!r}"
        )
        assert upgrade["to"] == _ts.WIKI_SCHEMA_VERSION, (
            f"schema_upgrade['to'] must equal WIKI_SCHEMA_VERSION, got {upgrade['to']!r}"
        )
        # Must list the properties added during the upgrade
        assert "properties_added" in upgrade, (
            f"schema_upgrade missing 'properties_added' key: {upgrade}"
        )
        assert isinstance(upgrade["properties_added"], list), (
            f"schema_upgrade['properties_added'] must be a list, got {type(upgrade['properties_added'])!r}"
        )

    @respx.mock
    def test_bootstrap_on_outdated_schema_does_not_raise_schema_outdated_error(self, monkeypatch):
        """wiki_bootstrap must NOT raise wiki_schema_outdated (unlike other wiki tools)."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        respx.get().mock(return_value=httpx.Response(200, json={
            "data": [{"id": "coll-001", "wiki_schema_version": "0.1.0"}],
            "pagination": {"has_more": False}
        }))
        respx.post().mock(return_value=httpx.Response(200, json={
            "type": {"id": "t1", "key": "wiki_source"},
            "object": {"id": "c1", "name": "Wiki"},
        }))
        respx.patch().mock(return_value=httpx.Response(200, json={
            "object": {"id": "coll-001"}
        }))
        from anytype_llm_wiki.wiki.bootstrap import wiki_bootstrap
        try:
            result = wiki_bootstrap(space_id=FAKE_SPACE_ID)
        except Exception as exc:
            pytest.fail(f"wiki_bootstrap raised on outdated schema: {exc}")
        result_str = str(result)
        assert "wiki_schema_outdated" not in result_str, (
            "wiki_bootstrap must NOT return wiki_schema_outdated — "
            "bootstrap is the remediation tool for this error"
        )


class TestBootstrapSchemaOutdatedV3Plus:
    """AC #13 — v0.3.0+ tools must return wiki_schema_outdated when schema is old.

    These tests are xfail because v0.3.0+ modules do not yet exist.
    Once they land, the xfail marks must be removed and the tests must pass.
    """

    @pytest.mark.xfail(
        reason="v0.3.0 wiki_ingest module not yet implemented; will pass once v0.3.0 ships",
        strict=False,
    )
    def test_wiki_ingest_raises_schema_outdated(self, monkeypatch):
        """wiki_ingest against a space with wiki_schema_version='0.2.0' (older than current) must return [CONFIG ERROR] wiki_schema_outdated."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        from anytype_llm_wiki.wiki.ingest import wiki_ingest  # v0.3.0 module
        # If we get here, the module exists. Seed outdated schema version via mock.
        import respx as _respx, httpx as _httpx
        with _respx.mock:
            _respx.get().mock(return_value=_httpx.Response(200, json={
                "data": [{"id": "coll-001", "wiki_schema_version": "0.2.0"}],
                "pagination": {"has_more": False}
            }))
            result = wiki_ingest(source="https://example.com/paper", space_id=FAKE_SPACE_ID)
        result_str = str(result)
        assert "wiki_schema_outdated" in result_str

    @pytest.mark.xfail(
        reason="v0.4.0 wiki_query module not yet implemented; will pass once v0.4.0 ships",
        strict=False,
    )
    def test_wiki_query_raises_schema_outdated(self, monkeypatch):
        """wiki_query against a space with wiki_schema_version='0.2.0' must return [CONFIG ERROR] wiki_schema_outdated."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        from anytype_llm_wiki.wiki.query import wiki_query  # v0.4.0 module
        import respx as _respx, httpx as _httpx
        with _respx.mock:
            _respx.get().mock(return_value=_httpx.Response(200, json={
                "data": [{"id": "coll-001", "wiki_schema_version": "0.2.0"}],
                "pagination": {"has_more": False}
            }))
            result = wiki_query(question="What is BGE-M3?", space_id=FAKE_SPACE_ID)
        result_str = str(result)
        assert "wiki_schema_outdated" in result_str


class TestBootstrapPatchDecisionScaffolding:
    """AC #14 — patch-decision.md scaffolding ships in v0.2.0.

    v0.2.0 ships the read_patch_decision() scaffolding function.
    v0.3.0/v0.4.0 activation tests are xfail until those modules land.
    """

    def test_read_patch_decision_function_exists(self):
        """wiki.util.read_patch_decision() (or equivalent) must exist in v0.2.0."""
        from anytype_llm_wiki.wiki import util
        assert hasattr(util, "read_patch_decision"), (
            "wiki.util must export read_patch_decision() in v0.2.0"
        )

    def test_read_patch_decision_is_callable(self):
        from anytype_llm_wiki.wiki.util import read_patch_decision
        assert callable(read_patch_decision)

    @pytest.mark.xfail(
        reason="v0.3.0 wiki_ingest not yet implemented; pre-check activated at v0.3.0",
        strict=False,
    )
    def test_wiki_ingest_returns_error_on_missing_patch_decision(self, monkeypatch, tmp_path):
        """wiki_ingest must return [CONFIG ERROR] patch_decision_missing_or_invalid when patch-decision.md is absent."""
        monkeypatch.setenv("ANYTYPE_API_KEY", FAKE_API_KEY)
        monkeypatch.setenv("ANYTYPE_API_URL", ANYTYPE_BASE)
        monkeypatch.setenv("ANYTYPE_API_VERSION", FAKE_API_VERSION)
        # Point ALDEIA_DIR to a tmp dir where patch-decision.md does not exist
        monkeypatch.setenv("ALDEIA_DIR", str(tmp_path))
        from anytype_llm_wiki.wiki.ingest import wiki_ingest
        import respx as _respx, httpx as _httpx
        with _respx.mock:
            _respx.post().mock(return_value=_httpx.Response(200, json={}))
            _respx.get().mock(return_value=_httpx.Response(200, json={
                "data": [], "pagination": {"has_more": False}
            }))
            result = wiki_ingest(source="https://example.com/paper", space_id=FAKE_SPACE_ID)
        result_str = str(result)
        assert "patch_decision_missing_or_invalid" in result_str


class TestBootstrapLiveAPI:
    """Live API test — requires ANYTYPE_API_KEY set in environment.

    Skipped automatically when ANYTYPE_API_KEY is absent from the environment.
    """

    @pytest.fixture(autouse=True)
    def require_live_anytype(self):
        if not os.environ.get("ANYTYPE_API_KEY"):
            pytest.skip("ANYTYPE_API_KEY not set — live-API test skipped")

    def test_live_bootstrap_creates_types(self):
        """Live-API: wiki_bootstrap on a test space creates types and returns status ok.

        Requires ANYTYPE_API_KEY and ANYTYPE_SPACE_ID in environment.
        """
        space_id = os.environ.get("ANYTYPE_SPACE_ID")
        if not space_id:
            pytest.skip("ANYTYPE_SPACE_ID not set — live-API bootstrap test skipped")
        from anytype_llm_wiki.wiki.bootstrap import wiki_bootstrap
        result = wiki_bootstrap(space_id=space_id)
        assert result.get("status") in ("ok", "partial"), (
            f"Live bootstrap returned unexpected status: {result.get('status')}"
        )


class TestFoundSchemaVersionRealShape:
    """_found_schema_version must read the REAL Anytype shape.

    Against a live Anytype API, ``GET /objects`` returns each object's
    ``properties`` as a LIST of ``{"key": ..., "text": ...}`` entries. That list
    branch is the only one that fires in production, yet the upgrade-path test
    seeds the version as a top-level key (the legacy back-compat branch). These
    tests lock the real array-shaped read path (impl-review-r2 SHOULD-FIX-3).
    """

    def test_reads_version_from_list_shaped_properties(self):
        from anytype_llm_wiki.wiki.bootstrap import _found_schema_version

        obj = {
            "id": "obj1",
            "name": "bootstrap 2026-06-03T10:10:00Z",
            "properties": [
                {"key": "wiki_subject", "text": "Wiki"},
                {"key": "wiki_schema_version", "text": "0.2.0"},
            ],
        }
        assert _found_schema_version(obj) == "0.2.0"

    def test_list_shape_without_marker_returns_none(self):
        from anytype_llm_wiki.wiki.bootstrap import _found_schema_version

        obj = {"properties": [{"key": "wiki_subject", "text": "Wiki"}]}
        assert _found_schema_version(obj) is None

    def test_legacy_dict_and_top_level_shapes_still_supported(self):
        from anytype_llm_wiki.wiki.bootstrap import _found_schema_version

        assert _found_schema_version({"wiki_schema_version": "0.1.0"}) == "0.1.0"
        assert (
            _found_schema_version({"properties": {"wiki_schema_version": "0.1.0"}})
            == "0.1.0"
        )

    def test_list_shaped_marker_drives_upgrade_detection(self):
        """End-to-end: an existing object whose list-shaped properties carry an
        OLDER version must trigger the schema_upgrade path."""
        from anytype_llm_wiki.wiki import bootstrap as _b

        older = {
            "id": "old-log",
            "name": "bootstrap old",
            "properties": [{"key": "wiki_schema_version", "text": "0.1.0"}],
        }
        # Drive only the version-detection helpers (no HTTP): the max across
        # objects must be the older version, and it must compare as an upgrade.
        found = _b._max_version(None, _b._found_schema_version(older))
        assert found == "0.1.0"
        assert _b._version_tuple(found) < _b._version_tuple(
            _b.types_schema.WIKI_SCHEMA_VERSION
        )
