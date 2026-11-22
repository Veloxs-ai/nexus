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

"""Adobe glyph names to Unicode (common names, accented letters, ``uniXXXX`` / ``uXXXX``)."""

from __future__ import annotations

import re

_LETTERS = {c: c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"}


_NAMES = {
    "space": " ",
    "exclam": "!",
    "quotedbl": '"',
    "numbersign": "#",
    "dollar": "$",
    "percent": "%",
    "ampersand": "&",
    "quotesingle": "'",
    "quoteright": "’",
    "parenleft": "(",
    "parenright": ")",
    "asterisk": "*",
    "plus": "+",
    "comma": ",",
    "hyphen": "-",
    "minus": "−",
    "period": ".",
    "slash": "/",
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "colon": ":",
    "semicolon": ";",
    "less": "<",
    "equal": "=",
    "greater": ">",
    "question": "?",
    "at": "@",
    "bracketleft": "[",
    "backslash": "\\",
    "bracketright": "]",
    "asciicircum": "^",
    "underscore": "_",
    "grave": "`",
    "quoteleft": "‘",
    "braceleft": "{",
    "bar": "|",
    "braceright": "}",
    "asciitilde": "~",
    "bullet": "•",
    "endash": "–",
    "emdash": "—",
    "quotedblleft": "“",
    "quotedblright": "”",
    "quotesinglbase": "‚",
    "quotedblbase": "„",
    "ellipsis": "…",
    "dagger": "†",
    "daggerdbl": "‡",
    "fi": "fi",
    "fl": "fl",
    "ff": "ff",
    "ffi": "ffi",
    "ffl": "ffl",
    "trademark": "™",
    "copyright": "©",
    "registered": "®",
    "degree": "°",
    "section": "§",
    "paragraph": "¶",
    "periodcentered": "·",
    "multiply": "×",
    "divide": "÷",
    "plusminus": "±",
    "Euro": "€",
    "euro": "€",
    "sterling": "£",
    "yen": "¥",
    "cent": "¢",
    "currency": "¤",
    "nbspace": " ",
    "uni00A0": " ",
    "exclamdown": "¡",
    "questiondown": "¿",
    "guillemotleft": "«",
    "guillemotright": "»",
    "guilsinglleft": "‹",
    "guilsinglright": "›",
    "perthousand": "‰",
    "florin": "ƒ",
    "fraction": "⁄",
    "onehalf": "½",
    "onequarter": "¼",
    "threequarters": "¾",
    "twosuperior": "²",
    "threesuperior": "³",
    "onesuperior": "¹",
    "mu": "µ",
    "germandbls": "ß",
    "dotlessi": "ı",
    "circumflex": "ˆ",
    "tilde": "˜",
    "macron": "¯",
    "acute": "´",
    "dieresis": "¨",
    "cedilla": "¸",
    "ring": "˚",
    "caron": "ˇ",
    "breve": "˘",
    "dotaccent": "˙",
    "hungarumlaut": "˝",
    "ogonek": "˛",
    "logicalnot": "¬",
    "brokenbar": "¦",
    "ordfeminine": "ª",
    "ordmasculine": "º",
    "AE": "Æ",
    "ae": "æ",
    "OE": "Œ",
    "oe": "œ",
    "Oslash": "Ø",
    "oslash": "ø",
    "Lslash": "Ł",
    "lslash": "ł",
    "Thorn": "Þ",
    "thorn": "þ",
    "Eth": "Ð",
    "eth": "ð",
    "arrowright": "→",
    "arrowleft": "←",
    "checkmark": "✓",
    "summation": "∑",
    "infinity": "∞",
    "lessequal": "≤",
    "greaterequal": "≥",
    "notequal": "≠",
    "approxequal": "≈",
    "partialdiff": "∂",
    "radical": "√",
    "Delta": "Δ",
    "Omega": "Ω",
    "pi": "π",
    "alpha": "α",
    "beta": "β",
    "gamma": "γ",
    "delta": "δ",
    "lozenge": "◊",
    "tab": "\t",
}


# Accented Latin letters: base letter + accent name (Aacute, eacute, ccedilla, ...).
_ACCENTS = {
    "acute": "́",
    "grave": "̀",
    "circumflex": "̂",
    "dieresis": "̈",
    "tilde": "̃",
    "ring": "̊",
    "cedilla": "̧",
    "caron": "̌",
}


_UNI = re.compile(r"^uni([0-9A-Fa-f]{4,})$")


_U = re.compile(r"^u([0-9A-Fa-f]{4,6})$")


def glyph_to_unicode(name: str) -> str | None:
    """Unicode text of an Adobe glyph name (``None`` when unknown)."""
    base = name.split(".", 1)[0].split("_", 1)[0] if name not in _NAMES else name
    if base in _NAMES:
        return _NAMES[base]
    if base in _LETTERS:
        return base
    match = _UNI.match(base)
    if match:
        hexes = match.group(1)
        try:
            return "".join(
                chr(int(hexes[i : i + 4], 16)) for i in range(0, len(hexes) - len(hexes) % 4, 4)
            )
        except ValueError:
            return None
    match = _U.match(base)
    if match:
        try:
            return chr(int(match.group(1), 16))
        except ValueError:
            return None
    for accent, mark in _ACCENTS.items():
        if base.endswith(accent) and len(base) == len(accent) + 1 and base[0].isalpha():
            import unicodedata

            return unicodedata.normalize("NFC", base[0] + mark)
    return None
