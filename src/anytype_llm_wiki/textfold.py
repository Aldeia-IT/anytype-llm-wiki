"""Accent- and case-insensitive text folding shared by retrieval and config."""

import unicodedata


def fold(text: str) -> str:
    """Fold text for accent- and case-insensitive matching.

    NFKD-decomposes the text, drops the combining marks and casefolds the rest,
    so "Zulú" and "Zulu" fold to "zulu" and "Aberrê" to "aberre"
    (Aldeia-IT/aldeia-box#327 D12 step 1).

    Args:
        text: any string; ``None``-safe callers pass ``""``.

    Returns:
        The folded string. Characters outside Latin letters and digits are kept
        (callers tokenize or normalise afterwards).
    """
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()
