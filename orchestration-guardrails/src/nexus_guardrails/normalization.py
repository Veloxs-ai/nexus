from __future__ import annotations

import unicodedata

_ZERO_WIDTH_CODEPOINTS = {
    "​",  # zero-width space
    "‌",  # zero-width non-joiner
    "‍",  # zero-width joiner
    "⁠",  # word joiner
    "﻿",  # zero-width no-break space / BOM
}


def normalize_text(text: str) -> str:
    """Apply NFKC normalization and strip zero-width / bidi control characters.

    Defends against common prompt-injection bypasses that rely on confusables,
    full-width lookalikes, or invisible characters inserted between letters.
    """
    if not text:
        return text
    normalized = unicodedata.normalize("NFKC", text)
    cleaned_chars: list[str] = []
    for char in normalized:
        if char in _ZERO_WIDTH_CODEPOINTS:
            continue
        category = unicodedata.category(char)
        # Strip bidi/format control characters (Cf) that don't render visibly.
        if category == "Cf":
            continue
        cleaned_chars.append(char)
    return "".join(cleaned_chars)


def luhn_valid(digits: str) -> bool:
    """Verify a digit string passes the Luhn checksum."""
    stripped = [int(ch) for ch in digits if ch.isdigit()]
    if len(stripped) < 13:
        return False
    total = 0
    for index, digit in enumerate(reversed(stripped)):
        if index % 2 == 1:
            doubled = digit * 2
            total += doubled - 9 if doubled > 9 else doubled
        else:
            total += digit
    return total % 10 == 0
