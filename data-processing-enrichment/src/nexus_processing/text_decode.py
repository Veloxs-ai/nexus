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

"""Bytes to text: encoding detection without third-party packages.

``decode_text`` turns raw file bytes into text the way an ingestion pipeline must:
never silently dropping characters. Order of evidence:

1. a byte-order mark (UTF-8, UTF-16 LE/BE, UTF-32 LE/BE);
2. UTF-16 without a BOM, recognised by NUL bytes in alternating positions;
3. strict UTF-8;
4. UTF-8 with a few broken bytes (a truncated or concatenated file): when valid multi-byte
   sequences outnumber the invalid bytes four to one, the text is UTF-8 and only the
   broken bytes become U+FFFD (counted in ``replaced``);
5. a legacy code page chosen by ``charset_detect.rank_encodings`` (Windows-1252 for
   Western text, which is what most non-UTF-8 office exports are, and Central European,
   Cyrillic, Greek, Turkish, Arabic, Hebrew, Baltic, KOI8-R, Shift-JIS, EUC-JP, GB18030,
   Big5 and EUC-KR when the bytes read as plausible text only in one of them);
6. latin-1, which maps every byte and so never fails (``confidence`` is low).

``looks_binary`` is the NUL sniff used to keep binary payloads out of text paths.
"""

from __future__ import annotations

import codecs
from dataclasses import dataclass

from .charset_detect import rank_encodings

__all__ = ["DecodedText", "decode_text", "looks_binary"]

_BOMS: tuple[tuple[bytes, str], ...] = (
    (codecs.BOM_UTF32_LE, "utf-32-le"),
    (codecs.BOM_UTF32_BE, "utf-32-be"),
    (codecs.BOM_UTF8, "utf-8"),
    (codecs.BOM_UTF16_LE, "utf-16-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be"),
)
_SNIFF = 8000


@dataclass(frozen=True)
class DecodedText:
    """Decoded text plus how it was decoded."""

    text: str
    encoding: str
    confidence: float
    bom: bool = False
    replaced: int = 0  # characters that could not be decoded and became U+FFFD


def looks_binary(data: bytes, sniff: int = _SNIFF) -> bool:
    """True when ``data`` is binary: a NUL byte in the first ``sniff`` bytes that is not
    explained by UTF-16/UTF-32 text."""
    head = bytes(data[:sniff])
    if b"\x00" not in head:
        return False
    if head.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return False
    return _utf16_order(head) is None


def _utf16_order(head: bytes) -> str | None:
    """'utf-16-le' / 'utf-16-be' when NULs sit in alternating positions (ASCII-heavy UTF-16)."""
    if len(head) < 4:
        return None
    even = head[0::2]
    odd = head[1::2]
    zeros_even = even.count(0) / len(even)
    zeros_odd = odd.count(0) / len(odd)
    if zeros_odd > 0.3 and zeros_even < 0.05:
        return "utf-16-le"
    if zeros_even > 0.3 and zeros_odd < 0.05:
        return "utf-16-be"
    return None


def _utf8_shape(text: str, raw: bytes) -> tuple[int, int]:
    """``(broken bytes, valid multi-byte characters)`` of a UTF-8 ``replace`` decode."""
    broken = text.count("\ufffd") - raw.count(b"\xef\xbf\xbd")  # real U+FFFD kept apart
    non_ascii = len(text) - len(text.encode("ascii", "ignore"))
    return broken, non_ascii - text.count("\ufffd")


def _mostly_utf8(raw: bytes) -> str | None:
    """UTF-8 text with a few undecodable bytes (``None`` when it is not UTF-8)."""
    head = raw[:65536]
    broken, multibyte = _utf8_shape(head.decode("utf-8", errors="replace"), head)
    if multibyte < 4 * broken and broken > 1:  # the start already reads as another encoding
        return None
    text = raw.decode("utf-8", errors="replace")
    broken, multibyte = _utf8_shape(text, raw)
    return text if broken > 0 and multibyte >= 8 and multibyte >= 4 * broken else None


def decode_text(data: bytes | bytearray | memoryview | str, strip_nul: bool = True) -> DecodedText:
    """Decode ``data`` to text; see the module docstring for the order of evidence.

    ``strip_nul`` removes NUL characters from the result (they cannot be stored in
    PostgreSQL text columns and carry no meaning in documents).
    """
    if isinstance(data, str):
        return DecodedText(data.replace("\x00", "") if strip_nul else data, "str", 1.0)
    raw = bytes(data)

    def done(text: str, encoding: str, confidence: float, bom: bool = False) -> DecodedText:
        replaced = text.count("�")
        if strip_nul:
            text = text.replace("\x00", "")
        return DecodedText(text, encoding, confidence, bom, replaced)

    for bom, encoding in _BOMS:
        if raw.startswith(bom):
            return done(raw[len(bom) :].decode(encoding, errors="replace"), encoding, 1.0, True)
    order = _utf16_order(raw[:_SNIFF])
    if order is not None:
        usable = raw[: len(raw) - (len(raw) % 2)]
        return done(usable.decode(order, errors="replace"), order, 0.9)
    try:
        return done(raw.decode("utf-8"), "utf-8", 0.95 if raw[:_SNIFF].isascii() else 1.0)
    except UnicodeDecodeError:
        pass
    mostly = _mostly_utf8(raw)
    if mostly is not None:
        return done(mostly, "utf-8", 0.8)
    for rank, encoding in enumerate(rank_encodings(raw)):
        try:
            text = raw.decode(encoding)  # the whole text must decode, not just the sample
        except UnicodeDecodeError:
            continue
        return done(text, encoding, 0.7 if rank == 0 else 0.5)
    return done(raw.decode("latin-1"), "latin-1", 0.4)
