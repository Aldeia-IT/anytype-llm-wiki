"""Typed, sourced links between wiki objects (Aldeia-IT/aldeia-box#1486).

STUB: signatures only, every body raises ``NotImplementedError``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .wiki_client import WikiClient
from ..anytype_client import AnytypeReadClient

LINK_TYPE_KEY = "wiki_link"
DEFAULT_LABEL = "related"
LABEL_MAX_CHARS = 60


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
    notes: list[str] = field(default_factory=list)


def normalize_label(raw: object) -> str:
    """Normalise a free relation label (lowercase, trimmed); never empty."""
    raise NotImplementedError("not implemented")


def link_object_name(from_name: str, label: str, to_name: str) -> str:
    """Name of a ``wiki_link`` object: ``<from> -[<label>]-> <to>``, at most 200 chars."""
    raise NotImplementedError("not implemented")


def union_ids(current: list[str], add: list[str]) -> list[str]:
    """Order-preserving union of two id lists."""
    raise NotImplementedError("not implemented")


def parse_link(obj: dict) -> LinkRecord | None:
    """Parse a ``wiki_link`` object; ``None`` when it is not one or is malformed."""
    raise NotImplementedError("not implemented")


def load_link_index(
    client: WikiClient, space_id: str
) -> dict[tuple[str, str, str], LinkRecord]:
    """All links of a space keyed by ``(from_id, label, to_id)``."""
    raise NotImplementedError("not implemented")


def relation_specs(
    extracted: dict,
    name_to_id: dict[str, str],
    *,
    strip_name=None,
) -> tuple[list[LinkSpec], list[str]]:
    """Validate the model's ``relations``; returns ``(specs, warnings)``."""
    raise NotImplementedError("not implemented")


def write_links(
    client: WikiClient,
    read_client: AnytypeReadClient,
    space_id: str,
    specs: list[LinkSpec],
    *,
    source_id: str | None,
    kind_by_id: dict[str, str],
    names_by_id: dict[str, str],
    link_index: dict[tuple[str, str, str], LinkRecord] | None = None,
) -> LinkWriteResult:
    """Create or source each link, then add both endpoints to the untyped index."""
    raise NotImplementedError("not implemented")


def links_by_endpoint(objects: list[dict]) -> dict[str, list[LinkRecord]]:
    """Index parsed links by each endpoint id (for ``wiki_query``)."""
    raise NotImplementedError("not implemented")
