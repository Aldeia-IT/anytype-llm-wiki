"""Typed, sourced links between wiki objects (Aldeia-IT/aldeia-box#1486).

A link is a ``wiki_link`` object: one directed edge ``from -> to`` with a short
free-text label and the Sources that state it. ``wiki_relations`` / ``wiki_related``
stay as the untyped, both-way index of related objects, written append-only
alongside each link. The caller holds the space lock; nothing here locks.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import httpx

from ..anytype_client import AnytypeReadClient
from .extraction import sanitize_name
from .util import (
    _existing_text,
    _rel_key,
    _relation_ids,
    normalize_title,
    strip_control_chars,
)
from .wiki_client import WikiClient

_IO_ERRORS = (httpx.HTTPError, KeyError, ValueError, TypeError)
_WS_RE = re.compile(r"\s+")
_EDGE_PUNCT = " .,;:!?\"'`()[]{}<>"

LINK_TYPE_KEY = "wiki_link"
DEFAULT_LABEL = "related"
LABEL_MAX_CHARS = 60
RELATION_SPECS_MAX = 200


@dataclass(frozen=True)
class LinkSpec:
    """One link to write; ``label`` is already normalised."""

    from_id: str
    to_id: str
    label: str


@dataclass(frozen=True)
class LinkRecord:
    """A stored ``wiki_link`` object, parsed."""

    id: str
    from_id: str
    to_id: str
    label: str
    source_ids: tuple[str, ...]


@dataclass
class LinkWriteResult:
    """Counts of one ``write_links`` call."""

    created: int = 0
    sourced: int = 0
    unchanged: int = 0
    skipped: int = 0
    failed: int = 0
    notes: list[str] = field(default_factory=list)


def normalize_label(raw: object) -> str:
    """Normalise a free relation label (lowercase, trimmed); never empty.

    A non-string, or a label that is empty or rejected by ``sanitize_name`` once
    cleaned, becomes ``DEFAULT_LABEL``. The result is stable under a second call.
    """
    if not isinstance(raw, str):
        return DEFAULT_LABEL
    text = unicodedata.normalize("NFKC", raw).replace("_", " ")
    text = _WS_RE.sub(" ", strip_control_chars(text)).strip().lower()
    text = text.replace("->", "-").replace("[", "(").replace("]", ")").replace(";", ",")
    text = text.strip(_EDGE_PUNCT)[:LABEL_MAX_CHARS]
    # Cutting can leave a space or punctuation at the end; strip so a second pass is a no-op.
    text = text.rstrip(_EDGE_PUNCT)
    if not text or sanitize_name(text) is None:
        return DEFAULT_LABEL
    return text


def link_object_name(from_id: str, to_id: str) -> str:
    """Name of a ``wiki_link`` object: ``link <from_id[-8:]>-<to_id[-8:]>``, no endpoint names.

    Holding no endpoint name or label keeps links out of every entity-name search.
    """
    return f"link {from_id[-8:]}-{to_id[-8:]}"


def union_ids(current: list[str], add: list[str]) -> list[str]:
    """Order-preserving union of two id lists."""
    return list(dict.fromkeys([*current, *add]))


def parse_link(obj: dict) -> LinkRecord | None:
    """Parse a ``wiki_link`` object; ``None`` when it is not one or is malformed.

    Malformed: ``properties`` is not a list, a side does not hold exactly one id, or
    the label is empty.
    """
    if not isinstance(obj, dict):
        return None
    obj_type = obj.get("type")
    if not isinstance(obj_type, dict) or obj_type.get("key") != LINK_TYPE_KEY:
        return None
    if not isinstance(obj.get("properties"), list) or not obj.get("id"):
        return None
    from_ids = _relation_ids(obj, "wiki_link_from")
    to_ids = _relation_ids(obj, "wiki_link_to")
    label = _existing_text(obj, "wiki_link_label")
    if len(from_ids) != 1 or len(to_ids) != 1 or not label:
        return None
    sources = tuple(union_ids(_relation_ids(obj, "wiki_link_sources"), []))
    return LinkRecord(obj["id"], from_ids[0], to_ids[0], label, sources)


def load_link_index(
    client: WikiClient, space_id: str
) -> dict[tuple[str, str, str], LinkRecord]:
    """All links of a space keyed by ``(from_id, label, to_id)``."""
    index: dict[tuple[str, str, str], LinkRecord] = {}
    for obj in client.list_objects(space_id):
        rec = parse_link(obj)
        if rec is not None:
            index.setdefault((rec.from_id, rec.label, rec.to_id), rec)
    return index


def relation_specs(
    extracted: dict, name_to_id: dict[str, str]
) -> tuple[list[LinkSpec], list[str]]:
    """Validate the model's ``relations``; returns ``(specs, warnings)``.

    Keeps dict items with string ``from``/``to``; endpoints resolve through
    ``name_to_id`` (an unresolved one warns ``relation_endpoint_unresolved: <name>``).
    Self-loops and duplicates drop; past ``RELATION_SPECS_MAX`` it warns
    ``relations_capped``.
    """
    relations = extracted.get("relations") if isinstance(extracted, dict) else None
    if not isinstance(relations, list):
        return [], []
    specs: list[LinkSpec] = []
    warnings: list[str] = []
    seen: set[tuple[str, str, str]] = set()

    def _resolve(name: str) -> str | None:
        clean = sanitize_name(name)
        found = name_to_id.get(normalize_title(clean)) if clean else None
        if found is None:
            warning = f"relation_endpoint_unresolved: {strip_control_chars(name).strip()[:100]}"
            if warning not in warnings:
                warnings.append(warning)
        return found

    for item in relations:
        if not isinstance(item, dict):
            continue
        raw_from, raw_to = item.get("from"), item.get("to")
        if not isinstance(raw_from, str) or not isinstance(raw_to, str):
            continue
        from_id, to_id = _resolve(raw_from), _resolve(raw_to)
        if from_id is None or to_id is None or from_id == to_id:
            continue
        key = (from_id, normalize_label(item.get("label")), to_id)
        if key in seen:
            continue
        if len(specs) >= RELATION_SPECS_MAX:
            if "relations_capped" not in warnings:
                warnings.append("relations_capped")
            continue
        seen.add(key)
        specs.append(LinkSpec(from_id=key[0], to_id=key[2], label=key[1]))
    return specs, warnings


def _link_properties(spec: LinkSpec, source_ids: list[str]) -> list[dict]:
    return [
        {"key": "wiki_link_from", "objects": [spec.from_id]},
        {"key": "wiki_link_to", "objects": [spec.to_id]},
        {"key": "wiki_link_label", "text": spec.label},
        {"key": "wiki_link_sources", "objects": source_ids},
    ]


def _write_index_sides(
    client: WikiClient,
    read_client: AnytypeReadClient,
    space_id: str,
    spec: LinkSpec,
    kind_by_id: dict[str, str],
    cache: dict[str, list[str]],
    result: LinkWriteResult,
) -> None:
    """Append each endpoint to the other's untyped index; undo side one if side two fails."""
    sides = [
        (spec.from_id, _rel_key(kind_by_id.get(spec.from_id, "entity")), spec.to_id),
        (spec.to_id, _rel_key(kind_by_id.get(spec.to_id, "entity")), spec.from_id),
    ]
    # Read both sides before writing either, so a failed read leaves the index untouched.
    for obj_id, rel_key, _other in sides:
        if obj_id in cache:
            continue
        try:
            cache[obj_id] = _relation_ids(read_client.get_object(space_id, obj_id), rel_key)
        except _IO_ERRORS as exc:
            result.failed += 1
            result.notes.append(f"relation_index_read_failed: {obj_id}: {exc}")
            return
    patched: tuple[str, str, list[str]] | None = None
    for obj_id, rel_key, other_id in sides:
        before = list(cache[obj_id])
        after = union_ids(before, [other_id])
        if after == before:
            continue
        try:
            client.update_object(
                space_id, obj_id, {"properties": [{"key": rel_key, "objects": after}]}
            )
        except _IO_ERRORS as exc:
            result.failed += 1
            if patched is None:
                result.notes.append(f"relation_index_write_failed: {obj_id}: {exc}")
                return
            first_id, first_key, first_before = patched
            try:
                client.update_object(
                    space_id, first_id, {"properties": [{"key": first_key, "objects": first_before}]}
                )
                cache[first_id] = first_before
                result.notes.append(
                    f"relation_rollback: reverted {first_id}.{first_key} after {obj_id} failed: {exc}"
                )
            except _IO_ERRORS as exc2:
                result.notes.append(
                    f"relation_rollback: could not revert {first_id}.{first_key}: {exc2}"
                )
            return
        cache[obj_id] = after
        if patched is None:
            patched = (obj_id, rel_key, before)


def write_links(
    client: WikiClient,
    read_client: AnytypeReadClient,
    space_id: str,
    specs: list[LinkSpec],
    *,
    source_id: str | None,
    kind_by_id: dict[str, str],
    link_index: dict[tuple[str, str, str], LinkRecord] | None = None,
    index_cache: dict[str, list[str]] | None = None,
) -> LinkWriteResult:
    """Create or source each link, then add both endpoints to the untyped index.

    Key ``(from_id, label, to_id)``; direction matters. No ``source_id`` writes
    nothing (``link_skipped_no_source``). Failures count ``failed`` with a note and
    never remove a created link; writing the link again repairs its index.
    ``link_index`` and ``index_cache`` are updated in place so a caller can share
    them across calls.
    """
    result = LinkWriteResult()
    if not specs:
        return result
    cache = index_cache if index_cache is not None else {}
    for spec in specs:
        if source_id is None:
            result.skipped += 1
            if "link_skipped_no_source" not in result.notes:
                result.notes.append("link_skipped_no_source")
            continue
        if spec.from_id == spec.to_id:
            result.skipped += 1
            continue
        if link_index is None:
            try:
                link_index = load_link_index(client, space_id)
            except _IO_ERRORS as exc:
                result.failed += 1
                result.notes.append(f"link_index_read_failed: {exc}")
                return result
        key = (spec.from_id, spec.label, spec.to_id)
        rec = link_index.get(key)
        if rec is None:
            try:
                created = client.create_object(
                    space_id,
                    type_key=LINK_TYPE_KEY,
                    name=link_object_name(spec.from_id, spec.to_id),
                    properties=_link_properties(spec, [source_id]),
                )
                link_index[key] = LinkRecord(
                    created["id"], spec.from_id, spec.to_id, spec.label, (source_id,)
                )
            except _IO_ERRORS as exc:
                result.failed += 1
                result.notes.append(
                    f"link_create_failed: {spec.from_id}->{spec.to_id}: {exc}"
                )
                continue
            result.created += 1
        elif source_id in rec.source_ids:
            result.unchanged += 1
        else:
            merged = union_ids(list(rec.source_ids), [source_id])
            try:
                client.update_object(
                    space_id,
                    rec.id,
                    {"properties": [{"key": "wiki_link_sources", "objects": merged}]},
                )
                link_index[key] = LinkRecord(
                    rec.id, rec.from_id, rec.to_id, rec.label, tuple(merged)
                )
                result.sourced += 1
            except _IO_ERRORS as exc:
                result.failed += 1
                result.notes.append(f"link_source_failed: {rec.id}: {exc}")
        _write_index_sides(client, read_client, space_id, spec, kind_by_id, cache, result)
    return result


def links_by_endpoint(objects: list[dict]) -> dict[str, list[LinkRecord]]:
    """Index parsed links by each endpoint id (for ``wiki_query``)."""
    by_endpoint: dict[str, list[LinkRecord]] = {}
    for obj in objects:
        rec = parse_link(obj)
        if rec is None:
            continue
        for endpoint in dict.fromkeys([rec.from_id, rec.to_id]):
            by_endpoint.setdefault(endpoint, []).append(rec)
    return by_endpoint
