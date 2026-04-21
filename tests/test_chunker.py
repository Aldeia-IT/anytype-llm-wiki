"""Tests for markdown chunker."""

from anytype_llm_wiki.chunker import chunk_object, _split_by_headings, _split_large, MAX_CHUNK_CHARS


def _make_obj(markdown: str, name: str = "Test", type_key: str = "page") -> dict:
    return {
        "id": "obj-1",
        "space_id": "space-1",
        "name": name,
        "type": {"key": type_key},
        "markdown": markdown,
    }


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
