"""Facts text kept as one section per source (Aldeia-IT/aldeia-box#1486).

STUB: signatures only, every body raises ``NotImplementedError``.
"""

from __future__ import annotations

from dataclasses import dataclass

SECTION_PREFIX = "## Source: "
LEGACY_LABEL = "unattributed (before per-source facts)"
SELF_CANDIDATE_MAX_SECTIONS = 8
SELF_CANDIDATE_MAX_CHARS = 6000


@dataclass(frozen=True)
class FactSection:
    """One source's section of a facts text."""

    label: str
    source_id: str | None
    lines: tuple[str, ...]


@dataclass(frozen=True)
class SectionMerge:
    """Result of ``append_source_section``."""

    text: str
    changed: bool
    new_units: tuple[str, ...]
    tagged: int
    earlier: tuple[FactSection, ...]


def fact_source_label(source: str) -> str:
    """Section label for a source reference or Source name, with secrets scrubbed."""
    raise NotImplementedError("not implemented")


def split_fact_units(facts: str) -> list[str]:
    """Split new facts into lossless units (lines, then sentences)."""
    raise NotImplementedError("not implemented")


def fact_key(unit: str) -> str:
    """Comparison key of a unit: case, spacing, tags and trailing cites ignored."""
    raise NotImplementedError("not implemented")


def parse_sections(text: str) -> list[FactSection]:
    """Parse a facts text; unsectioned text becomes one ``LEGACY_LABEL`` section."""
    raise NotImplementedError("not implemented")


def render_sections(sections: list[FactSection]) -> str:
    """Render sections back to the stored text."""
    raise NotImplementedError("not implemented")


def append_source_section(
    existing_text: str, label: str, source_id: str | None, new_facts: str
) -> SectionMerge:
    """Add ``new_facts`` as this source's section; tag duplicates; never drop a line."""
    raise NotImplementedError("not implemented")


def self_candidates(
    obj_id: str, name: str, earlier: tuple[FactSection, ...]
) -> list[dict]:
    """Contradiction-check candidates for an object's own earlier sections, capped."""
    raise NotImplementedError("not implemented")


def add_conflict_markers(
    text: str, label: str, source_id: str | None, conflicts: list[tuple[str, str]]
) -> str:
    """Add ``> [CONFLICT with <earlier label>: <reason>]`` lines under a section heading."""
    raise NotImplementedError("not implemented")


def add_also_tags(text: str, label: str, duplicates: list[tuple[int, str]]) -> str:
    """Tag the matching unit of each ``(section index, earlier text)`` with ``[also: <label>]``."""
    raise NotImplementedError("not implemented")


def no_lines_dropped(
    old_text: str, candidate_text: str, *, label: str, source_id: str | None
) -> bool:
    """True only if the candidate keeps every section, unit, tag and flag of ``old_text``."""
    raise NotImplementedError("not implemented")
