"""Facts text kept as one section per source (Aldeia-IT/aldeia-box#1486).

A ``wiki_facts`` / ``wiki_definition`` value is a list of sections, one per Source::

    ## Source: <label> (id:<source_object_id>)
    <unit> <unit> [also: <label 2>; <label 3>] <unit>
    > [CONFLICT with <earlier label>: <reason>]

Everything here is a pure string function. The page text, the stored text and the
model's judgements are all untrusted, so every facts write goes through
``canonical_facts`` and the ``no_lines_dropped`` guard. A unit is a sentence or a line
of the page and is never reworded.
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlparse

from .extraction import sanitize_property_value
from .util import scrub_credentials, strip_control_chars

SECTION_PREFIX = "## Source: "
LEGACY_LABEL = "unattributed (before per-source facts)"
SELF_CANDIDATE_MAX_SECTIONS = 8
SELF_CANDIDATE_MAX_CHARS = 6000
LABEL_MAX_CHARS = 200
REASON_MAX_CHARS = 200

_HEADING_RE = re.compile(r"^## Source: (?P<label>.*?)(?: \(id:(?P<id>[^()\s]+)\))?$")
_LINE_BREAKS_RE = re.compile("\r\n|[\r\x85\u2028\u2029]")
_WS_RE = re.compile(r"\s+")
_HASH_RUN_RE = re.compile(r"#{2,}")
_SENTENCE_BREAK_RE = re.compile('(?<=[.!?])\\s+(?=[A-ZÀ-Ý0-9"“(\\[])')
_SENTENCE_START_RE = re.compile('[A-ZÀ-Ý0-9"\u201c(\\[]')
# A tag or a page locator written right after a unit belongs to that unit.
_TOKEN = r"\[(?:also|superseded):[^\]]*\]|\[pp?\.[^\]]*\]"
_TOKENS_RE = re.compile(rf"(?:{_TOKEN})(?:\s+(?:{_TOKEN}))*", re.IGNORECASE)
_ALSO_RE = re.compile(r"\[also:([^\]]*)\]", re.IGNORECASE)
_SUPERSEDED_RE = re.compile(r"\[superseded:([^\]]*)\]", re.IGNORECASE)
_TAGS_RE = re.compile(r"\[(?:also|superseded):[^\]]*\]", re.IGNORECASE)
_TRAILING_CITE_RE = re.compile(r"\s*\[pp?\. [^\]]*\]\s*$")
_DEFUSE_RE = re.compile(r"\[(?=(?:also:|superseded:|conflict))", re.IGNORECASE)
_LEADING_MARKUP_RE = re.compile(r"^[\s#>\-]+")
_PATH_SEGMENT_MIN = 20
# Any "scheme://" URL in prose, whatever the scheme or its case (postgres://u:pw@host/x).
_ANY_URL_RE = re.compile(r"""\b[A-Za-z][A-Za-z0-9+.-]*://[^\s)\]>"']+""")
_SELF_ID_RE = re.compile(r"#s(\d+)$")
_ELLIPSIS = "…"


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


# ---------------------------------------------------------------------------
# Sanitising
# ---------------------------------------------------------------------------


def _normalize_text(text: str) -> str:
    """Line breaks of every kind to ``\\n``; control and format (Cf) characters removed."""
    text = _LINE_BREAKS_RE.sub("\n", text)
    text = strip_control_chars(text)
    return "".join(c for c in text if unicodedata.category(c) != "Cf")


def _clean_single_line(text: str, max_chars: int) -> str:
    """A heading label or marker reason: one line, no brackets, no ``;``, no forged ``(id:``."""
    text = _WS_RE.sub(" ", _normalize_text(text)).strip()
    text = text.replace("[", "(").replace("]", ")").replace(";", ",")
    text = _HASH_RUN_RE.sub("#", text.replace("(id:", "(id :"))
    return text[:max_chars].strip()


def _clean_label(label: str) -> str:
    return _clean_single_line(label, LABEL_MAX_CHARS)


def _elide_url_path(url: str) -> str:
    """Replace each path segment of 20+ characters (an id, a key, a JWT) by an ellipsis."""
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    host, sep, path = rest.partition("/")
    segments = [_ELLIPSIS if len(seg) >= _PATH_SEGMENT_MIN else seg for seg in path.split("/")]
    return f"{scheme}://{host}{sep}{'/'.join(segments)}"


def _is_http_url(text: str) -> bool:
    """One whitespace-free token whose scheme is http or https, in any case."""
    if not re.fullmatch(r"\S+", text):
        return False
    try:
        return urlparse(text).scheme.lower() in ("http", "https")
    except ValueError:
        return False


def fact_source_label(source: str) -> str:
    """Section label for a source reference or Source name, with secrets scrubbed.

    A URL keeps scheme, host and path (credentials, query and fragment dropped; every
    path segment of 20+ characters elided; the scheme may be any case), a local path its basename, other text (a
    remember note) its words with embedded URLs of any scheme scrubbed the same way.
    """
    text = source if isinstance(source, str) else str(source)
    stripped = text.strip()
    if _is_http_url(stripped):
        text = _elide_url_path(scrub_credentials(stripped))
    elif stripped.startswith(("/", "~/", "./", "../")) and "\n" not in stripped:
        text = os.path.basename(stripped.rstrip("/")) or stripped
    else:
        text = _ANY_URL_RE.sub(lambda m: _elide_url_path(scrub_credentials(m.group(0))), text)
        text = sanitize_property_value(text)
    return _clean_label(text).lstrip("#").strip()


def _sanitize_new_text(text: str) -> str:
    """New page text: normalised, tag and heading look-alikes defused, markup stripped per line."""
    lines: list[str] = []
    for line in _normalize_text(text).split("\n"):
        line = _LEADING_MARKUP_RE.sub("", _DEFUSE_RE.sub("(", line))
        # Every run of '#' collapses to one, so no input (### Source:, ########) can leave
        # a "## Source: " behind; "(id:" is defused as in labels.
        lines.append(_HASH_RUN_RE.sub("#", line).replace("(id:", "(id :").strip())
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------


def _unit_spans(line: str) -> list[tuple[int, int]]:
    """``(start, end)`` of each unit of one line; tags and page locators stay with their unit."""
    pieces: list[tuple[int, int]] = []
    start = 0
    for match in _SENTENCE_BREAK_RE.finditer(line):
        # A full stop inside a bracket ("[p. 12]", "[also: a. B]") is not a sentence end.
        if line.rfind("[", 0, match.start()) > line.rfind("]", 0, match.start()):
            continue
        pieces.append((start, match.start()))
        start = match.end()
    pieces.append((start, len(line)))
    spans: list[list[int]] = []
    for first, last in pieces:
        first = max(first, spans[-1][1] if spans else 0)
        while first < last and line[first].isspace():
            first += 1
        if first >= last:
            continue
        tokens = _TOKENS_RE.match(line, first) if spans else None
        if tokens is None:
            spans.append([first, last])
            continue
        spans[-1][1] = tokens.end()
        rest = tokens.end()
        while rest < last and line[rest].isspace():
            rest += 1
        if rest >= last:
            continue
        if _SENTENCE_START_RE.match(line, rest):
            spans.append([rest, last])
        else:
            spans[-1][1] = last
    return [(a, b) for a, b in spans if line[a:b].strip()]


def _line_units(line: str) -> list[str]:
    return [line[a:b] for a, b in _unit_spans(line)]


def split_fact_units(facts: str) -> list[str]:
    """Split new facts into lossless units (lines, then sentences)."""
    return [unit for para in _paragraph_units(facts) for unit in para]


def _paragraph_units(facts: str) -> list[list[str]]:
    """Units of each non-empty input line of new (untrusted) text."""
    paragraphs = []
    for line in _sanitize_new_text(facts).split("\n"):
        units = _line_units(line)
        if units:
            paragraphs.append(units)
    return paragraphs


def fact_key(unit: str) -> str:
    """Comparison key of a unit: case, spacing, tags and trailing cites ignored."""
    text = _TAGS_RE.sub("", unicodedata.normalize("NFKC", unit)).rstrip()
    while True:
        shorter = _TRAILING_CITE_RE.sub("", text)
        if shorter == text:
            break
        text = shorter
    text = re.sub(r"^\s*-\s+", "", text).lower()
    return _WS_RE.sub(" ", text).strip().rstrip(".;,").strip()


def _tag_labels(unit: str, regex: re.Pattern[str]) -> list[str]:
    labels: list[str] = []
    for match in regex.finditer(unit):
        labels.extend(part.strip() for part in match.group(1).split(";") if part.strip())
    return labels


def _add_also_label(unit: str, label: str) -> str:
    """``unit`` with ``label`` in its ``[also: ...]`` tag (created after the unit if absent)."""
    existing = list(_ALSO_RE.finditer(unit))
    if existing:
        last = existing[-1]
        joined = "; ".join([*_tag_labels(last.group(0), _ALSO_RE), label])
        return f"{unit[: last.start()]}[also: {joined}]{unit[last.end():]}"
    return f"{unit.rstrip()} [also: {label}]"


def _without_label(unit: str, label: str) -> str:
    """``unit`` with ``label`` taken out of its ``[also:]``/``[superseded:]`` tags."""

    def _rewrite(name: str):
        def _sub(match: re.Match[str]) -> str:
            kept = [p for p in _tag_labels(match.group(0), _TAGS_RE_BY_NAME[name]) if p != label]
            return f"[{name}: {'; '.join(kept)}]" if kept else ""

        return _sub

    out = _ALSO_RE.sub(_rewrite("also"), unit)
    out = _SUPERSEDED_RE.sub(_rewrite("superseded"), out)
    return _WS_RE.sub(" ", out).strip() if out != unit else unit


_TAGS_RE_BY_NAME = {"also": _ALSO_RE, "superseded": _SUPERSEDED_RE}


# ---------------------------------------------------------------------------
# Parse and render
# ---------------------------------------------------------------------------


def parse_sections(
    text: str, *, known_ids: frozenset[str] | None = None
) -> list[FactSection]:
    """Parse a facts text; unsectioned text becomes one ``LEGACY_LABEL`` section.

    A section id not in ``known_ids`` is dropped (label-only); ``None`` keeps every id.
    A heading written in the middle of a line still starts a section, so a page cannot
    hide one.
    """
    if not isinstance(text, str) or not text.strip():
        return []
    flat = _normalize_text(text).replace(SECTION_PREFIX, "\n" + SECTION_PREFIX)
    sections: list[FactSection] = []
    label: str | None = None
    source_id: str | None = None
    lines: list[str] = []

    def _close() -> None:
        if label is not None:
            sections.append(FactSection(label, source_id, tuple(lines)))
        elif lines:
            sections.append(FactSection(LEGACY_LABEL, None, tuple(lines)))

    for raw in flat.split("\n"):
        line = raw.strip()
        if not line:
            continue
        match = _HEADING_RE.match(line) if line.startswith(SECTION_PREFIX) else None
        if match is None:
            lines.append(line)
            continue
        _close()
        found_id = match.group("id")
        if found_id is not None and known_ids is not None and found_id not in known_ids:
            found_id = None
        label, source_id, lines = _clean_label(match.group("label")) or "unlabelled", found_id, []
    _close()
    return sections


def _heading(section: FactSection) -> str:
    suffix = f" (id:{section.source_id})" if section.source_id else ""
    return f"{SECTION_PREFIX}{section.label}{suffix}"


def render_sections(sections: list[FactSection]) -> str:
    """Render sections back to the stored text."""
    out: list[str] = []
    for section in sections:
        out.append(_heading(section))
        out.extend(section.lines)
    return "\n".join(out)


def canonical_facts(text: str, known_ids: frozenset[str]) -> str:
    """The stored form of a facts text: ``render_sections(parse_sections(text, known_ids=...))``."""
    return render_sections(parse_sections(text, known_ids=known_ids))


# ---------------------------------------------------------------------------
# Merging a source
# ---------------------------------------------------------------------------


def _is_flag(line: str) -> bool:
    return line.startswith(">")


def _is_writer(section: FactSection, label: str, source_id: str | None) -> bool:
    """The section of this source: keyed by id, else the id-less one with this label."""
    if source_id is not None:
        return section.source_id == source_id
    return section.source_id is None and section.label == label


def _writer_index(sections: list[FactSection], label: str, source_id: str | None) -> int | None:
    for index, section in enumerate(sections):
        if _is_writer(section, label, source_id):
            return index
    return None


def _insert_before_flags(lines: list[str], new_lines: list[str]) -> list[str]:
    cut = len(lines)
    while cut > 0 and _is_flag(lines[cut - 1]):
        cut -= 1
    return [*lines[:cut], *new_lines, *lines[cut:]]


def append_source_section(
    existing_text: str, label: str, source_id: str | None, new_facts: str
) -> SectionMerge:
    """Add ``new_facts`` as this source's section; tag duplicates; never drop a line.

    A unit already in this source's section, or in any section with this label, is
    skipped; a unit already in another section gets ``label`` in its ``[also: ...]``
    tag; the rest are appended to this source's section (created last), one line per
    input paragraph. ``earlier`` lists the sections not carrying ``label`` (a section
    with this label is never offered as a contradiction candidate).
    """
    label = _clean_label(label) or "unlabelled"
    sections = parse_sections(existing_text, known_ids=None)
    earlier = tuple(s for s in sections if s.label != label)
    paragraphs = _paragraph_units(new_facts)
    if not paragraphs:
        return SectionMerge(existing_text, False, (), 0, earlier)

    own = _writer_index(sections, label, source_id)
    line_lists = [list(s.lines) for s in sections]
    seen = {
        fact_key(unit)
        for index, s in enumerate(sections)
        if index == own or s.label == label
        for line in s.lines
        if not _is_flag(line)
        for unit in _line_units(line)
    }
    new_lines: list[str] = []
    new_units: list[str] = []
    tagged = 0
    for units in paragraphs:
        fresh: list[str] = []
        for unit in units:
            key = fact_key(unit)
            if not key or key in seen:
                continue
            seen.add(key)
            target = _find_unit(sections, line_lists, key)
            if target is None:
                fresh.append(unit)
                continue
            sec_index, line_index, span = target
            line = line_lists[sec_index][line_index]
            if label in _tag_labels(line[span[0] : span[1]], _ALSO_RE):
                continue
            tagged_unit = _add_also_label(line[span[0] : span[1]], label)
            line_lists[sec_index][line_index] = line[: span[0]] + tagged_unit + line[span[1] :]
            tagged += 1
        if fresh:
            new_lines.append(" ".join(fresh))
            new_units.extend(fresh)

    if not new_units and not tagged:
        return SectionMerge(existing_text, False, (), 0, earlier)
    merged = [FactSection(s.label, s.source_id, tuple(lines)) for s, lines in zip(sections, line_lists)]
    if new_lines:
        if own is None:
            merged.append(FactSection(label, source_id, tuple(new_lines)))
        else:
            lines = _insert_before_flags(list(merged[own].lines), new_lines)
            merged[own] = FactSection(merged[own].label, merged[own].source_id, tuple(lines))
    return SectionMerge(render_sections(merged), True, tuple(new_units), tagged, earlier)


def _find_unit(
    sections: list[FactSection], line_lists: list[list[str]], key: str
) -> tuple[int, int, tuple[int, int]] | None:
    """Position of the first unit with ``key`` in any section's current lines."""
    for sec_index in range(len(sections)):
        for line_index, line in enumerate(line_lists[sec_index]):
            if _is_flag(line):
                continue
            for span in _unit_spans(line):
                if fact_key(line[span[0] : span[1]]) == key:
                    return sec_index, line_index, span
    return None


def self_candidates(
    obj_id: str, name: str, earlier: tuple[FactSection, ...]
) -> list[dict]:
    """Contradiction-check candidates for an object's own earlier sections, capped.

    Newest first, ``SELF_CANDIDATE_MAX_SECTIONS`` sections and
    ``SELF_CANDIDATE_MAX_CHARS`` characters at most; the oldest are dropped first. The
    id ``<obj_id>#s<n>`` carries the section's position in ``earlier``.
    """
    candidates: list[dict] = []
    used = 0
    for index in range(len(earlier) - 1, -1, -1):
        if len(candidates) >= SELF_CANDIDATE_MAX_SECTIONS:
            break
        section = earlier[index]
        facts = "\n".join(section.lines)
        if used + len(facts) > SELF_CANDIDATE_MAX_CHARS:
            if candidates:
                break
            facts = facts[:SELF_CANDIDATE_MAX_CHARS]
        used += len(facts)
        candidates.append(
            {
                "object_id": f"{obj_id}#s{index}",
                "name": f"{name} (earlier source: {section.label})",
                "facts": facts,
            }
        )
    return candidates


def filter_duplicates(
    items: object, self_ids: frozenset[str], new_units: tuple[str, ...]
) -> list[tuple[int, str]]:
    """Keep judged duplicates whose ``#s<n>`` id the check offered, one per new unit.

    Returns ``(section index, earlier unit)`` pairs for ``add_also_tags``. Mirrors
    ``_filter_contradictions``: nothing the model invented (an id it was not offered, a
    ``new`` text that is none of the new units) gets through.
    """
    if not isinstance(items, list):
        return []
    open_keys = [fact_key(unit) for unit in new_units]
    kept: list[tuple[int, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        object_id, earlier, new = item.get("object_id"), item.get("earlier"), item.get("new")
        if not (isinstance(object_id, str) and isinstance(earlier, str) and isinstance(new, str)):
            continue
        match = _SELF_ID_RE.search(object_id)
        if object_id not in self_ids or match is None:
            continue
        key = fact_key(new)
        if key not in open_keys:
            continue
        open_keys.remove(key)
        single = _WS_RE.sub(" ", _normalize_text(earlier)).strip()
        kept.append((int(match.group(1)), single[:SELF_CANDIDATE_MAX_CHARS]))
    return kept


# ---------------------------------------------------------------------------
# Markers and tags added after the merge
# ---------------------------------------------------------------------------


def add_conflict_markers(
    text: str, label: str, source_id: str | None, conflicts: list[tuple[str, str]]
) -> str:
    """Add ``> [CONFLICT with <earlier label>: <reason>]`` lines under a section heading.

    The lines go last in the writer's section. No such section, or nothing to add,
    leaves ``text`` unchanged.
    """
    sections = parse_sections(text, known_ids=None)
    index = _writer_index(sections, _clean_label(label), source_id)
    if index is None or not conflicts:
        return text
    lines = list(sections[index].lines)
    for earlier_label, reason in conflicts:
        marker = (
            f"> [CONFLICT with {_clean_label(str(earlier_label))}: "
            f"{_clean_single_line(str(reason), REASON_MAX_CHARS)}]"
        )
        if marker not in lines:
            lines.append(marker)
    if lines == list(sections[index].lines):
        return text
    sections[index] = FactSection(sections[index].label, sections[index].source_id, tuple(lines))
    return render_sections(sections)


def add_also_tags(text: str, label: str, duplicates: list[tuple[int, str]]) -> str:
    """Tag the matching unit of each ``(section index, earlier text)`` with ``[also: <label>]``.

    The index counts the sections that do not carry ``label``, as ``earlier`` of
    ``append_source_section`` does. No matching unit leaves that pair ignored.
    """
    label = _clean_label(label)
    sections = parse_sections(text, known_ids=None)
    positions = [i for i, s in enumerate(sections) if s.label != label]
    line_lists = {i: list(sections[i].lines) for i in positions}
    changed = False
    for number, earlier_text in duplicates:
        if not isinstance(number, int) or not 0 <= number < len(positions):
            continue
        lines = line_lists[positions[number]]
        key = fact_key(earlier_text)
        found = False
        for line_index, line in enumerate(lines):
            if _is_flag(line):
                continue
            for a, b in _unit_spans(line):
                if fact_key(line[a:b]) != key:
                    continue
                found = True
                if label not in _tag_labels(line[a:b], _ALSO_RE):
                    lines[line_index] = line[:a] + _add_also_label(line[a:b], label) + line[b:]
                    changed = True
                break
            if found:
                break
    if not changed:
        return text
    merged = [
        FactSection(s.label, s.source_id, tuple(line_lists.get(i, s.lines)))
        for i, s in enumerate(sections)
    ]
    return render_sections(merged)


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------


def _split_lines(section: FactSection) -> tuple[list[str], list[str]]:
    """``(units, flag lines)`` of a section."""
    units: list[str] = []
    flags: list[str] = []
    for line in section.lines:
        if _is_flag(line):
            flags.append(line)
        else:
            units.extend(_line_units(line))
    return units, flags


def no_lines_dropped(
    old_text: str,
    candidate_text: str,
    *,
    label: str,
    source_id: str | None,
    allowed_new_keys: frozenset[str],
    allowed_new_units: frozenset[str] | None = None,
) -> bool:
    """True only if the candidate keeps everything of ``old_text`` and adds only the writer's.

    Additions allowed: the writer's own section, units whose key is in
    ``allowed_new_keys``, and tags or flags carrying the writer's label. A new unit
    may carry no ``[also:]``/``[superseded:]`` tag except the writer's own label.
    With ``allowed_new_units`` (the input units, ``split_fact_units(new facts)``) a new
    unit must also equal one of them once the writer's tag is taken off, so a page
    citation the input did not carry is refused. The writer's new section must hold
    at least one unit. Both texts are read with every id kept, so call it on
    ``canonical_facts`` output.
    """
    label_ = _clean_label(label)
    exact = None if allowed_new_units is None else {_WS_RE.sub(" ", u).strip() for u in allowed_new_units}

    def _new_unit_ok(unit: str) -> bool:
        if fact_key(unit) not in allowed_new_keys:
            return False
        bare = _without_label(unit, label_)
        if _TAGS_RE.search(bare):
            return False
        return exact is None or _WS_RE.sub(" ", bare).strip() in exact

    label = _clean_label(label)
    old = parse_sections(old_text, known_ids=None)
    cand = parse_sections(candidate_text, known_ids=None)
    if len(cand) < len(old) or len(cand) > len(old) + 1:
        return False
    for before, after in zip(old, cand):
        if (before.label, before.source_id) != (after.label, after.source_id):
            return False
    extra = cand[len(old) :]
    if extra:
        new = extra[0]
        if (new.label, new.source_id) != (label, source_id) or not _is_writer(new, label, source_id):
            return False
        if _writer_index(old, label, source_id) is not None:
            return False
    for before, after in zip(old, cand):
        old_units, old_flags = _split_lines(before)
        new_units, new_flags = _split_lines(after)
        writer = _is_writer(before, label, source_id)
        if len(new_units) < len(old_units):
            return False
        for kept_old, kept_new in zip(old_units, new_units):
            if _without_label(kept_old, label) != _without_label(kept_new, label):
                return False
        appended = new_units[len(old_units) :]
        if appended and not (writer and all(_new_unit_ok(u) for u in appended)):
            return False
        remaining = list(new_flags)
        for flag in old_flags:
            if flag not in remaining:
                return False
            remaining.remove(flag)
        if remaining and not writer:
            return False
    if extra:
        units, _flags = _split_lines(extra[0])
        if not units or not all(_new_unit_ok(u) for u in units):
            return False
    return True
