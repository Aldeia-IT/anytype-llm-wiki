"""Markdown chunking with metadata."""

import re

from .wiki.util import strip_control_chars


MAX_CHUNK_CHARS = 1500  # ~375 tokens, well within bge-m3's 8192 token limit

# Wiki text properties whose values are embedded when an object has no markdown
# body (ingest-authored objects store prose in properties, not the body). Each
# key maps to a synthetic heading so the chunk reads like a body section.
WIKI_TEXT_PROPERTY_KEYS = frozenset({
    "wiki_facts", "wiki_description", "wiki_definition", "wiki_open_questions",
    "wiki_dimensions", "wiki_verdict", "wiki_question", "wiki_answer",
})
WIKI_PROPERTY_HEADING = {
    "wiki_facts": "Facts", "wiki_description": "Description",
    "wiki_definition": "Definition", "wiki_open_questions": "Open Questions",
    "wiki_dimensions": "Dimensions", "wiki_verdict": "Verdict",
    "wiki_question": "Question", "wiki_answer": "Answer",
}


def chunk_object(obj: dict) -> list[dict]:
    """Split an Anytype object into chunks with metadata.

    Each chunk gets: object_id, space_id, object_name, type_key, heading, text.

    When a markdown body is present it is the sole source of chunks. When the
    body is empty/absent, allowlisted wiki text properties are embedded instead
    (dedup guard: a body and its properties are never both emitted).
    """
    object_id = obj.get("id", "")
    space_id = obj.get("space_id", "")
    object_name = obj.get("name", "")
    type_key = obj.get("type", {}).get("key", "unknown")

    markdown = obj.get("markdown", "") or ""
    if markdown.strip():
        return _chunk_body(markdown, object_id, space_id, object_name, type_key)

    return _chunk_properties(obj, object_id, space_id, object_name, type_key)


def _chunk_body(
    markdown: str, object_id: str, space_id: str, object_name: str, type_key: str
) -> list[dict]:
    sections = _split_by_headings(markdown)
    chunks = []

    for heading, text in sections:
        text = text.strip()
        if not text:
            continue
        # Split oversized sections by paragraphs
        for sub_text in _split_large(text):
            chunks.append({
                "object_id": object_id,
                "space_id": space_id,
                "object_name": object_name,
                "type_key": type_key,
                "heading": heading,
                "text": sub_text,
            })

    return chunks


def _chunk_properties(
    obj: dict, object_id: str, space_id: str, object_name: str, type_key: str
) -> list[dict]:
    chunks = []
    for prop in obj.get("properties", []):
        if not isinstance(prop, dict):
            continue
        key = prop.get("key")
        if key not in WIKI_TEXT_PROPERTY_KEYS:
            continue
        text = strip_control_chars(prop.get("text") or "")
        if not text.strip():
            continue
        heading = WIKI_PROPERTY_HEADING[key]
        for sub_text in _split_large(text.strip()):
            chunks.append({
                "object_id": object_id,
                "space_id": space_id,
                "object_name": object_name,
                "type_key": type_key,
                "heading": heading,
                "text": sub_text,
            })

    return chunks


def _split_by_headings(markdown: str) -> list[tuple[str, str]]:
    """Split markdown into (heading, body) pairs."""
    pattern = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)
    matches = list(pattern.finditer(markdown))

    if not matches:
        return [("", markdown)]

    sections = []
    # Content before first heading
    pre = markdown[: matches[0].start()].strip()
    if pre:
        sections.append(("", pre))

    for i, m in enumerate(matches):
        heading = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        body = markdown[start:end].strip()
        if body:
            sections.append((heading, body))

    return sections


def _split_large(text: str) -> list[str]:
    """Split text exceeding MAX_CHUNK_CHARS by paragraphs, then hard-split."""
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]

    paragraphs = re.split(r"\n\s*\n", text)
    result = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) + 2 <= MAX_CHUNK_CHARS:
            current = f"{current}\n\n{para}" if current else para
        else:
            if current:
                result.append(current)
            # Hard-split paragraphs that are themselves too large
            if len(para) > MAX_CHUNK_CHARS:
                for i in range(0, len(para), MAX_CHUNK_CHARS):
                    result.append(para[i : i + MAX_CHUNK_CHARS])
                current = ""
            else:
                current = para

    if current:
        result.append(current)

    return result
