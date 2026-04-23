"""Tests for wiki/types_schema.py — canonical type_keys, property definitions, WIKI_SCHEMA_VERSION.

Covers AC #1 (property names match spec) and the schema version contract (AC #13 prerequisite).
"""

import re
import pytest


class TestWikiSchemaVersion:
    def test_module_exports_wiki_schema_version(self):
        """WIKI_SCHEMA_VERSION must be exported from types_schema module."""
        from anytype_llm_wiki.wiki.types_schema import WIKI_SCHEMA_VERSION  # noqa: F401

    def test_wiki_schema_version_is_string(self):
        """WIKI_SCHEMA_VERSION must be a string."""
        from anytype_llm_wiki.wiki.types_schema import WIKI_SCHEMA_VERSION
        assert isinstance(WIKI_SCHEMA_VERSION, str)

    def test_wiki_schema_version_semver_format(self):
        """WIKI_SCHEMA_VERSION must match semver-ish format x.y.z."""
        from anytype_llm_wiki.wiki.types_schema import WIKI_SCHEMA_VERSION
        assert re.match(r"^\d+\.\d+\.\d+$", WIKI_SCHEMA_VERSION), (
            f"WIKI_SCHEMA_VERSION={WIKI_SCHEMA_VERSION!r} does not match x.y.z"
        )


class TestCanonicalTypeKeys:
    """The six canonical type_key values must be defined exactly as specified."""

    def test_wiki_source_type_key(self):
        """wiki_source type key must be present in the schema."""
        from anytype_llm_wiki.wiki.types_schema import WIKI_TYPES
        keys = [t["type_key"] for t in WIKI_TYPES]
        assert "wiki_source" in keys

    def test_wiki_entity_type_key(self):
        """wiki_entity type key must be present."""
        from anytype_llm_wiki.wiki.types_schema import WIKI_TYPES
        keys = [t["type_key"] for t in WIKI_TYPES]
        assert "wiki_entity" in keys

    def test_wiki_concept_type_key(self):
        """wiki_concept type key must be present."""
        from anytype_llm_wiki.wiki.types_schema import WIKI_TYPES
        keys = [t["type_key"] for t in WIKI_TYPES]
        assert "wiki_concept" in keys

    def test_wiki_comparison_type_key(self):
        """wiki_comparison type key must be present."""
        from anytype_llm_wiki.wiki.types_schema import WIKI_TYPES
        keys = [t["type_key"] for t in WIKI_TYPES]
        assert "wiki_comparison" in keys

    def test_wiki_query_type_key(self):
        """wiki_query type key must be present."""
        from anytype_llm_wiki.wiki.types_schema import WIKI_TYPES
        keys = [t["type_key"] for t in WIKI_TYPES]
        assert "wiki_query" in keys

    def test_wiki_log_type_key(self):
        """wiki_log type key must be present."""
        from anytype_llm_wiki.wiki.types_schema import WIKI_TYPES
        keys = [t["type_key"] for t in WIKI_TYPES]
        assert "wiki_log" in keys

    def test_exactly_six_types(self):
        """Exactly six types must be defined — no more, no fewer."""
        from anytype_llm_wiki.wiki.types_schema import WIKI_TYPES
        keys = [t["type_key"] for t in WIKI_TYPES]
        assert len(keys) == 6, f"Expected 6 types, got {len(keys)}: {keys}"

    def test_all_type_keys_have_wiki_prefix(self):
        """All type keys must be prefixed wiki_."""
        from anytype_llm_wiki.wiki.types_schema import WIKI_TYPES
        for t in WIKI_TYPES:
            assert t["type_key"].startswith("wiki_"), (
                f"type_key {t['type_key']!r} missing wiki_ prefix"
            )


class TestSourceProperties:
    """Source type must expose exactly the specified property keys."""

    def _source_props(self):
        from anytype_llm_wiki.wiki.types_schema import WIKI_TYPES
        for t in WIKI_TYPES:
            if t["type_key"] == "wiki_source":
                return [p["property_key"] for p in t["properties"]]
        pytest.fail("wiki_source not found in WIKI_TYPES")

    def test_source_has_wiki_url(self):
        assert "wiki_url" in self._source_props()

    def test_source_has_wiki_file_path(self):
        assert "wiki_file_path" in self._source_props()

    def test_source_has_wiki_excerpt(self):
        assert "wiki_excerpt" in self._source_props()

    def test_source_has_wiki_ingested_at(self):
        assert "wiki_ingested_at" in self._source_props()

    def test_source_has_wiki_domain_tags(self):
        assert "wiki_domain_tags" in self._source_props()

    def test_source_has_wiki_source_type(self):
        assert "wiki_source_type" in self._source_props()


class TestEntityProperties:
    """Entity type must expose exactly the specified property keys."""

    def _entity_props(self):
        from anytype_llm_wiki.wiki.types_schema import WIKI_TYPES
        for t in WIKI_TYPES:
            if t["type_key"] == "wiki_entity":
                return [p["property_key"] for p in t["properties"]]
        pytest.fail("wiki_entity not found in WIKI_TYPES")

    def test_entity_has_wiki_description(self):
        assert "wiki_description" in self._entity_props()

    def test_entity_has_wiki_facts(self):
        assert "wiki_facts" in self._entity_props()

    def test_entity_has_wiki_relations(self):
        assert "wiki_relations" in self._entity_props()

    def test_entity_has_wiki_sources(self):
        assert "wiki_sources" in self._entity_props()

    def test_entity_has_wiki_domain_tags(self):
        assert "wiki_domain_tags" in self._entity_props()

    def test_entity_has_wiki_contradictions(self):
        assert "wiki_contradictions" in self._entity_props()

    def test_entity_has_wiki_status(self):
        assert "wiki_status" in self._entity_props()

    def test_entity_has_wiki_last_reviewed(self):
        assert "wiki_last_reviewed" in self._entity_props()


class TestConceptProperties:
    """Concept type must expose exactly the specified property keys."""

    def _concept_props(self):
        from anytype_llm_wiki.wiki.types_schema import WIKI_TYPES
        for t in WIKI_TYPES:
            if t["type_key"] == "wiki_concept":
                return [p["property_key"] for p in t["properties"]]
        pytest.fail("wiki_concept not found in WIKI_TYPES")

    def test_concept_has_wiki_definition(self):
        assert "wiki_definition" in self._concept_props()

    def test_concept_has_wiki_open_questions(self):
        assert "wiki_open_questions" in self._concept_props()

    def test_concept_has_wiki_related(self):
        """Concept uses wiki_related (not wiki_relations — that is Entity's field)."""
        assert "wiki_related" in self._concept_props()

    def test_concept_has_wiki_sources(self):
        assert "wiki_sources" in self._concept_props()

    def test_concept_has_wiki_domain_tags(self):
        assert "wiki_domain_tags" in self._concept_props()

    def test_concept_has_wiki_contradictions(self):
        assert "wiki_contradictions" in self._concept_props()

    def test_concept_has_wiki_status(self):
        assert "wiki_status" in self._concept_props()


class TestComparisonProperties:
    """Comparison type must expose exactly the specified property keys."""

    def _comparison_props(self):
        from anytype_llm_wiki.wiki.types_schema import WIKI_TYPES
        for t in WIKI_TYPES:
            if t["type_key"] == "wiki_comparison":
                return [p["property_key"] for p in t["properties"]]
        pytest.fail("wiki_comparison not found in WIKI_TYPES")

    def test_comparison_has_wiki_subjects(self):
        assert "wiki_subjects" in self._comparison_props()

    def test_comparison_has_wiki_dimensions(self):
        assert "wiki_dimensions" in self._comparison_props()

    def test_comparison_has_wiki_verdict(self):
        assert "wiki_verdict" in self._comparison_props()

    def test_comparison_has_wiki_sources(self):
        assert "wiki_sources" in self._comparison_props()


class TestQueryProperties:
    """Query type must expose exactly the specified property keys."""

    def _query_props(self):
        from anytype_llm_wiki.wiki.types_schema import WIKI_TYPES
        for t in WIKI_TYPES:
            if t["type_key"] == "wiki_query":
                return [p["property_key"] for p in t["properties"]]
        pytest.fail("wiki_query not found in WIKI_TYPES")

    def test_query_has_wiki_question(self):
        assert "wiki_question" in self._query_props()

    def test_query_has_wiki_answer(self):
        assert "wiki_answer" in self._query_props()

    def test_query_has_wiki_drew_from(self):
        assert "wiki_drew_from" in self._query_props()

    def test_query_has_wiki_asked_at(self):
        assert "wiki_asked_at" in self._query_props()


class TestWikiLogProperties:
    """WikiLog type must expose exactly the specified property keys."""

    def _log_props(self):
        from anytype_llm_wiki.wiki.types_schema import WIKI_TYPES
        for t in WIKI_TYPES:
            if t["type_key"] == "wiki_log":
                return [p["property_key"] for p in t["properties"]]
        pytest.fail("wiki_log not found in WIKI_TYPES")

    def test_log_has_wiki_action(self):
        assert "wiki_action" in self._log_props()

    def test_log_has_wiki_subject(self):
        assert "wiki_subject" in self._log_props()

    def test_log_has_wiki_objects_created(self):
        assert "wiki_objects_created" in self._log_props()

    def test_log_has_wiki_objects_updated(self):
        assert "wiki_objects_updated" in self._log_props()

    def test_log_has_wiki_timestamp(self):
        assert "wiki_timestamp" in self._log_props()

    def test_log_has_wiki_notes(self):
        assert "wiki_notes" in self._log_props()


class TestDefaultDomainTags:
    """Default domain tags must match the exact list in the spec."""

    EXPECTED_TAGS = {
        "wiki_ai-research",
        "wiki_infrastructure",
        "wiki_business",
        "wiki_engineering",
        "wiki_governance",
        "wiki_science",
        "wiki_other",
    }

    def test_default_domain_tags_exported(self):
        """DEFAULT_DOMAIN_TAGS constant must be exported from types_schema."""
        from anytype_llm_wiki.wiki.types_schema import DEFAULT_DOMAIN_TAGS  # noqa: F401

    def test_default_domain_tags_exact_set(self):
        """DEFAULT_DOMAIN_TAGS must match exactly the 7 tags from the spec."""
        from anytype_llm_wiki.wiki.types_schema import DEFAULT_DOMAIN_TAGS
        assert set(DEFAULT_DOMAIN_TAGS) == self.EXPECTED_TAGS, (
            f"Tag mismatch. Extra: {set(DEFAULT_DOMAIN_TAGS) - self.EXPECTED_TAGS}, "
            f"Missing: {self.EXPECTED_TAGS - set(DEFAULT_DOMAIN_TAGS)}"
        )

    def test_default_domain_tags_all_have_wiki_prefix(self):
        """All default domain tags must start with wiki_."""
        from anytype_llm_wiki.wiki.types_schema import DEFAULT_DOMAIN_TAGS
        for tag in DEFAULT_DOMAIN_TAGS:
            assert tag.startswith("wiki_"), f"Tag {tag!r} missing wiki_ prefix"
