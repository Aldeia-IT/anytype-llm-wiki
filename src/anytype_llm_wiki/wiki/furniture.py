"""Page furniture: text a web page carries around its content, not content itself.

A licence or copyright notice and a line that only states a date (a byline, an edit
stamp) are furniture. The fetch's recall step does not append such lines, and ingest
drops an extracted name that is furniture (Aldeia-IT/aldeia-box#1508). The rules are
generic: no site is named here (Aldeia-IT/aldeia-box#1427).

Pure functions on strings; no imports from the rest of the package, so ``fetch`` and
``extraction`` can both use them.
"""

import re

# Month names in English, Portuguese and Spanish, written out.
_MONTHS = frozenset(
    {
        "january", "february", "march", "april", "may", "june", "july", "august",
        "september", "october", "november", "december",
        "janeiro", "fevereiro", "março", "marco", "abril", "maio", "junho", "julho",
        "agosto", "setembro", "outubro", "novembro", "dezembro",
        "enero", "febrero", "marzo", "mayo", "junio", "julio", "septiembre", "setiembre",
        "octubre", "noviembre", "diciembre",
    }
)
# Common abbreviations. Several are everyday words too ("out", "set", "mar" in
# Portuguese), so an abbreviation counts as a month only next to a 4-digit year.
_MONTH_ABBREVIATIONS = frozenset(
    {
        "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
        "fev", "abr", "mai", "ago", "set", "out", "dez", "ene", "dic",
    }
)
# Words a written date joins its parts with ("1 de Janeiro de 2010", "26 of May").
_DATE_JOINERS = frozenset(("de", "del", "of", "em", "en", "on", "in", "the"))
# A day or a year, with an optional ordinal suffix ("26th", "1º").
_DATE_NUMBER_RE = re.compile(r"^\d{1,4}(?:st|nd|rd|th|º|ª|o|a)?$")
_YEAR_RE = re.compile(r"^\d{4}$")
# A numeric date has a 4-digit year at one end; a dot separates its parts only next
# to a 4-digit year, so a version number ("1.2.3", "2.0.10") is not a date.
_NUMERIC_DATE_RE = re.compile(
    r"^\d{4}([-/.])\d{1,2}\1\d{1,2}$|^\d{1,2}([-/.])\d{1,2}\2\d{4}$|^\d{1,2}([-/])\d{1,2}\3\d{2}$"
)
# The longest date form kept in view: "the 1st of January of 2010" (6 words).
_DATE_MAX_TOKENS = 7

# A notice is short: a licence footer runs to about 15-25 words. A longer line is
# body text even when it names a licence (Aldeia-IT/aldeia-box#1508 review F1).
_NOTICE_MAX_WORDS = 30
# A Creative Commons licence written as its code or spelled out with its version:
# "CC BY-SA 4.0", "Creative Commons Attribution-ShareAlike 4.0". The bare
# organisation name ("Creative Commons") is not a notice.
_CC_LICENCE = (
    r"\bcc[\s-]?by(?:-(?:sa|nc|nd))*(?:\s+\d\.\d)?\b"
    r"|\bcc0\b"
    r"|creative\s+commons\s+(?:attribution|atribui[çc][ãa]o|reconocimiento|zero)"
    r"[\w\s,-]{0,60}?\d\.\d"
)
_NOTICE_SHAPE_RE = re.compile(
    # Opens with the copyright sign, alone or after "Copyright": "© Grupo X", "©".
    r"^\s*(?:copyright\s*)?(?:©|\(c\))"
    # Opens with "Copyright", alone or with a year: "Copyright", "Copyright 2016 X".
    r"|^\s*copyright\s*(?:$|\d{4}\b)"
    # The sign with a year anywhere: "Grupo X © 2016".
    r"|(?:©|\(c\))\s*\d{4}\b"
    r"|all\s+rights\s+reserved|todos\s+os\s+direitos\s+reservados"
    r"|todos\s+los\s+derechos\s+reservados"
    # "licensed under" a named licence: "licensed under the MIT License".
    r"|\blicensed\s+under\s+(?:the\s+|an?\s+)?(?:"
    + _CC_LICENCE
    + r"|[\w .-]{0,60}?\b(?:license|licence|licença|licencia)\b)"
    r"|" + _CC_LICENCE,
    re.IGNORECASE,
)


def is_licence_notice(text: str) -> bool:
    """Tell whether ``text`` is a licence or copyright notice, by its shape.

    A notice is at most thirty words and either opens with ``©`` / ``(c)`` (alone
    or after "Copyright"), is "Copyright" alone or followed by a year, carries
    ``©`` before a year, says "all rights reserved" (English, Portuguese or
    Spanish), names a Creative Commons licence by its code or spelled out with
    its version (``CC BY-SA 4.0``, ``Creative Commons Attribution-ShareAlike
    4.0``), or says "licensed under" a named licence. Not notices: a licence or
    organisation named on its own (``MIT License``, ``Creative Commons``,
    ``Copyright Act``), and a body sentence that mentions ``©``, copyright or
    Creative Commons in passing (Aldeia-IT/aldeia-box#1508).

    Args:
        text: a line of page text or an extracted name.

    Returns:
        ``True`` for a notice; ``False`` otherwise, including non-str input.
    """
    if not isinstance(text, str) or len(text.split()) > _NOTICE_MAX_WORDS:
        return False
    return bool(_NOTICE_SHAPE_RE.search(text))


def is_date_only(text: str) -> bool:
    """Tell whether ``text`` states a date and nothing else.

    Either a numeric date (``2016-10-01``, ``01/10/2016``), or at most seven words
    that are all month names, numbers (a day or year, ``26th`` and ``1º`` count) or
    joining words (``de``, ``of``, ...), with at least one month and one number:
    ``outubro, 2016``, ``1 de Janeiro, 2010``, ``26 August 1997``, ``May 1968``.
    A month abbreviation counts only next to a 4-digit year (``out 2016``,
    ``3 mar 2010``): alone it can be a word ("Out 1", "Mar 3"). A numeric date
    has a 4-digit year (or a 2-digit year after ``-`` / ``/``), so a version
    number (``1.2.3``) is not one.
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
    has_year = any(_YEAR_RE.match(token) for token in tokens)
    months = _MONTHS | _MONTH_ABBREVIATIONS if has_year else _MONTHS
    has_month = any(token in months for token in tokens)
    has_number = any(_DATE_NUMBER_RE.match(token) for token in tokens)
    return (
        has_month
        and has_number
        and all(
            token in months or token in _DATE_JOINERS or _DATE_NUMBER_RE.match(token)
            for token in tokens
        )
    )
