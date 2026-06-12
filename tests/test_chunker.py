"""Tests for markdown chunker — existing tests plus v0.3.0 property-embedding extension.

Existing tests cover the body-chunk path. The new tests (§9.2) cover AC-P1..P9 for the
property-embedding extension to chunk_object. Tests must FAIL until chunker.py is extended
with WIKI_TEXT_PROPERTY_KEYS, WIKI_PROPERTY_HEADING, and the property-chunk path.
"""

import pytest

from anytype_llm_wiki.chunker import chunk_object, _split_by_headings, _split_large, MAX_CHUNK_CHARS


def _make_obj(markdown: str, name: str = "Test", type_key: str = "page") -> dict:
    return {
        "id": "obj-1",
        "space_id": "space-1",
        "name": name,
        "type": {"key": type_key},
        "markdown": markdown,
    }


def _make_wiki_obj(
    properties: list[dict] | None = None,
    markdown: str = "",
    name: str = "Test Entity",
    type_key: str = "wiki_entity",
    obj_id: str = "eid-1",
    space_id: str = "space-1",
) -> dict:
    """Build a wiki object dict for property-chunk tests.

    Note (CTO-A3 addendum item 2): the body-chunk path reads obj.get("markdown","").
    The 'markdown' key assumption is verified during gate V1 against the live API;
    the tests here use it as specified until V1 confirms or corrects the key.
    """
    obj: dict = {
        "id": obj_id,
        "space_id": space_id,
        "name": name,
        "type": {"key": type_key},
        "markdown": markdown,
    }
    if properties is not None:
        obj["properties"] = properties
    return obj


class TestSplitByHeadings:
    def test_no_headings(self):
        sections = _split_by_headings("Just some text\nwith lines")
        assert len(sections) == 1
        assert sections[0] == ("", "Just some text\nwith lines")

    def test_single_heading(self):
        md = "## Title\nContent here"
        sections = _split_by_headings(md)
        assert len(sections) == 1
        assert sections[0][0] == "Title"
        assert "Content here" in sections[0][1]

    def test_multiple_headings(self):
        md = "## First\nContent 1\n## Second\nContent 2\n### Third\nContent 3"
        sections = _split_by_headings(md)
        assert len(sections) == 3
        assert sections[0][0] == "First"
        assert sections[1][0] == "Second"
        assert sections[2][0] == "Third"

    def test_content_before_first_heading(self):
        md = "Preamble text\n\n## Heading\nBody"
        sections = _split_by_headings(md)
        assert len(sections) == 2
        assert sections[0][0] == ""
        assert "Preamble" in sections[0][1]
        assert sections[1][0] == "Heading"

    def test_empty_sections_skipped(self):
        md = "## Heading A\n\n## Heading B\nActual content"
        sections = _split_by_headings(md)
        # Heading A has no content, should be skipped
        assert all(body.strip() for _, body in sections)


class TestSplitLarge:
    def test_small_text_unchanged(self):
        text = "Short text"
        assert _split_large(text) == ["Short text"]

    def test_large_text_split_by_paragraphs(self):
        para = "A" * 500
        text = f"{para}\n\n{para}\n\n{para}\n\n{para}"
        result = _split_large(text)
        assert len(result) > 1
        assert all(len(r) <= MAX_CHUNK_CHARS for r in result)

    def test_single_huge_paragraph_hard_split(self):
        text = "X" * (MAX_CHUNK_CHARS * 3)
        result = _split_large(text)
        assert len(result) == 3
        assert all(len(r) <= MAX_CHUNK_CHARS for r in result)


class TestChunkObject:
    def test_empty_markdown(self):
        obj = _make_obj("")
        assert chunk_object(obj) == []

    def test_none_markdown(self):
        obj = _make_obj("")
        obj["markdown"] = None
        assert chunk_object(obj) == []

    def test_basic_chunking(self):
        obj = _make_obj("## Section\nSome content here", name="My Page")
        chunks = chunk_object(obj)
        assert len(chunks) == 1
        assert chunks[0]["object_id"] == "obj-1"
        assert chunks[0]["space_id"] == "space-1"
        assert chunks[0]["object_name"] == "My Page"
        assert chunks[0]["type_key"] == "page"
        assert chunks[0]["heading"] == "Section"
        assert "Some content" in chunks[0]["text"]

    def test_multiple_sections(self):
        md = "## A\nContent A\n## B\nContent B\n## C\nContent C"
        chunks = chunk_object(_make_obj(md))
        assert len(chunks) == 3
        headings = [c["heading"] for c in chunks]
        assert headings == ["A", "B", "C"]

    def test_metadata_preserved(self):
        obj = _make_obj("Some plain text", name="Notes", type_key="note")
        chunks = chunk_object(obj)
        assert len(chunks) == 1
        assert chunks[0]["type_key"] == "note"
        assert chunks[0]["object_name"] == "Notes"


# ---------------------------------------------------------------------------
# v0.3.0 Property-Embedding Tests (§9.2, AC-P1 through AC-P9)
# These tests will FAIL until chunker.py is extended with WIKI_TEXT_PROPERTY_KEYS.
# ---------------------------------------------------------------------------


class TestWikiTextPropertyKeysConstant:
    """Guard that WIKI_TEXT_PROPERTY_KEYS and WIKI_PROPERTY_HEADING exist and are correct."""

    def test_wiki_text_property_keys_exists(self):
        """WIKI_TEXT_PROPERTY_KEYS must be importable from chunker (AC-P1, Decision 1)."""
        from anytype_llm_wiki.chunker import WIKI_TEXT_PROPERTY_KEYS
        assert WIKI_TEXT_PROPERTY_KEYS is not None

    def test_wiki_text_property_keys_is_frozenset(self):
        """WIKI_TEXT_PROPERTY_KEYS must be a frozenset (Decision 1 §4.1)."""
        from anytype_llm_wiki.chunker import WIKI_TEXT_PROPERTY_KEYS
        assert isinstance(WIKI_TEXT_PROPERTY_KEYS, frozenset)

    def test_wiki_text_property_keys_has_eight_entries(self):
        """Allowlist must contain exactly 8 keys (Decision 1 §4.1)."""
        from anytype_llm_wiki.chunker import WIKI_TEXT_PROPERTY_KEYS
        assert len(WIKI_TEXT_PROPERTY_KEYS) == 8

    def test_wiki_text_property_keys_exact_set(self):
        """Allowlist must contain the 8 specified keys and no others (Decision 1 §4.1)."""
        from anytype_llm_wiki.chunker import WIKI_TEXT_PROPERTY_KEYS
        expected = frozenset({
            "wiki_facts",
            "wiki_description",
            "wiki_definition",
            "wiki_open_questions",
            "wiki_dimensions",
            "wiki_verdict",
            "wiki_question",
            "wiki_answer",
        })
        assert WIKI_TEXT_PROPERTY_KEYS == expected

    def test_wiki_excerpt_not_in_allowlist(self):
        """wiki_excerpt (wiki_source) must NOT be in WIKI_TEXT_PROPERTY_KEYS (AC-P6)."""
        from anytype_llm_wiki.chunker import WIKI_TEXT_PROPERTY_KEYS
        assert "wiki_excerpt" not in WIKI_TEXT_PROPERTY_KEYS

    def test_wiki_property_heading_exists(self):
        """WIKI_PROPERTY_HEADING must be importable from chunker (Decision 1 §4.1)."""
        from anytype_llm_wiki.chunker import WIKI_PROPERTY_HEADING
        assert WIKI_PROPERTY_HEADING is not None

    def test_wiki_property_heading_maps_all_eight_keys(self):
        """WIKI_PROPERTY_HEADING must map all 8 allowlist keys to display names (§4.1)."""
        from anytype_llm_wiki.chunker import WIKI_PROPERTY_HEADING, WIKI_TEXT_PROPERTY_KEYS
        for key in WIKI_TEXT_PROPERTY_KEYS:
            assert key in WIKI_PROPERTY_HEADING, f"WIKI_PROPERTY_HEADING missing key: {key!r}"

    def test_wiki_property_heading_values(self):
        """WIKI_PROPERTY_HEADING values must match the spec's display-name map (Decision 1 §4.1)."""
        from anytype_llm_wiki.chunker import WIKI_PROPERTY_HEADING
        expected_headings = {
            "wiki_facts": "Facts",
            "wiki_description": "Description",
            "wiki_definition": "Definition",
            "wiki_open_questions": "Open Questions",
            "wiki_dimensions": "Dimensions",
            "wiki_verdict": "Verdict",
            "wiki_question": "Question",
            "wiki_answer": "Answer",
        }
        for key, heading in expected_headings.items():
            assert WIKI_PROPERTY_HEADING.get(key) == heading, (
                f"WIKI_PROPERTY_HEADING[{key!r}] expected {heading!r}, got {WIKI_PROPERTY_HEADING.get(key)!r}"
            )


class TestPropertyChunkEmitted:
    """AC-P1: wiki_entity with wiki_facts + empty body emits at least one chunk, heading='Facts'."""

    def test_property_chunk_emitted(self):
        """AC-P1: wiki_entity object with wiki_facts populated, no body → 1+ chunks, heading='Facts'.

        Covers: §9.2 test_property_chunk_emitted, AC-P1.
        """
        obj = _make_wiki_obj(
            properties=[{"key": "wiki_facts", "text": "- GPT-4 is a large language model\n- Released 2023"}],
            markdown="",
            type_key="wiki_entity",
        )
        chunks = chunk_object(obj)
        assert len(chunks) >= 1, "Expected at least one chunk from wiki_facts property"
        assert any(c["heading"] == "Facts" for c in chunks), (
            f"Expected heading='Facts', got headings: {[c['heading'] for c in chunks]}"
        )
        assert any("GPT-4" in c["text"] for c in chunks), (
            "Expected wiki_facts text in chunk"
        )


class TestAllAllowlistKeysEmitChunks:
    """AC-P1/P3: each of the 8 allowlist keys emits a chunk with the correct heading."""

    @pytest.mark.parametrize("prop_key,expected_heading", [
        ("wiki_facts", "Facts"),
        ("wiki_description", "Description"),
        ("wiki_definition", "Definition"),
        ("wiki_open_questions", "Open Questions"),
        ("wiki_dimensions", "Dimensions"),
        ("wiki_verdict", "Verdict"),
        ("wiki_question", "Question"),
        ("wiki_answer", "Answer"),
    ])
    def test_all_allowlist_keys_emit_chunks(self, prop_key: str, expected_heading: str):
        """AC-P1 (all 8 keys): each allowlisted property key yields chunk with correct heading.

        Covers: §9.2 test_all_allowlist_keys_emit_chunks.
        """
        obj = _make_wiki_obj(
            properties=[{"key": prop_key, "text": f"Some content for {prop_key}"}],
            markdown="",
        )
        chunks = chunk_object(obj)
        assert len(chunks) >= 1, f"Expected chunk(s) for property key {prop_key!r}, got none"
        headings = [c["heading"] for c in chunks]
        assert expected_heading in headings, (
            f"Property {prop_key!r}: expected heading {expected_heading!r}, got {headings!r}"
        )


class TestNonWikiPropertyNotEmitted:
    """AC-P3: non-wiki properties (description, status) do not produce property chunks."""

    def test_non_wiki_property_not_emitted(self):
        """AC-P3: obj with only non-wiki keys (description, status) → 0 property chunks.

        Covers: §9.2 test_non_wiki_property_not_emitted.
        """
        obj = _make_wiki_obj(
            properties=[
                {"key": "description", "text": "A regular description"},
                {"key": "status", "text": "active"},
                {"key": "category", "text": "general"},
            ],
            markdown="",
            type_key="page",
        )
        chunks = chunk_object(obj)
        assert chunks == [], (
            f"Expected 0 chunks for non-wiki properties, got {len(chunks)}: {chunks}"
        )


class TestBodyPresentDedup:
    """AC-P4: wiki_entity with non-empty markdown body → body chunks only, no property chunks."""

    def test_body_present_dedup(self):
        """AC-P4: obj with non-empty markdown + wiki_facts → body chunks only, no property chunks.

        Covers: §9.2 test_body_present_dedup. Property chunks are only emitted when body is empty.
        """
        obj = _make_wiki_obj(
            properties=[{"key": "wiki_facts", "text": "- Key fact 1\n- Key fact 2"}],
            markdown="## Introduction\nThis is a manually written body with real content.",
            type_key="wiki_entity",
        )
        chunks = chunk_object(obj)
        assert len(chunks) >= 1, "Expected body chunks when markdown is non-empty"
        # All chunks must come from body sections (heading = "Introduction" or similar markdown heading)
        for chunk in chunks:
            assert chunk["heading"] != "Facts", (
                f"Property chunk with heading='Facts' emitted despite non-empty markdown body: {chunk}"
            )


class TestWikiExcerptExcluded:
    """AC-P6: wiki_source with wiki_excerpt populated and no body → 0 property chunks."""

    def test_wiki_excerpt_excluded(self):
        """AC-P6: wiki_source obj with wiki_excerpt populated, no body → 0 chunks.

        wiki_excerpt is NOT in WIKI_TEXT_PROPERTY_KEYS — it must be excluded.
        Covers: §9.2 test_wiki_excerpt_excluded.
        """
        obj = _make_wiki_obj(
            properties=[{"key": "wiki_excerpt", "text": "This is an excerpt from the source."}],
            markdown="",
            type_key="wiki_source",
        )
        chunks = chunk_object(obj)
        assert chunks == [], (
            f"Expected 0 chunks for wiki_excerpt property (excluded from allowlist), got {len(chunks)}"
        )


class TestOversizedWikiFactsSplit:
    """AC-P5: wiki_facts value > MAX_CHUNK_CHARS (1500) → 2+ chunks."""

    def test_oversized_wiki_facts_split(self):
        """AC-P5: wiki_facts value of 3000 chars → 2+ chunks (split behavior, _split_large).

        Covers: §9.2 test_oversized_wiki_facts_split.
        """
        long_text = ("- A long fact about a thing\n" * 120)  # well over 1500 chars
        assert len(long_text) > MAX_CHUNK_CHARS, "Test setup: text must exceed MAX_CHUNK_CHARS"
        obj = _make_wiki_obj(
            properties=[{"key": "wiki_facts", "text": long_text}],
            markdown="",
            type_key="wiki_entity",
        )
        chunks = chunk_object(obj)
        assert len(chunks) >= 2, (
            f"Expected 2+ chunks for oversized wiki_facts, got {len(chunks)}"
        )
        for chunk in chunks:
            assert len(chunk["text"]) <= MAX_CHUNK_CHARS, (
                f"Chunk text exceeds MAX_CHUNK_CHARS ({MAX_CHUNK_CHARS}): {len(chunk['text'])} chars"
            )


class TestEmptyPropertyNotEmitted:
    """AC-P1: allowlisted key with empty text value is not emitted."""

    def test_empty_property_not_emitted(self):
        """AC-P1 edge: allowlisted key present but text is empty string → not emitted.

        Covers: §9.2 test_empty_property_not_emitted.
        """
        obj = _make_wiki_obj(
            properties=[
                {"key": "wiki_facts", "text": ""},
                {"key": "wiki_description", "text": "   "},  # whitespace-only
            ],
            markdown="",
            type_key="wiki_entity",
        )
        chunks = chunk_object(obj)
        assert chunks == [], (
            f"Expected 0 chunks for empty/whitespace property values, got {len(chunks)}"
        )


class TestPropertyChunkMissingSpaceIdTolerated:
    """AC-P8 (B3): chunk_object on a property-only object missing space_id/id does not raise KeyError."""

    def test_property_chunk_missing_space_id_tolerated(self):
        """AC-P8/B3: property-only obj missing space_id (and id) → no KeyError; space_id/object_id default to ''.

        Covers: §9.2 test_property_chunk_missing_space_id_tolerated.
        The new property-chunk path is reachable precisely for empty-body objects, so
        the B3 hardening (obj.get instead of obj[]) is critical here.
        """
        obj = {
            # Deliberately omit "id" and "space_id" keys
            "name": "Orphaned Entity",
            "type": {"key": "wiki_entity"},
            "markdown": "",
            "properties": [{"key": "wiki_facts", "text": "- Fact about this entity"}],
        }
        # Must not raise KeyError
        try:
            chunks = chunk_object(obj)
        except KeyError as exc:
            pytest.fail(f"chunk_object raised KeyError on missing space_id/id: {exc}")
        assert len(chunks) >= 1, "Expected at least one chunk from wiki_facts"
        for chunk in chunks:
            assert chunk.get("space_id") == "", (
                f"Expected space_id='' when missing, got {chunk.get('space_id')!r}"
            )
            assert chunk.get("object_id") == "", (
                f"Expected object_id='' when missing, got {chunk.get('object_id')!r}"
            )


# ---------------------------------------------------------------------------
# v1 (issue #323) — Chunker date-payload tests (AC-F8, AC-F9)
# These tests FAIL until chunk_object extracts last_modified_date and injects
# it into every chunk.
# ---------------------------------------------------------------------------


class TestChunkerLastModifiedDate:
    """AC-F8/F9: chunk_object injects last_modified_date when present; omits when absent."""

    def test_chunker_writes_last_modified_date(self):
        """AC-F8: entity with body + last_modified_date property → every chunk carries it."""
        from anytype_llm_wiki.chunker import chunk_object

        obj = {
            "id": "ent-1",
            "space_id": "sp-1",
            "name": "Neural Networks",
            "type": {"key": "wiki_entity"},
            "markdown": "# Overview\nTransformers use attention.",
            "properties": [{"key": "last_modified_date", "date": "2026-05-01T00:00:00+00:00"}],
        }
        chunks = chunk_object(obj)
        assert chunks, "Expected at least one chunk from the markdown body"
        assert all(c.get("last_modified_date") == "2026-05-01T00:00:00+00:00" for c in chunks), (
            f"Every chunk must carry last_modified_date='2026-05-01T00:00:00+00:00'. "
            f"Chunk dates: {[c.get('last_modified_date') for c in chunks]}"
        )

    def test_chunker_property_concept_date_and_absence(self):
        """AC-F9: property-only concept with date → all chunks carry it;
        object without date → field absent from chunks.
        """
        from anytype_llm_wiki.chunker import chunk_object

        obj = {
            "id": "con-1",
            "space_id": "sp-1",
            "name": "Attention",
            "type": {"key": "wiki_concept"},
            "markdown": "",
            "properties": [
                {"key": "wiki_definition", "text": "A mechanism for weighting inputs."},
                {"key": "last_modified_date", "date": "2026-05-02T00:00:00+00:00"},
            ],
        }
        chunks = chunk_object(obj)
        assert chunks, "Expected at least one property chunk"
        assert all(c.get("last_modified_date") == "2026-05-02T00:00:00+00:00" for c in chunks), (
            f"Every chunk must carry last_modified_date='2026-05-02T00:00:00+00:00'. "
            f"Got: {[c.get('last_modified_date') for c in chunks]}"
        )

        # Same object but without last_modified_date property
        obj_nodate = {**obj, "properties": [{"key": "wiki_definition", "text": "A mechanism."}]}
        chunks2 = chunk_object(obj_nodate)
        assert chunks2, "Expected at least one property chunk from wiki_definition"
        assert all("last_modified_date" not in c for c in chunks2), (
            f"Chunks must NOT carry last_modified_date when property is absent. "
            f"Got: {[c.get('last_modified_date') for c in chunks2]}"
        )


class TestPropertyValueSanitized:
    """AC#16 delta (SF2): property values containing bidi/control chars are sanitized on write.

    The bidi/control-char sanitizer must be applied to property values, not only names.
    This widens the embedding surface protection: AC#16 extended assertion.
    Covers: §9.2 test_property_value_sanitized.
    """

    def test_property_value_sanitized(self):
        """AC#16 delta: property value with U+FEFF/U+2028/U+2029/tag-chars → sanitizer strips them.

        Asserts the sanitizer is applied to wiki_facts text (a property value)
        so the embedded chunk does not carry invisible control characters.
        NOTE: This test verifies the sanitized output from chunk_object, asserting
        that the emitted chunk's text does not contain the forbidden codepoints.
        The sanitizer is applied during write (ingest pipeline), or alternatively
        the chunker applies it before embedding.
        """
        # Build property value containing forbidden codepoints
        forbidden_bom = "﻿"          # BOM
        forbidden_ls = " "           # LINE SEPARATOR
        forbidden_ps = " "           # PARAGRAPH SEPARATOR
        forbidden_tag = "\U000E0020"      # TAG SPACE (U+E0020 — first in tag block)
        raw_value = (
            f"{forbidden_bom}Some facts{forbidden_ls}about the topic"
            f"{forbidden_ps}and more{forbidden_tag}content"
        )
        obj = _make_wiki_obj(
            properties=[{"key": "wiki_facts", "text": raw_value}],
            markdown="",
            type_key="wiki_entity",
        )
        chunks = chunk_object(obj)
        assert len(chunks) >= 1, "Expected at least one chunk"
        for chunk in chunks:
            text = chunk["text"]
            assert forbidden_bom not in text, "U+FEFF (BOM) must be stripped from property chunk text"
            assert forbidden_ls not in text, "U+2028 (LINE SEPARATOR) must be stripped from property chunk text"
            assert forbidden_ps not in text, "U+2029 (PARAGRAPH SEPARATOR) must be stripped from property chunk text"
            assert forbidden_tag not in text, "U+E0020 (TAG SPACE) must be stripped from property chunk text"
