# Copyright 2026 Veloxs AI Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import unicodedata

_ZERO_WIDTH_CODEPOINTS = {
    "​",  # zero-width space
    "‌",  # zero-width non-joiner
    "‍",  # zero-width joiner
    "⁠",  # word joiner
    "﻿",  # zero-width no-break space / BOM
}


class _FormatChars(dict):
    """``str.translate`` table: format/bidi characters (category Cf, which includes the
    zero-width characters) map to ``None``, every other character to itself. Filled per
    code point on first sight."""

    def __missing__(self, code: int) -> str | None:
        char = chr(code)
        value = None if is_invisible(char) else char
        self[code] = value
        return value


_FORMAT_CHARS = _FormatChars()


def normalize_text(text: str) -> str:
    """Apply NFKC normalization and strip zero-width / bidi control characters.

    Defends against common prompt-injection bypasses that rely on confusables,
    full-width lookalikes, or invisible characters inserted between letters.
    ASCII text is returned as is (NFKC does not change it and it has no format characters).
    """
    if not text or text.isascii():
        return text
    return unicodedata.normalize("NFKC", text).translate(_FORMAT_CHARS)


# Characters removed from STORED text: invisible and able to hide or reorder what a reader
# sees. ZWJ / ZWNJ (U+200D / U+200C) are kept: Indic scripts, Persian and emoji need them.
_INVISIBLE_STORED = {
    0x200B: None,  # zero-width space
    0x2060: None,  # word joiner
    0xFEFF: None,  # zero-width no-break space / BOM
    0x00AD: None,  # soft hyphen
    **{cp: None for cp in range(0x202A, 0x202F)},  # bidi embeddings and overrides
    **{cp: None for cp in range(0x2066, 0x206A)},  # bidi isolates
    0x200E: None,  # left-to-right mark
    0x200F: None,  # right-to-left mark
}


def strip_invisible(text: str) -> str:
    """Remove bidi controls and zero-width spaces from text that is stored or shown,
    keeping zero-width joiners (one ``str.translate`` pass)."""
    return text.translate(_INVISIBLE_STORED) if text and not text.isascii() else text


def is_invisible(char: str) -> bool:
    """True for characters the detectors ignore (zero-width and format/bidi controls)."""
    return char in _ZERO_WIDTH_CODEPOINTS or unicodedata.category(char) == "Cf"


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
