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

"""PDF object syntax (ISO 32000-1 §7.3): the lexer and object types shared by the reader,
the font decoder and the content-stream interpreter."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .pdf_filters import apply_filters, stream_filters

__all__ = [
    "DELIMITERS",
    "WHITESPACE",
    "PdfError",
    "PdfName",
    "PdfRef",
    "PdfStream",
    "decode_stream",
]

WHITESPACE = b" \t\r\n\x0c\x00"
DELIMITERS = b"()<>[]{}/%"


class PdfError(ValueError):
    """The file is not a PDF this reader can open."""


class PdfName(str):
    """A PDF name object (``/Type`` -> ``PdfName("Type")``)."""

    __slots__ = ()


@dataclass(frozen=True)
class PdfRef:
    num: int
    gen: int = 0


@dataclass
class PdfStream:
    dict: dict[str, Any]
    raw: bytes

    def get(self, key: str, default: Any = None) -> Any:
        return self.dict.get(key, default)


def decode_stream(stream: PdfStream, resolve: Any = None, stop_at_image: bool = True) -> bytes:
    """The stream's data with its filters applied (see pdf_filters.apply_filters)."""
    return apply_filters(stream.raw, stream_filters(stream.dict, resolve), stop_at_image)


class _Lexer:
    """Tokeniser/parser for PDF objects over a bytes buffer."""

    _NUMBER = re.compile(rb"[+-]?(?:\d+\.?\d*|\.\d+)")
    _REF = re.compile(rb"\s*(\d+)\s+(\d+)\s+R(?![A-Za-z0-9])")

    def __init__(self, data: bytes, pos: int = 0) -> None:
        self.data = data
        self.pos = pos

    def skip(self) -> None:
        data, n = self.data, len(self.data)
        while self.pos < n:
            c = data[self.pos]
            if c in WHITESPACE:
                self.pos += 1
            elif c == 0x25:  # % comment
                end = data.find(b"\n", self.pos)
                end2 = data.find(b"\r", self.pos)
                ends = [e for e in (end, end2) if e != -1]
                self.pos = min(ends) if ends else n
            else:
                break

    def parse(self, depth: int = 0) -> Any:
        if depth > 200:
            raise PdfError("object nesting too deep")
        self.skip()
        data = self.data
        if self.pos >= len(data):
            raise PdfError("unexpected end of data")
        c = data[self.pos : self.pos + 1]
        if c == b"/":
            return self._name()
        if c == b"(":
            return self._literal()
        if c == b"<":
            if data[self.pos : self.pos + 2] == b"<<":
                return self._dict(depth)
            return self._hex()
        if c == b"[":
            self.pos += 1
            items: list[Any] = []
            while True:
                self.skip()
                if self.pos >= len(data):
                    return items
                if data[self.pos : self.pos + 1] == b"]":
                    self.pos += 1
                    return items
                items.append(self.parse(depth + 1))
        if c in b"+-.0123456789":
            ref = self._REF.match(data, self.pos)
            if ref and c.isdigit():
                self.pos = ref.end()
                return PdfRef(int(ref.group(1)), int(ref.group(2)))
            match = self._NUMBER.match(data, self.pos)
            if not match:
                self.pos += 1
                return 0
            self.pos = match.end()
            token = match.group(0)
            try:
                return float(token) if b"." in token else int(token)
            except ValueError:
                return 0
        word = self._keyword()
        if word == b"true":
            return True
        if word == b"false":
            return False
        if word == b"null":
            return None
        if not word:
            self.pos += 1
            return None
        return word.decode("latin-1")  # operator or keyword (callers check)

    def _keyword(self) -> bytes:
        start = self.pos
        data, n = self.data, len(self.data)
        while (
            self.pos < n and data[self.pos] not in WHITESPACE and data[self.pos] not in DELIMITERS
        ):
            self.pos += 1
        return data[start : self.pos]

    def _name(self) -> PdfName:
        self.pos += 1
        raw = self._keyword()
        if b"#" in raw:
            raw = re.sub(rb"#([0-9A-Fa-f]{2})", lambda m: bytes([int(m.group(1), 16)]), raw)
        return PdfName(raw.decode("latin-1"))

    def _literal(self) -> bytes:
        data, n = self.data, len(self.data)
        self.pos += 1
        out = bytearray()
        depth = 1
        while self.pos < n:
            c = data[self.pos]
            self.pos += 1
            if c == 0x5C:  # backslash
                if self.pos >= n:
                    break
                e = data[self.pos]
                self.pos += 1
                if e in b"01234567":
                    digits = bytes([e])
                    while len(digits) < 3 and self.pos < n and data[self.pos] in b"01234567":
                        digits += data[self.pos : self.pos + 1]
                        self.pos += 1
                    out.append(int(digits, 8) & 0xFF)
                elif e == 0x0D:  # line continuation
                    if self.pos < n and data[self.pos] == 0x0A:
                        self.pos += 1
                elif e == 0x0A:
                    pass
                else:
                    out.append(
                        {0x6E: 0x0A, 0x72: 0x0D, 0x74: 0x09, 0x62: 0x08, 0x66: 0x0C}.get(e, e)
                    )
            elif c == 0x28:
                depth += 1
                out.append(c)
            elif c == 0x29:
                depth -= 1
                if depth == 0:
                    break
                out.append(c)
            else:
                out.append(c)
        return bytes(out)

    def _hex(self) -> bytes:
        end = self.data.find(b">", self.pos)
        end = len(self.data) if end == -1 else end
        digits = re.sub(rb"[^0-9A-Fa-f]", b"", self.data[self.pos + 1 : end])
        self.pos = end + 1
        if len(digits) % 2:
            digits += b"0"
        return bytes.fromhex(digits.decode("ascii"))

    def _dict(self, depth: int) -> dict[str, Any]:
        self.pos += 2
        out: dict[str, Any] = {}
        data = self.data
        while True:
            self.skip()
            if self.pos >= len(data):
                return out
            if data[self.pos : self.pos + 2] == b">>":
                self.pos += 2
                return out
            key = self.parse(depth + 1)
            if not isinstance(key, PdfName):
                continue
            out[str(key)] = self.parse(depth + 1)
