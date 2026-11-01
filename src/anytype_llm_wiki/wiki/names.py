"""Name normalisation and title stripping, shared by the indexer and the wiki pipeline.

Kept apart from ``indexer`` (which loads the vector-store client) so
``wiki.util`` and the dry-run harness can strip title words without importing it
(Aldeia-IT/aldeia-box#1427 AC7, #1430). Behaviour is the indexer's D13 name tier:
the title list is ``config.NAME_TIER_TITLE_WORDS`` (built-in list when ``None``),
read at call time.
"""

import re

from .. import config
from ..textfold import fold

# D13 name tier: built-in leading title words (overridden by
# config.NAME_TIER_TITLE_WORDS), the non-alphanumeric runs norm() collapses and
# a trailing parenthetical context.
_BUILTIN_TITLE_WORDS = (
    "mestre", "mestra", "contramestre", "contramestra", "contra-mestre",
    "contra-mestra", "professor", "professora",
)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _norm(text: str) -> str:
    """Fold, collapse every run of non-``[a-z0-9]`` characters to one space, trim (D13)."""
    return _NON_ALNUM_RE.sub(" ", fold(text)).strip()


def _trailing_group_start(text: str) -> int | None:
    """Index of the ``(`` opening the balanced group ``text`` ends with, else ``None``.

    ``text`` must already be right-stripped. Nested groups belong to the outer one.
    """
    if not text.endswith(")"):
        return None
    depth = 0
    for i in range(len(text) - 1, -1, -1):
        if text[i] == ")":
            depth += 1
        elif text[i] == "(":
            depth -= 1
            if depth == 0:
                return i
    return None


def split_qualifier(name: str) -> tuple[str, str]:
    """Split a display name into its base and its trailing qualifier (Aldeia-IT/aldeia-box#1439).

    The qualifier is the last balanced parenthetical group at the end of the
    name, nested groups included: "Onça (São Paulo)" gives ``("Onça", "São
    Paulo")`` and "Filhos de Bimba (Bay Area (California))" gives ``("Filhos de
    Bimba", "Bay Area (California)")``. Both parts are stripped, the spelling is
    kept.

    Args:
        name: a display name; a non-string has no qualifier.

    Returns:
        ``(base, qualifier)``; ``(name, "")`` when the name does not end in a
        balanced group, or is only that group ("(São Paulo)").
    """
    if not isinstance(name, str):
        return name, ""
    text = name.rstrip()
    start = _trailing_group_start(text)
    if start is None or not text[:start].strip():
        return name, ""
    return text[:start].strip(), text[start + 1:-1].strip()


def _split_name(name: str) -> tuple[str, str]:
    """Return ``(base, paren)``: the normalised name without and the normalised trailing ``(...)``.

    The trailing group is the one ``split_qualifier`` takes, nested groups
    included. A name that is only a parenthetical keeps its whole normalised
    text as ``base``.
    """
    text = name.rstrip()
    start = _trailing_group_start(text)
    if start is None:
        return _norm(name), ""
    base = _norm(text[:start]) or _norm(name)
    return base, _norm(text[start + 1:-1])


def _title_words() -> tuple[str, ...]:
    """The normalised title words, longest first; read from config at call time (D13)."""
    configured = config.NAME_TIER_TITLE_WORDS
    words = _BUILTIN_TITLE_WORDS if configured is None else configured
    return tuple(sorted({w for w in map(_norm, words) if w}, key=len, reverse=True))


def _strip_title(normed: str, titles: tuple[str, ...]) -> str:
    """Remove one leading whole-word title; a text that is only a title stays as it is."""
    for title in titles:
        if normed.startswith(title + " "):
            return normed[len(title) + 1:]
    return normed


def strip_display_title(name: str) -> str:
    """Remove one leading title word from a display name, keeping the rest as written.

    The display counterpart of ``strip_name`` (same title list, ``_title_words()``,
    so ``config.NAME_TIER_TITLE_WORDS`` applies): "Mestre Bimba" gives "Bimba",
    "Contra-Mestre Fulano" gives "Fulano", "Mestre Zé do Lenço" gives "Zé do
    Lenço". A name that is only a title ("Mestre", "Mestre (Salvador)"), a name
    without a leading title and a non-string stay as they are.

    Args:
        name: an object name as extracted or given by a caller.

    Returns:
        The name without its leading title word; the input when nothing applies.
    """
    if not isinstance(name, str):
        return name
    base = _split_name(name)[0]
    title = next((t for t in _title_words() if base.startswith(t + " ")), None)
    if title is None:
        return name
    tokens = list(re.finditer(r"[^\W_]+", name))
    needed = len(title.split())
    if len(tokens) <= needed:
        return name
    rest = name[tokens[needed - 1].end():].lstrip(" \t-_.,:;")
    return rest if rest.strip() else name
