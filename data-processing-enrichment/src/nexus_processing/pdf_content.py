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

"""PDF content streams: positioned text runs and the images a page draws.

A small interpreter of the page description operators that matter for text
(ISO 32000-1 §8-9): graphics state (``q``/``Q``/``cm``), text objects and state
(``BT``/``ET``, ``Tf``, ``Tc``, ``Tw``, ``Tz``, ``TL``, ``Ts``, ``Td``/``TD``/``Tm``/``T*``),
text showing (``Tj``, ``TJ`` with kerning, ``'``, ``"``) and ``Do`` for Form XObjects
(recursively) and images. Inline images (``BI``...``ID``...``EI``) are skipped.

``page_content`` returns the page's text runs, each with its baseline position, size
and extent in page space, in content-stream order (which is the reading order the
producer wrote), plus the images drawn with their area on the page.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .pdf_fonts import PdfFont
from .pdf_lexer import PdfRef, PdfStream, _Lexer, decode_stream
from .pdf_reader import PdfDocument

__all__ = ["PageContent", "PdfImage", "TextRun", "page_content"]

MAX_FORM_DEPTH = 8
MAX_OPERATIONS = 2_000_000  # per page, guards pathological streams


@dataclass
class TextRun:
    text: str
    x: float  # start of the baseline, page space
    y: float
    end_x: float  # end of the run (x after the last glyph advance)
    size: float  # effective font size in page space
    font: str = ""


@dataclass
class PdfImage:
    stream: PdfStream
    area: float  # page-space area the image covers
    ref: int | None = None


@dataclass
class PageContent:
    runs: list[TextRun] = field(default_factory=list)
    images: list[PdfImage] = field(default_factory=list)
    width: float = 612.0
    height: float = 792.0


Matrix = tuple[float, float, float, float, float, float]
IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _mul(m: Matrix, n: Matrix) -> Matrix:
    a, b, c, d, e, f = m
    a2, b2, c2, d2, e2, f2 = n
    return (
        a * a2 + b * c2,
        a * b2 + b * d2,
        c * a2 + d * c2,
        c * b2 + d * d2,
        e * a2 + f * c2 + e2,
        e * b2 + f * d2 + f2,
    )


def _num(value: Any, default: float = 0.0) -> float:
    return (
        float(value) if isinstance(value, int | float) and not isinstance(value, bool) else default
    )


def _matrix(values: list[Any]) -> Matrix:
    nums = [_num(v) for v in values[:6]]
    while len(nums) < 6:
        nums.append(0.0)
    return (nums[0], nums[1], nums[2], nums[3], nums[4], nums[5])


class _Interpreter:
    def __init__(self, doc: PdfDocument, fonts_cache: dict[int, PdfFont]) -> None:
        self.doc = doc
        self.fonts_cache = fonts_cache
        self.content = PageContent()
        self.ops = 0

    # ---- resources ----------------------------------------------------------------
    def _font(self, resources: dict[str, Any], name: str) -> PdfFont:
        fonts = self.doc.resolve(resources.get("Font")) if isinstance(resources, dict) else None
        ref = fonts.get(name) if isinstance(fonts, dict) else None
        font = self.doc.resolve(ref)
        if not isinstance(font, dict):  # a font the page uses but never defines
            if -1 not in self.fonts_cache:
                self.fonts_cache[-1] = PdfFont({}, self.doc.resolve, fallback=True)
            return self.fonts_cache[-1]
        key = ref.num if isinstance(ref, PdfRef) else id(font)
        if key not in self.fonts_cache:
            self.fonts_cache[key] = PdfFont(font, self.doc.resolve)
        return self.fonts_cache[key]

    # ---- operators ----------------------------------------------------------------
    def run(self, data: bytes, resources: dict[str, Any], ctm: Matrix, depth: int = 0) -> None:
        lexer = _Lexer(data)
        operands: list[Any] = []
        stack: list[tuple[Matrix, dict[str, Any]]] = []
        ts: dict[str, Any] = {
            "font": None,
            "size": 0.0,
            "Tc": 0.0,
            "Tw": 0.0,
            "Th": 1.0,
            "TL": 0.0,
            "Ts": 0.0,
        }
        tm: Matrix = IDENTITY
        tlm: Matrix = IDENTITY
        n = len(data)
        while lexer.pos < n:
            try:
                lexer.skip()
                if lexer.pos >= n:
                    break
                tok = lexer.parse()
            except Exception:
                break
            if type(tok) is not str:  # operand (names are PdfName, strings bytes)
                operands.append(tok)
                continue
            self.ops += 1
            if self.ops > MAX_OPERATIONS:
                break
            op = tok
            if op == "BI":  # inline image: skip to EI
                end = data.find(b"EI", lexer.pos)
                while end != -1 and not (
                    data[end - 1 : end] in b" \t\r\n" and data[end + 2 : end + 3] in b" \t\r\n"
                ):
                    end = data.find(b"EI", end + 2)
                lexer.pos = n if end == -1 else end + 2
            elif op == "q":
                stack.append((ctm, dict(ts)))
            elif op == "Q":
                if stack:
                    ctm, saved = stack.pop()
                    ts.update(saved)
            elif op == "cm" and len(operands) >= 6:
                ctm = _mul(_matrix(operands[-6:]), ctm)
            elif op == "BT":
                tm = tlm = IDENTITY
            elif op == "Tf" and len(operands) >= 2:
                name = operands[-2]
                ts["font"] = self._font(resources, str(name))
                ts["size"] = _num(operands[-1])
            elif op == "Tc" and operands:
                ts["Tc"] = _num(operands[-1])
            elif op == "Tw" and operands:
                ts["Tw"] = _num(operands[-1])
            elif op == "Tz" and operands:
                ts["Th"] = _num(operands[-1], 100.0) / 100.0
            elif op == "TL" and operands:
                ts["TL"] = _num(operands[-1])
            elif op == "Ts" and operands:
                ts["Ts"] = _num(operands[-1])
            elif op in ("Td", "TD") and len(operands) >= 2:
                tx, ty = _num(operands[-2]), _num(operands[-1])
                if op == "TD":
                    ts["TL"] = -ty
                tlm = _mul((1.0, 0.0, 0.0, 1.0, tx, ty), tlm)
                tm = tlm
            elif op == "Tm" and len(operands) >= 6:
                tlm = tm = _matrix(operands[-6:])
            elif op == "T*":
                tlm = _mul((1.0, 0.0, 0.0, 1.0, 0.0, -ts["TL"]), tlm)
                tm = tlm
            elif op in ("Tj", "'", '"', "TJ"):
                if op in ("'", '"'):
                    if op == '"' and len(operands) >= 3:
                        ts["Tw"], ts["Tc"] = _num(operands[-3]), _num(operands[-2])
                    tlm = _mul((1.0, 0.0, 0.0, 1.0, 0.0, -ts["TL"]), tlm)
                    tm = tlm
                items = operands[-1] if operands else b""
                items = items if isinstance(items, list) else [items]
                tm = self._show(items, ts, tm, ctm)
            elif op == "Do" and operands and depth < MAX_FORM_DEPTH:
                self._do(str(operands[-1]), resources, ctm, depth)
            operands = []

    def _show(self, items: list[Any], ts: dict[str, Any], tm: Matrix, ctm: Matrix) -> Matrix:
        font: PdfFont | None = ts["font"]
        size, th = ts["size"], ts["Th"]
        for item in items:
            if isinstance(item, int | float) and not isinstance(item, bool):
                tm = _mul((1.0, 0.0, 0.0, 1.0, -item / 1000.0 * size * th, 0.0), tm)
                continue
            if not isinstance(item, bytes) or font is None:
                continue
            start = _mul((size * th, 0.0, 0.0, size, 0.0, ts["Ts"]), _mul(tm, ctm))
            chars: list[str] = []
            for text, width, is_space in font.decode(item):
                advance = (width * size + ts["Tc"] + (ts["Tw"] if is_space else 0.0)) * th
                tm = _mul((1.0, 0.0, 0.0, 1.0, advance, 0.0), tm)
                chars.append(text)
            end = _mul(tm, ctm)
            text = "".join(chars)
            if text:
                scale = math.hypot(start[2], start[3]) or abs(size)
                self.content.runs.append(
                    TextRun(text, start[4], start[5], end[4], abs(scale), font.name)
                )
        return tm

    def _do(self, name: str, resources: dict[str, Any], ctm: Matrix, depth: int) -> None:
        doc = self.doc
        xobjects = doc.resolve(resources.get("XObject")) if isinstance(resources, dict) else None
        if not isinstance(xobjects, dict):
            return
        ref = xobjects.get(name)
        obj = doc.resolve(ref)
        if not isinstance(obj, PdfStream):
            return
        subtype = str(doc.resolve(obj.get("Subtype")) or "")
        if subtype == "Image":
            area = abs(ctm[0] * ctm[3] - ctm[1] * ctm[2])
            self.content.images.append(
                PdfImage(obj, area, ref.num if isinstance(ref, PdfRef) else None)
            )
        elif subtype == "Form":
            matrix = doc.resolve(obj.get("Matrix"))
            form_ctm = _mul(_matrix(matrix), ctm) if isinstance(matrix, list) else ctm
            form_resources = doc.resolve(obj.get("Resources"))
            try:
                data = decode_stream(obj, doc.resolve)
            except Exception:
                return
            self.run(
                data,
                form_resources if isinstance(form_resources, dict) else resources,
                form_ctm,
                depth + 1,
            )


def _page_streams(doc: PdfDocument, page: dict[str, Any]) -> bytes:
    contents = doc.resolve(page.get("Contents"))
    parts = contents if isinstance(contents, list) else [contents]
    out: list[bytes] = []
    for part in parts:
        stream = doc.resolve(part)
        if isinstance(stream, PdfStream):
            try:
                out.append(decode_stream(stream, doc.resolve))
            except Exception:
                continue
    return b"\n".join(out)


def page_content(
    doc: PdfDocument, page: dict[str, Any], fonts_cache: dict[int, PdfFont] | None = None
) -> PageContent:
    """Text runs and images of one page (see the module docstring)."""
    interp = _Interpreter(doc, fonts_cache if fonts_cache is not None else {})
    box = doc.resolve(page.get("CropBox")) or doc.resolve(page.get("MediaBox"))
    if isinstance(box, list) and len(box) == 4:
        x0, y0, x1, y1 = (_num(doc.resolve(v)) for v in box)
        interp.content.width, interp.content.height = abs(x1 - x0), abs(y1 - y0)
    resources = doc.resolve(page.get("Resources"))
    interp.run(_page_streams(doc, page), resources if isinstance(resources, dict) else {}, IDENTITY)
    return interp.content
