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

# The shape below must cover the whole text, so a title or a body sentence that only
# contains a notice is never one (Aldeia-IT/aldeia-box#1508). The word cap is a
# backstop: the shapes are short by construction.
_NOTICE_MAX_WORDS = 30
_SIGN = r"(?:©|\(c\))"
_YEAR = r"\d{4}(?:\s*[-–]\s*\d{4})?"
# Who holds the copyright: up to six words after the sign or year ("Grupo X",
# "Velhosmestres.com.").
_HOLDER = r"[^\s©]+(?:\s+[^\s©]+){0,5}"
_RESERVED = (
    r"(?:all\s+rights\s+reserved|todos\s+os\s+direitos\s+reservados"
    r"|todos\s+los\s+derechos\s+reservados)"
)
# A copyright line: "© 2026 Grupo X", "Copyright © X", "Copyright 2016 X",
# "Copyright", "X © 2016", each optionally closed by "All rights reserved".
# "Copyright" + a word that is not a year ("Copyright law") is not one.
_COPYRIGHT = (
    rf"(?:(?:copyright\s*)?{_SIGN}\s*(?:{_YEAR})?(?:[\s,.]*{_HOLDER})?"
    rf"|copyright(?:\s+{_YEAR}(?:[\s,.]+{_HOLDER})?)?"
    rf"|{_HOLDER}\s*{_SIGN}\s*{_YEAR})"
    rf"(?:[\s.,|–-]+{_RESERVED})?"
)
# A Creative Commons licence written as its code (a space may stand for the hyphen,
# as in markdown-stripped text) or spelled out with its version, with an optional
# tail and code in brackets: "CC BY-SA 4.0", "Creative Commons
# Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)". The bare organisation
# name ("Creative Commons") is not a licence.
_CC_CODE = r"(?:cc[\s-]?by(?:[\s-](?:sa|nc|nd))*(?:\s+\d\.\d)?|cc0)"
_CC_TAIL = (
    r"(?:\s+(?:international|internacional|unported|generic|brasil|brazil"
    r"|public\s+license|license|licence|licença|licencia|deed))*"
)
_CC_SPELLED = (
    r"creative\s+commons\s+(?:attribution|atribui[çc][ãa]o|reconocimiento|zero)"
    r"[\w\s,-]{0,60}?\d\.\d"
)
_CC_LICENCE = rf"(?:{_CC_SPELLED}|{_CC_CODE}){_CC_TAIL}(?:\s*\(\s*{_CC_CODE}{_CC_TAIL}\s*\))?"
_NAMED_LICENCE = rf"(?:{_CC_LICENCE}|[\w .-]{{0,60}}?\b(?:license|licence|licença|licencia))"
# What a licence statement is about: "This work", "Content on this site".
_LICENSED_SUBJECT = (
    r"(?:except\s+where\s+otherwise\s+noted,?\s+)?(?:all\s+)?(?:the\s+)?"
    r"(?:(?:content|contents|text|material)(?:\s+(?:on|of)\s+this\s+(?:site|website|page|wiki))?"
    r"|this\s+(?:work|page|site|website|article|text|content))"
)
# A licence statement: "Licensed under CC BY-SA 4.0", "This work is licensed under a
# Creative Commons Attribution 4.0 International License", "Content is available
# under ... unless otherwise noted".
_LICENSED = (
    rf"(?:{_LICENSED_SUBJECT}\s+)?(?:(?:is|are)\s+)?"
    r"(?:available|licensed|published|distributed|released)\s+under\s+"
    r"(?:the\s+terms\s+of\s+)?(?:the\s+|an?\s+)?"
    rf"{_NAMED_LICENCE}(?:[\s,]+(?:unless|except)\s+otherwise\s+(?:noted|stated|indicated))?"
)
_NOTICE_RE = re.compile(
    rf"{_COPYRIGHT}|{_RESERVED}|{_LICENSED}|{_CC_LICENCE}", re.IGNORECASE
)


def is_licence_notice(text: str) -> bool:
    """Tell whether ``text`` is, as a whole, a licence or copyright notice.

    The notice must cover the whole text (edge whitespace and punctuation
    aside), which is at most thirty words. Notices: a copyright line that opens
    with ``©`` / ``(c)`` or "Copyright" (alone or with a year) or ends with ``©``
    and a year, with only a year and a holder of up to six words besides
    (``© 2026 Grupo X``, ``Copyright 2016 Velhosmestres``), optionally closed by
    "All rights reserved"; "All rights reserved" alone (English, Portuguese or
    Spanish); a Creative Commons licence by its code or spelled out with its
    version (``CC BY-SA 4.0``, ``Creative Commons Attribution-ShareAlike 4.0
    International (CC BY-SA 4.0)``); a licence statement ("Licensed under CC
    BY-SA 4.0", "Content is available under ... unless otherwise noted").

    Not notices: a licence or organisation named on its own (``MIT License``,
    ``Creative Commons``, ``Copyright Act``), and any text that only contains a
    notice: a title ("History of CC BY-SA 4.0 adoption") or a body sentence that
    mentions a licence or ``©`` mid-sentence (Aldeia-IT/aldeia-box#1508).

    Args:
        text: a line of page text or an extracted name.

    Returns:
        ``True`` for a notice; ``False`` otherwise, including non-str input.
    """
    if not isinstance(text, str):
        return False
    stripped = text.strip().strip(".,;:|").strip()
    if not stripped or len(stripped.split()) > _NOTICE_MAX_WORDS:
        return False
    return bool(_NOTICE_RE.fullmatch(stripped))


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
