"""Markdown chunking with metadata."""

import re

from .wiki.util import scrub_url_secrets, strip_control_chars


MAX_CHUNK_CHARS = 1500  # ~375 tokens, well within bge-m3's 8192 token limit

# Wiki text properties whose values are embedded when an object has no markdown
# body (ingest-authored objects store prose in properties, not the body). Each
# key maps to a synthetic heading so the chunk reads like a body section.
WIKI_TEXT_PROPERTY_KEYS = frozenset({
    "wiki_facts", "wiki_description", "wiki_definition", "wiki_open_questions",
    "wiki_dimensions", "wiki_verdict", "wiki_question", "wiki_answer",
    "wiki_excerpt",  # NEW in #336: enables wiki_source objects to be chunked
})
WIKI_PROPERTY_HEADING = {
    "wiki_facts": "Facts", "wiki_description": "Description",
    "wiki_definition": "Definition", "wiki_open_questions": "Open Questions",
    "wiki_dimensions": "Dimensions", "wiki_verdict": "Verdict",
    "wiki_question": "Question", "wiki_answer": "Answer",
    "wiki_excerpt": "Excerpt",  # NEW in #336
}


def extract_payload_metadata(obj: dict) -> dict:
    """Extract the optional per-object payload metadata from an Anytype object.

    One property parser shared by ``chunk_object`` (stamps the result on every
    chunk) and the ``indexer`` payload-only backfill (Aldeia-IT/aldeia-box#1413).

    Args:
        obj: Anytype object as returned by GET (``properties`` list of dicts).

    Returns:
        A dict holding only the keys that are present and non-empty:
        ``last_modified_date`` (str, the ``date`` of that property),
        ``source_type`` (the ``wiki_source_type`` select name),
        ``domain_tags`` (list of ``wiki_domain_tags`` multi_select names) and
        ``wiki_url`` (the ``wiki_url`` url property, passed through
        ``scrub_url_secrets``: userinfo and secret-looking query parameters
        removed, the rest of the link kept; non-string or empty values are
        dropped).
        Malformed properties are skipped, never raised on.
    """
    metadata: dict = {}
    seen_date = False
    for prop in obj.get("properties", []) or []:
        if not isinstance(prop, dict):
            continue
        k = prop.get("key")
        if k == "last_modified_date":
            # Same read shape as indexer._get_last_modified; the first one
            # wins, and a None date stamps nothing.
            if not seen_date:
                seen_date = True
                if prop.get("date") is not None:
                    metadata["last_modified_date"] = prop.get("date")
        elif k == "wiki_source_type":
            # select/multi_select hydrate with `name` inline on the GET
            # response — no id->name resolution at read time (#336).
            sel = prop.get("select")
            if isinstance(sel, dict) and sel.get("name") is not None:
                metadata["source_type"] = sel.get("name")
        elif k == "wiki_domain_tags":
            multi = prop.get("multi_select")
            if isinstance(multi, list):
                tags = [
                    t["name"] for t in multi
                    if isinstance(t, dict) and t.get("name")
                ]
                if tags:
                    metadata["domain_tags"] = tags
                else:
                    metadata.pop("domain_tags", None)
        elif k == "wiki_url":
            url = prop.get("url")
            if isinstance(url, str) and url.strip():
                metadata["wiki_url"] = scrub_url_secrets(url.strip())
    return metadata


def chunk_object(obj: dict) -> list[dict]:
    """Split an Anytype object into chunks with metadata.

    Each chunk gets: object_id, space_id, object_name, type_key, heading, text,
    plus the optional keys from ``extract_payload_metadata`` (last_modified_date,
    source_type, domain_tags, wiki_url) when the object carries them.

    When a markdown body is present it is the sole source of chunks. When the
    body is empty/absent, allowlisted wiki text properties are embedded instead
    (dedup guard: a body and its properties are never both emitted).
    """
    object_id = obj.get("id", "")
    space_id = obj.get("space_id", "")
    object_name = obj.get("name", "")
    type_key = obj.get("type", {}).get("key", "unknown")

    markdown = obj.get("markdown", "") or ""
    chunks = (
        _chunk_body(markdown, object_id, space_id, object_name, type_key)
        if markdown.strip()
        else _chunk_properties(obj, object_id, space_id, object_name, type_key)
    )

    # Optional payload metadata (date, source_type, domain_tags, wiki_url):
    # stamped on every chunk, each key omitted entirely when absent.
    metadata = extract_payload_metadata(obj)
    for chunk in chunks:
        chunk.update(metadata)

    return chunks


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
