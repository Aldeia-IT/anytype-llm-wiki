"""Markdown chunking with metadata."""

import re


MAX_CHUNK_CHARS = 1500  # ~375 tokens, well within bge-m3's 8192 token limit


def chunk_object(obj: dict) -> list[dict]:
    """Split an Anytype object's markdown body into chunks with metadata.

    Each chunk gets: object_id, space_id, object_name, type_key, heading, text.
    """
    markdown = obj.get("markdown", "") or ""
    if not markdown.strip():
        return []

    object_id = obj["id"]
    space_id = obj["space_id"]
    object_name = obj.get("name", "")
    type_key = obj.get("type", {}).get("key", "unknown")

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
