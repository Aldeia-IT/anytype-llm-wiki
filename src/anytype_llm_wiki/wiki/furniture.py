"""Page furniture: text a web page carries around its content, not content itself.

A licence or copyright notice and a line that only states a date (a byline, an edit
stamp) are furniture. The fetch's recall step does not append such lines, and ingest
drops an extracted name that is furniture (Aldeia-IT/aldeia-box#1508). The rules are
generic: no site is named here (Aldeia-IT/aldeia-box#1427).

Pure functions on strings; no imports from the rest of the package, so ``fetch`` and
``extraction`` can both use them.
"""

import re

# Month names and common abbreviations in English, Portuguese and Spanish.
_MONTHS = frozenset(
    {
        "january", "february", "march", "april", "may", "june", "july", "august",
        "september", "october", "november", "december",
        "janeiro", "fevereiro", "março", "marco", "abril", "maio", "junho", "julho",
        "agosto", "setembro", "outubro", "novembro", "dezembro",
        "enero", "febrero", "marzo", "mayo", "junio", "julio", "septiembre", "setiembre",
        "octubre", "noviembre", "diciembre",
        "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
        "fev", "abr", "mai", "ago", "set", "out", "dez", "ene", "dic",
    }
)
# Words a written date joins its parts with ("1 de Janeiro de 2010", "26 of May").
_DATE_JOINERS = frozenset(("de", "del", "of", "em", "en", "on", "in", "the"))
# A day or a year, with an optional ordinal suffix ("26th", "1º").
_DATE_NUMBER_RE = re.compile(r"^\d{1,4}(?:st|nd|rd|th|º|ª|o|a)?$")
_NUMERIC_DATE_RE = re.compile(r"^\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}$")
# The longest date form kept in view: "the 1st of January of 2010" (6 words).
_DATE_MAX_TOKENS = 7

_LICENCE_NOTICE_RE = re.compile(
    r"creative\s+commons|\bcc[\s-]+by\b|all\s+rights\s+reserved"
    r"|todos\s+os\s+direitos\s+reservados|todos\s+los\s+derechos\s+reservados"
    r"|\blicensed\s+under\b|©|^\s*(?:\(c\)\s*\d{4}|copyright\b)",
    re.IGNORECASE,
)


def is_licence_notice(text: str) -> bool:
    """Tell whether ``text`` is a licence or copyright notice.

    A notice names Creative Commons or a CC BY licence, says "all rights reserved"
    (English, Portuguese or Spanish) or "licensed under", carries ``©``, or opens
    with "Copyright" or "(c) <year>". A licence named on its own ("MIT License") is
    not a notice, and a sentence that mentions copyright further in is not either.

    Args:
        text: a line of page text or an extracted name.

    Returns:
        ``True`` for a notice; ``False`` otherwise, including non-str input.
    """
    return isinstance(text, str) and bool(_LICENCE_NOTICE_RE.search(text))


def is_date_only(text: str) -> bool:
    """Tell whether ``text`` states a date and nothing else.

    Either a numeric date (``2016-10-01``, ``01/10/2016``), or at most seven words
    that are all month names, numbers (a day or year, ``26th`` and ``1º`` count) or
    joining words (``de``, ``of``, ...), with at least one month and one number:
    ``outubro, 2016``, ``1 de Janeiro, 2010``, ``26 August 1997``, ``May 1968``.
    A bare year (``1974``) and a lone month (``Maio``) are not dates here: a bare
    year line can be body text (Aldeia-IT/aldeia-box#1432 D11a), a month can be a name.

    Args:
        text: a line of page text or an extracted name.

    Returns:
        ``True`` for a date-only text; ``False`` otherwise, including non-str input.
    """
    if not isinstance(text, str):
        return False
    stripped = text.strip().strip(".,;:")
    if _NUMERIC_DATE_RE.match(stripped):
        return True
    tokens = re.findall(r"\w+", stripped.lower())
    if not tokens or len(tokens) > _DATE_MAX_TOKENS:
        return False
    has_month = any(token in _MONTHS for token in tokens)
    has_number = any(_DATE_NUMBER_RE.match(token) for token in tokens)
    return (
        has_month
        and has_number
        and all(
            token in _MONTHS or token in _DATE_JOINERS or _DATE_NUMBER_RE.match(token)
            for token in tokens
        )
    )
