"""wiki/pdf.py — text from PDF sources, read and extracted in page windows.

Aldeia-IT/aldeia-box#1483 (D3, D4). ``read_pdf`` takes the text layer of the
first ``WIKI_PDF_MAX_PAGES`` pages with pypdf (compressed streams included) and
keeps each page's number. There is no OCR: a PDF without a text layer is
refused by the usable-content gate in ``fetch.py``. ``extract_pages`` sends the
pages to ``extract()`` in windows that each fit the extraction input budget and
tags every extracted fact with the page(s) it came from.

PDF bytes are untrusted input. pypdf is pure Python and caps decompressed
stream sizes itself; any parser failure becomes a ``PdfUnreadable`` reason, never
a traceback in the ingest result.
"""

import io
import logging
import re
import time
import unicodedata
from collections.abc import Callable

from pypdf import PdfReader

from .extraction import source_budget_chars
from .util import normalize_title

_log = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"

# A page with fewer visible characters than this has no usable text layer
# (a scanned page, a figure, or only a page number).
_MIN_PAGE_CHARS = 20

# A page whose visible text is at least this share of unmapped glyphs (private-use,
# unassigned, control characters or U+FFFD) came out garbled: the font has no
# usable character map.
_GARBLED_SHARE = 0.1

_DEGRADED_PREFIX = "extraction_degraded: "

Page = tuple[int, str]


class PdfUnreadable(Exception):
    """The PDF cannot be read: ``str(exc)`` is the refusal reason."""


def is_pdf(data: bytes, content_type: str | None = None) -> bool:
    """Whether a body is a PDF, by its content type or its ``%PDF-`` magic bytes.

    A body served as HTML or text counts only when it starts with the magic, so
    a web page that merely quotes ``%PDF-`` stays a page. Any other type
    (``application/octet-stream``, none) counts when the magic is in the first
    kilobyte, where the PDF specification lets it sit.

    :param data: the body bytes (only the first kilobyte is inspected).
    :param content_type: the response's Content-Type, if any.
    :returns: True for a PDF.
    """
    ctype = (content_type or "").lower()
    if "pdf" in ctype:
        return True
    if "html" in ctype or ctype.startswith("text/"):
        return data.lstrip().startswith(PDF_MAGIC)
    return PDF_MAGIC in data[:1024]


def _clean_page_text(text: str) -> str:
    """Trim line ends, collapse runs of spaces and blank lines."""
    lines = [re.sub(r"[ \t ]+", " ", line).strip() for line in text.splitlines()]
    out = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return out.strip()


def _visible_len(text: str) -> int:
    return len(re.sub(r"\s", "", text))


def _garbled_share(text: str) -> float:
    visible = [ch for ch in text if not ch.isspace()]
    if not visible:
        return 0.0
    bad = sum(
        1
        for ch in visible
        if ch == "�" or unicodedata.category(ch) in ("Co", "Cn", "Cs", "Cc")
    )
    return bad / len(visible)


def page_label(numbers: list[int]) -> str:
    """Render page numbers for provenance: ``p. 3``, ``pp. 3–5`` or ``pp. 3, 5–6``.

    :param numbers: 1-based page numbers, in any order (duplicates are ignored).
    :returns: the label; an empty string for no pages.
    """
    nums = sorted(set(numbers))
    if not nums:
        return ""
    if len(nums) == 1:
        return f"p. {nums[0]}"
    runs: list[list[int]] = [[nums[0], nums[0]]]
    for n in nums[1:]:
        if n == runs[-1][1] + 1:
            runs[-1][1] = n
        else:
            runs.append([n, n])
    parts = [str(a) if a == b else f"{a}–{b}" for a, b in runs]
    return "pp. " + ", ".join(parts)


def read_pdf(data: bytes, max_pages: int, max_parse_s: float = 60.0) -> dict:
    """Read the text layer of the first ``max_pages`` pages of a PDF.

    The parse runs while the space lock is held, so it has a wall-clock budget:
    the clock is checked before each page, and once ``max_parse_s`` seconds have
    passed the remaining pages are not read. A single page that is slow to parse
    is not interrupted; the budget stops the next one.

    :param data: the whole PDF file.
    :param max_pages: how many pages to read (``WIKI_PDF_MAX_PAGES``).
    :param max_parse_s: wall-clock budget in seconds (``WIKI_PDF_MAX_PARSE_S``).
    :returns: ``{"pages", "total_pages", "pages_read", "no_text_pages",
        "warnings"}``. ``pages`` lists ``(page_number, text)`` for every read page
        that has a text layer (1-based numbers). ``warnings`` names a cut-off
        (``pdf_pages_capped``), a spent time budget (``pdf_parse_time_capped``),
        pages without a text layer
        (``pdf_pages_without_text``), pages pypdf could not read
        (``pdf_pages_unreadable``) and garbled text (``pdf_text_degraded``).
    :raises PdfUnreadable: the file is not a readable PDF (``pdf_unreadable: <cls>``)
        or is encrypted with a password (``pdf_encrypted``).
    """
    started = time.monotonic()
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                opened = reader.decrypt("")
            except Exception as exc:  # AES needs an extra we don't ship
                raise PdfUnreadable("pdf_encrypted") from exc
            if not opened:
                raise PdfUnreadable("pdf_encrypted")
        total = len(reader.pages)
    except PdfUnreadable:
        raise
    except Exception as exc:  # any parser failure on untrusted bytes
        raise PdfUnreadable(f"pdf_unreadable: {type(exc).__name__}") from exc

    page_cap = min(total, max_pages)
    pages_read = 0
    timed_out = False
    pages: list[Page] = []
    no_text: list[int] = []
    failed: list[int] = []
    garbled: list[int] = []
    for index in range(page_cap):
        if time.monotonic() - started >= max_parse_s:
            timed_out = True
            break
        pages_read += 1
        number = index + 1
        try:
            raw = reader.pages[index].extract_text() or ""
        except Exception as exc:  # noqa: BLE001 — one bad page must not lose the rest
            _log.warning("pdf page %d unreadable: %s", number, type(exc).__name__)
            failed.append(number)
            continue
        text = _clean_page_text(raw)
        if _visible_len(text) < _MIN_PAGE_CHARS:
            no_text.append(number)
            continue
        if _garbled_share(text) >= _GARBLED_SHARE:
            garbled.append(number)
        pages.append((number, text))

    warnings: list[str] = []
    if total > page_cap:
        warnings.append(
            f"pdf_pages_capped: read {page_cap} of {total} pages (WIKI_PDF_MAX_PAGES)"
        )
    if timed_out:
        warnings.append(
            f"pdf_parse_time_capped: read {pages_read} of {page_cap} pages in the "
            f"{max_parse_s:g} s budget (WIKI_PDF_MAX_PARSE_S)"
        )
    if failed:
        warnings.append(f"pdf_pages_unreadable: {page_label(failed)}")
    if no_text and pages:
        warnings.append(
            f"pdf_pages_without_text: {len(no_text)} of {pages_read} pages have no "
            f"text layer ({page_label(no_text)}); no OCR"
        )
    if garbled:
        warnings.append(f"pdf_text_degraded: unmapped glyphs on {page_label(garbled)}")
    return {
        "pages": pages,
        "total_pages": total,
        "pages_read": pages_read,
        "no_text_pages": no_text,
        "warnings": warnings,
    }


def pages_markdown(pages: list[Page]) -> str:
    """Join page texts with a ``[p. N]`` marker line before each page.

    The marker keeps page provenance in the stored excerpt. It is not a heading,
    so it never becomes a heading-derived candidate.
    """
    return "\n\n".join(f"[p. {number}]\n\n{text}" for number, text in pages)


def page_windows(pages: list[Page], budget_chars: int) -> list[list[Page]]:
    """Group consecutive pages into windows of at most ``budget_chars`` characters.

    A window's text is its pages joined by a blank line. A page larger than the
    budget on its own is a window by itself (``extract()`` then cuts it and
    reports ``truncated``).

    :param pages: ``(page_number, text)`` in reading order.
    :param budget_chars: the source budget of one ``extract()`` call.
    :returns: the windows, in order; empty for no pages.
    """
    windows: list[list[Page]] = []
    current: list[Page] = []
    size = 0
    for page in pages:
        added = len(page[1]) + (2 if current else 0)
        if current and size + added > budget_chars:
            windows.append(current)
            current, size = [], 0
            added = len(page[1])
        current.append(page)
        size += added
    if current:
        windows.append(current)
    return windows


def window_text(window: list[Page]) -> str:
    """The text one window sends to ``extract()``."""
    return "\n\n".join(text for _number, text in window)


def _mention_pages(name: str, window: list[Page]) -> list[int]:
    """Pages of ``window`` whose text names ``name`` (case- and space-insensitive)."""
    needle = " ".join(name.casefold().split())
    if not needle:
        return []
    return [
        number for number, text in window if needle in " ".join(text.casefold().split())
    ]


_FACT_FIELDS = {"entities": ("description", "definition"), "concepts": ("definition", "description")}


def extract_pdf_source(
    pages: list[Page],
    *,
    space_id: str,
    extract_fn: Callable[..., dict],
    subject_hint: str | None = None,
) -> dict:
    """Extract a PDF source in page windows sized to one ``extract()`` call.

    The one PDF branch that ``wiki_ingest`` and ``scripts/ingest_dry_run.py``
    share: ``extract_pages`` with windows of ``source_budget_chars(subject_hint)``
    characters, so a window is cut only when a single page is larger.

    :param pages: ``(page_number, text)`` from ``read_pdf``.
    :param space_id: passed through to ``extract_fn``.
    :param extract_fn: ``extraction.extract`` (injected so a caller's stub applies).
    :param subject_hint: passed through to ``extract_fn``; its prompt block counts
        against the window budget.
    :returns: ``extract_pages``'s merged result (``windows`` and ``warnings``
        included).
    """
    return extract_pages(
        pages,
        space_id=space_id,
        extract_fn=extract_fn,
        budget_chars=source_budget_chars(subject_hint),
        subject_hint=subject_hint,
    )


def extract_pages(
    pages: list[Page],
    *,
    space_id: str,
    extract_fn: Callable[..., dict],
    budget_chars: int,
    subject_hint: str | None = None,
) -> dict:
    """Run ``extract_fn`` over page windows and merge the results with page provenance.

    Each extracted fact ends with the page(s) it came from, e.g. ``[p. 12]``:
    the pages of its window that name the item, else the whole window. An item
    found in several windows keeps one entry whose facts are joined, each with
    its pages.

    :param pages: ``(page_number, text)`` from ``read_pdf``.
    :param space_id: passed through to ``extract_fn``.
    :param extract_fn: ``extraction.extract`` (injected so ingest's stub applies).
    :param budget_chars: the window size (``extraction.source_budget_chars``).
    :param subject_hint: passed through to ``extract_fn``.
    :returns: an ``extract()``-shaped dict (``entities``, ``concepts``,
        ``relations``, optional ``primary_subject``) plus ``windows`` (the count)
        and ``warnings``: ``extraction_input_truncated`` for a window that was cut,
        ``extraction_partial`` for each degraded window when others succeeded.
        When every window degraded, ``error`` is the first window's
        ``extraction_degraded: <reason>``. A ``[CONFIG ERROR]`` from any window is
        returned as is, at once.
    """
    windows = page_windows(pages, budget_chars)
    merged: dict = {
        "entities": [],
        "concepts": [],
        "relations": [],
        "windows": len(windows),
        "warnings": [],
    }
    seen: dict[tuple[str, str], dict] = {}
    degraded: list[tuple[list[int], str]] = []
    kwargs = {"subject_hint": subject_hint} if subject_hint else {}
    for window in windows:
        numbers = [number for number, _text in window]
        label = page_label(numbers)
        out = extract_fn(markdown=window_text(window), space_id=space_id, **kwargs)
        if not isinstance(out, dict):
            degraded.append((numbers, "malformed_json"))
            continue
        error = str(out.get("error") or "")
        if error.startswith("[CONFIG ERROR]"):
            return out
        truncated = out.get("truncated")
        if isinstance(truncated, dict):
            merged["warnings"].append(
                f"extraction_input_truncated: {label} "
                f"{truncated.get('kept_chars')}/{truncated.get('total_chars')} chars"
            )
        if error:
            degraded.append((numbers, error.removeprefix(_DEGRADED_PREFIX)))
            continue
        if out.get("primary_subject") and "primary_subject" not in merged:
            merged["primary_subject"] = out["primary_subject"]
        if isinstance(out.get("relations"), list):
            merged["relations"].extend(out["relations"])
        for key, (field, other) in _FACT_FIELDS.items():
            for item in out.get(key) or []:
                if not isinstance(item, dict) or not item.get("name"):
                    continue
                facts = str(item.get(field) or item.get(other) or "").strip()
                where = page_label(_mention_pages(str(item["name"]), window) or numbers)
                tagged = f"{facts} [{where}]" if facts else f"[{where}]"
                ident = (key, normalize_title(str(item["name"])))
                if ident in seen:
                    prior = seen[ident]
                    prior[field] = f"{prior[field]}\n{tagged}"
                    continue
                entry = dict(item)
                entry[field] = tagged
                entry.pop(other, None)
                seen[ident] = entry
                merged[key].append(entry)

    if degraded and len(degraded) == len(windows):
        merged["error"] = f"{_DEGRADED_PREFIX}{degraded[0][1]}"
        return merged
    for numbers, reason in degraded:
        merged["warnings"].append(
            f"extraction_partial: {page_label(numbers)} degraded ({reason})"
        )
    return merged
