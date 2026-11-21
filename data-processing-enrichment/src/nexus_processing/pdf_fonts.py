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

"""PDF fonts: character codes to Unicode text and advance widths.

- ``/ToUnicode`` CMaps (``bfchar``, ``bfrange`` with offsets or arrays, code space
  ranges for multi-byte codes) are used first: they are how Type0/CID fonts (most
  modern PDFs) say what their glyphs mean.
- Simple fonts fall back to their ``/Encoding`` (WinAnsi, MacRoman, Standard) plus
  ``/Differences`` glyph names, resolved through a table of common Adobe glyph names and
  the ``uniXXXX`` / ``uXXXX`` conventions.
- Widths come from ``/Widths`` + ``/FirstChar`` (simple fonts) or ``/W`` + ``/DW``
  (CID fonts), scaled by ``/FontMatrix`` for Type3 fonts.
"""

from __future__ import annotations

import re
from typing import Any

from .pdf_lexer import PdfStream, _Lexer, decode_stream

__all__ = ["PdfFont", "glyph_to_unicode", "parse_cmap"]

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


def _standard_char(code: int) -> str:
    if code == 0x27:
        return "’"
    if code == 0x60:
        return "‘"
    return chr(code) if 0x20 <= code < 0x7F else ""


def _base_encoding(name: str) -> list[str]:
    if name == "WinAnsiEncoding":
        table = []
        for code in range(256):
            try:
                table.append(bytes([code]).decode("cp1252"))
            except UnicodeDecodeError:
                table.append("")
        return table
    if name == "MacRomanEncoding":
        return [bytes([c]).decode("mac_roman") if c >= 0x20 else "" for c in range(256)]
    if name == "PDFDocEncoding":
        return [bytes([c]).decode("latin-1") for c in range(256)]
    return [_standard_char(c) for c in range(256)]  # StandardEncoding (and unknown)


def _utf16(data: bytes) -> str:
    if len(data) % 2:
        data = data + b"\0"
    try:
        return data.decode("utf-16-be")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def parse_cmap(data: bytes) -> tuple[dict[int, str], list[tuple[int, int, int]]]:
    """``({code: text}, [(byte length, low, high) code space ranges])`` of a ToUnicode CMap."""
    mapping: dict[int, str] = {}
    spaces: list[tuple[int, int, int]] = []
    lexer = _Lexer(data)
    tokens: list[Any] = []
    while True:
        try:
            lexer.skip()
            if lexer.pos >= len(data):
                break
            tok = lexer.parse()
        except Exception:
            break
        if tok == "endcodespacerange":
            for low, high in zip(tokens[0::2], tokens[1::2], strict=False):
                if isinstance(low, bytes) and isinstance(high, bytes) and low:
                    spaces.append(
                        (len(low), int.from_bytes(low, "big"), int.from_bytes(high, "big"))
                    )
            tokens = []
        elif tok == "endbfchar":
            for src, dst in zip(tokens[0::2], tokens[1::2], strict=False):
                if isinstance(src, bytes) and isinstance(dst, bytes):
                    mapping[int.from_bytes(src, "big")] = _utf16(dst)
            tokens = []
        elif tok == "endbfrange":
            for i in range(0, len(tokens) - 2, 3):
                low, high, dst = tokens[i], tokens[i + 1], tokens[i + 2]
                if not (isinstance(low, bytes) and isinstance(high, bytes)):
                    continue
                lo, hi = int.from_bytes(low, "big"), int.from_bytes(high, "big")
                if hi - lo > 65536:
                    continue
                if isinstance(dst, list):
                    for k, item in enumerate(dst[: hi - lo + 1]):
                        if isinstance(item, bytes):
                            mapping[lo + k] = _utf16(item)
                elif isinstance(dst, bytes) and dst:
                    base = int.from_bytes(dst, "big")
                    for k in range(hi - lo + 1):
                        mapping[lo + k] = _utf16((base + k).to_bytes(len(dst), "big"))
            tokens = []
        elif tok in ("begincodespacerange", "beginbfchar", "beginbfrange"):
            tokens = []
        elif isinstance(tok, (bytes, list)):
            tokens.append(tok)
        elif isinstance(tok, str):
            tokens = [] if tok.startswith("begin") else tokens
    return mapping, spaces


class PdfFont:
    """One font resource: ``decode(bytes)`` yields ``(text, width_in_text_space, is_space)``."""

    def __init__(self, font: dict[str, Any], resolve: Any, fallback: bool = False) -> None:
        """``fallback``: a font the page names but does not define; its strings are read as
        UTF-8 (else Latin-1) with a nominal width."""
        self.fallback = fallback
        self.resolve = resolve
        self.subtype = str(resolve(font.get("Subtype")) or "Type1")
        self.name = str(resolve(font.get("BaseFont")) or "")
        self.composite = self.subtype == "Type0"
        matrix = resolve(font.get("FontMatrix"))
        self.scale = (
            float(matrix[0])
            if self.subtype == "Type3" and isinstance(matrix, list) and matrix
            else 0.001
        )
        self.to_unicode: dict[int, str] = {}
        self.spaces: list[tuple[int, int, int]] = []
        tounicode = resolve(font.get("ToUnicode"))
        if isinstance(tounicode, PdfStream):
            try:
                self.to_unicode, self.spaces = parse_cmap(decode_stream(tounicode, resolve))
            except Exception:
                self.to_unicode, self.spaces = {}, []
        self.encoding = self._simple_encoding(font) if not self.composite else []
        self.widths: dict[int, float] = {}
        self.default_width = 1000.0 if self.composite else 500.0
        if self.composite:
            self._cid_widths(font)
        else:
            self._simple_widths(font)
        if self.composite and not self.spaces:
            self.spaces = [(2, 0, 0xFFFF)]

    def _simple_encoding(self, font: dict[str, Any]) -> list[str]:
        enc = self.resolve(font.get("Encoding"))
        base_name = "StandardEncoding"
        diffs: list[Any] = []
        if isinstance(enc, str):
            base_name = enc
        elif isinstance(enc, dict):
            base_name = str(self.resolve(enc.get("BaseEncoding")) or "StandardEncoding")
            diffs = self.resolve(enc.get("Differences")) or []
        if (
            self.subtype == "TrueType"
            and base_name == "StandardEncoding"
            and not isinstance(enc, (str, dict))
        ):
            base_name = "WinAnsiEncoding"
        table = _base_encoding(base_name)
        code = 0
        for item in diffs:
            item = self.resolve(item)
            if isinstance(item, int):
                code = item
            elif isinstance(item, str) and 0 <= code < 256:
                text = glyph_to_unicode(str(item))
                if text is not None:
                    table[code] = text
                code += 1
        return table

    def _simple_widths(self, font: dict[str, Any]) -> None:
        first = int(self.resolve(font.get("FirstChar")) or 0)
        widths = self.resolve(font.get("Widths")) or []
        for i, w in enumerate(widths):
            w = self.resolve(w)
            if isinstance(w, int | float):
                self.widths[first + i] = float(w)
        desc = self.resolve(font.get("FontDescriptor"))
        if isinstance(desc, dict):
            missing = self.resolve(desc.get("MissingWidth"))
            if isinstance(missing, int | float) and missing:
                self.default_width = float(missing)
        if "Courier" in self.name:
            self.default_width = 600.0

    def _cid_widths(self, font: dict[str, Any]) -> None:
        descendants = self.resolve(font.get("DescendantFonts")) or []
        desc = self.resolve(descendants[0]) if descendants else None
        if not isinstance(desc, dict):
            return
        dw = self.resolve(desc.get("DW"))
        if isinstance(dw, int | float):
            self.default_width = float(dw)
        w = self.resolve(desc.get("W")) or []
        i = 0
        while i < len(w):
            first = self.resolve(w[i])
            nxt = self.resolve(w[i + 1]) if i + 1 < len(w) else None
            if isinstance(nxt, list):
                for k, width in enumerate(nxt):
                    width = self.resolve(width)
                    if isinstance(first, int) and isinstance(width, int | float):
                        self.widths[first + k] = float(width)
                i += 2
            else:
                last = nxt
                width = self.resolve(w[i + 2]) if i + 2 < len(w) else None
                if (
                    isinstance(first, int)
                    and isinstance(last, int)
                    and isinstance(width, int | float)
                ):
                    for cid in range(first, min(last, first + 65536) + 1):
                        self.widths[cid] = float(width)
                i += 3

    def _codes(self, data: bytes) -> list[tuple[int, int]]:
        """``[(code, byte length)]`` of a string shown with this font."""
        if not self.composite and (not self.spaces or all(n == 1 for n, _, _ in self.spaces)):
            return [(b, 1) for b in data]
        out = []
        i = 0
        lengths = sorted({n for n, _, _ in self.spaces}) or [2]
        while i < len(data):
            for n in lengths:
                if i + n > len(data):
                    continue
                code = int.from_bytes(data[i : i + n], "big")
                if any(length == n and lo <= code <= hi for length, lo, hi in self.spaces):
                    out.append((code, n))
                    i += n
                    break
            else:
                n = lengths[-1] if i + lengths[-1] <= len(data) else 1
                out.append((int.from_bytes(data[i : i + n], "big"), n))
                i += n
        return out

    def decode(self, data: bytes) -> list[tuple[str, float, bool]]:
        if self.fallback:
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                text = data.decode("latin-1")
            return [(ch, self.default_width * self.scale, ch == " ") for ch in text]
        out: list[tuple[str, float, bool]] = []
        for code, length in self._codes(data):
            if code in self.to_unicode:
                text = self.to_unicode[code]
            elif self.composite:
                text = ""  # a CID with no ToUnicode entry: the glyph has no known meaning
            else:
                text = self.encoding[code] if code < len(self.encoding) else ""
            width = self.widths.get(code, self.default_width) * self.scale
            out.append((text, width, length == 1 and code == 32))
        return out
