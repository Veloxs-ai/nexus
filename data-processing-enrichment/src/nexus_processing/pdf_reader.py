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

"""PDF object model reader (ISO 32000-1), standard library only.

Resolves a PDF the way a conforming reader does instead of scanning it with regular
expressions:

- cross-reference **tables** and **streams** (``/W``, ``/Index``), ``/Prev`` chains and
  hybrid files (``/XRefStm``); when they are missing or broken the xref is rebuilt by
  scanning for ``N G obj`` headers;
- **object streams** (``/ObjStm``): compressed objects are read from their container;
- stream filters: Flate (with PNG/TIFF predictors), LZW, ASCIIHex, ASCII85 and
  RunLength; image codecs (DCT, JPX, CCITT, JBIG2) are left encoded for the caller;
- the **page tree** in document order, with inherited ``/Resources``, ``/MediaBox`` and
  ``/Rotate``.

Encrypted files (standard security handler: RC4, AES-128, AES-256) are decrypted when an
empty user or owner password opens them (``pdf_crypt``; streams lazily, on first use).
``PdfDocument.needs_password`` is True when a real password is needed: nothing is guessed.
"""

from __future__ import annotations

import re
from typing import Any

from .pdf_crypt import SecurityHandler
from .pdf_filters import IMAGE_FILTERS
from .pdf_lexer import (
    WHITESPACE,
    PdfError,
    PdfName,
    PdfRef,
    PdfStream,
    _Lexer,
    decode_stream,
)

__all__ = [
    "IMAGE_FILTERS",
    "PdfDocument",
    "PdfError",
    "PdfName",
    "PdfRef",
    "PdfStream",
    "decode_stream",
]


class _SealedStream(PdfStream):
    """A stream of an encrypted file: its data is decrypted on first access to ``raw``."""

    def __init__(self, sdict: dict[str, Any], sealed: bytes, unseal: Any) -> None:
        self.dict = sdict
        self._sealed: bytes | None = sealed
        self._unseal = unseal
        self._raw: bytes | None = None

    @property
    def raw(self) -> bytes:  # type: ignore[override]
        if self._raw is None:
            self._raw = self._unseal(self._sealed or b"")
            self._sealed = None
        return self._raw


# --------------------------------------------------------------------------------------
# Document
# --------------------------------------------------------------------------------------
_OBJ_HEADER = re.compile(rb"(?<![0-9])(\d{1,10})\s+(\d{1,5})\s+obj\b")


class PdfDocument:
    """Random access to the objects of one PDF file (see the module docstring)."""

    def __init__(self, data: bytes) -> None:
        if not data or b"%PDF" not in data[:1024]:
            raise PdfError("not a PDF file (no %PDF header)")
        self.data = data
        match = re.search(rb"%PDF-(\d+\.\d+)", data[:1024])
        self.version = match.group(1).decode("ascii") if match else "1.4"
        self.xref: dict[int, tuple[int, int, int]] = {}  # num -> (kind, a, b)
        self.trailer: dict[str, Any] = {}
        self._cache: dict[int, Any] = {}
        self._objstm: dict[int, dict[int, Any]] = {}
        self.form_cache: dict[int, bytes] = {}  # decoded Form XObjects (pdf_content)
        self.repaired = False
        self._resolving: set[int] = set()
        try:
            self._read_xref_chain()
        except (PdfError, ValueError, IndexError):
            self.xref, self.trailer = {}, {}
        if not self.xref or "Root" not in self.trailer:
            self._rebuild()
        self.encrypted = "Encrypt" in self.trailer
        self.security: SecurityHandler | None = None
        self._encrypt_num: int | None = None
        if self.encrypted:
            self._open_security()

    # ---- encryption ---------------------------------------------------------------
    def _open_security(self) -> None:
        ref = self.trailer.get("Encrypt")
        self._encrypt_num = ref.num if isinstance(ref, PdfRef) else None
        encrypt = self.resolve(ref)
        ids = self.resolve(self.trailer.get("ID"))
        first_id = ids[0] if isinstance(ids, list) and ids and isinstance(ids[0], bytes) else b""
        if isinstance(encrypt, dict):
            self.security = SecurityHandler(encrypt, first_id)
        # Objects read before the key was known (the Encrypt dictionary aside) are re-read.
        self._cache = {n: o for n, o in self._cache.items() if n == self._encrypt_num}
        self._objstm = {}

    @property
    def needs_password(self) -> bool:
        """Encrypted, and no empty password opens it (or the handler is not supported)."""
        return self.encrypted and (self.security is None or self.security.needs_password)

    def _decrypt(self, obj: Any, num: int, gen: int, depth: int = 0) -> Any:
        security = self.security
        if security is None or depth > 200:
            return obj
        if isinstance(obj, bytes):
            return security.decrypt_string(obj, num, gen)
        if isinstance(obj, list):
            return [self._decrypt(x, num, gen, depth + 1) for x in obj]
        if isinstance(obj, dict):
            return {k: self._decrypt(v, num, gen, depth + 1) for k, v in obj.items()}
        if isinstance(obj, PdfStream):
            if obj.dict.get("Type") == "XRef":
                return obj
            sdict = self._decrypt(obj.dict, num, gen, depth + 1)
            return _SealedStream(
                sdict, obj.raw, lambda raw: security.decrypt_stream(raw, sdict, num, gen)
            )
        return obj

    # ---- cross references ---------------------------------------------------------
    def _read_xref_chain(self) -> None:
        tail = self.data[-2048:]
        idx = tail.rfind(b"startxref")
        if idx == -1:
            raise PdfError("no startxref")
        lexer = _Lexer(tail, idx + 9)
        offset = lexer.parse()
        seen: set[int] = set()
        first = True
        while isinstance(offset, int) and offset not in seen and 0 <= offset < len(self.data):
            seen.add(offset)
            trailer = self._read_xref_at(offset)
            if first:
                self.trailer = dict(trailer)
                first = False
            else:
                for key, value in trailer.items():
                    self.trailer.setdefault(key, value)
            if isinstance(trailer.get("XRefStm"), int):
                self._read_xref_at(int(trailer["XRefStm"]))
            offset = trailer.get("Prev")

    def _read_xref_at(self, offset: int) -> dict[str, Any]:
        lexer = _Lexer(self.data, offset)
        lexer.skip()
        if self.data.startswith(b"xref", lexer.pos):
            return self._read_xref_table(lexer.pos + 4)
        return self._read_xref_stream(offset)

    def _read_xref_table(self, pos: int) -> dict[str, Any]:
        data = self.data
        lexer = _Lexer(data, pos)
        while True:
            lexer.skip()
            if data.startswith(b"trailer", lexer.pos):
                lexer.pos += 7
                trailer = lexer.parse()
                return trailer if isinstance(trailer, dict) else {}
            start = lexer.parse()
            count = lexer.parse()
            if not isinstance(start, int) or not isinstance(count, int):
                raise PdfError("bad xref subsection")
            lexer.skip()
            for i in range(count):
                entry = data[lexer.pos : lexer.pos + 20]
                parts = entry.split()
                if len(parts) < 3:
                    raise PdfError("bad xref entry")
                lexer.pos += 20
                if len(entry) == 20 and entry[18:19] not in b" \r\n":
                    lexer.pos -= 1  # 19-byte entries written by some producers
                num = start + i
                if parts[2][:1] == b"n" and num not in self.xref:
                    self.xref[num] = (1, int(parts[0]), int(parts[1]))
                elif num not in self.xref:
                    self.xref[num] = (0, 0, 0)
                lexer.skip()

    def _read_xref_stream(self, offset: int) -> dict[str, Any]:
        obj = self._parse_indirect_at(offset)
        if not isinstance(obj, PdfStream):
            raise PdfError("xref offset does not point at an xref stream")
        d = obj.dict
        widths = [int(w) for w in d.get("W", [1, 2, 1])]
        size = int(d.get("Size", 0))
        index = d.get("Index") or [0, size]
        raw = decode_stream(obj)
        entry_len = sum(widths)
        pos = 0
        for start, count in zip(index[0::2], index[1::2], strict=False):
            for num in range(int(start), int(start) + int(count)):
                if pos + entry_len > len(raw):
                    break
                fields = []
                p = pos
                for w in widths:
                    fields.append(int.from_bytes(raw[p : p + w], "big") if w else None)
                    p += w
                pos += entry_len
                kind = fields[0] if fields[0] is not None else 1
                if num not in self.xref:
                    self.xref[num] = (int(kind), int(fields[1] or 0), int(fields[2] or 0))
        return {
            k: v for k, v in d.items() if k not in ("Length", "Filter", "DecodeParms", "W", "Index")
        }

    def _rebuild(self) -> None:
        """Recover objects by scanning for ``N G obj`` headers (damaged or missing xref)."""
        self.repaired = True
        self.xref = {}
        for match in _OBJ_HEADER.finditer(self.data):
            self.xref[int(match.group(1))] = (1, match.start(), int(match.group(2)))
        trailer: dict[str, Any] = {}
        for match in re.finditer(rb"trailer\s*<<", self.data):
            parsed = _Lexer(self.data, match.end() - 2).parse()
            if isinstance(parsed, dict):
                trailer.update(parsed)
        if "Root" not in trailer:
            for num in list(self.xref):
                obj = self.get(num)
                if isinstance(obj, dict) and obj.get("Type") == "Catalog":
                    trailer["Root"] = PdfRef(num)
                    break
                if isinstance(obj, PdfStream) and obj.get("Type") == "XRef" and "Root" in obj.dict:
                    trailer.setdefault("Root", obj.dict["Root"])
        self.trailer = trailer

    # ---- objects ------------------------------------------------------------------
    def _parse_indirect_at(self, offset: int) -> Any:
        lexer = _Lexer(self.data, offset)
        match = _OBJ_HEADER.match(self.data, offset) or _OBJ_HEADER.search(
            self.data, offset, offset + 64
        )
        if match:
            lexer.pos = match.end()
        obj = lexer.parse()
        lexer.skip()
        if isinstance(obj, dict) and self.data.startswith(b"stream", lexer.pos):
            start = lexer.pos + 6
            if self.data[start : start + 2] == b"\r\n":
                start += 2
            elif self.data[start : start + 1] in (b"\n", b"\r"):
                start += 1
            length = obj.get("Length")
            if isinstance(length, PdfRef):
                length = self.get(length.num) if length.num not in self._resolving else None
            end = -1
            if (
                isinstance(length, int)
                and length >= 0
                and self.data.startswith(b"endstream", self._skip_ws(start + length))
            ):
                end = start + length
            if end == -1:
                found = self.data.find(b"endstream", start)
                end = found if found != -1 else len(self.data)
                while end > start and self.data[end - 1 : end] in (b"\n", b"\r"):
                    end -= 1
            return PdfStream(obj, self.data[start:end])
        return obj

    def _skip_ws(self, pos: int) -> int:
        while pos < len(self.data) and self.data[pos] in WHITESPACE:
            pos += 1
        return pos

    def get(self, num: int) -> Any:
        if num in self._cache:
            return self._cache[num]
        entry = self.xref.get(num)
        if entry is None:
            return None
        kind, a, _gen = entry
        if num in self._resolving:
            return None
        self._resolving.add(num)
        try:
            if kind == 1:
                obj = self._parse_indirect_at(a)
                if self.security is not None and self.security.key and num != self._encrypt_num:
                    obj = self._decrypt(obj, num, _gen)
            elif kind == 2:
                obj = self._from_objstm(a, num)
            else:
                obj = None
        except (PdfError, ValueError, IndexError, RecursionError):
            obj = None
        finally:
            self._resolving.discard(num)
        self._cache[num] = obj
        return obj

    def _from_objstm(self, container: int, num: int) -> Any:
        if container not in self._objstm:
            stream = self.get(container)
            objects: dict[int, Any] = {}
            if isinstance(stream, PdfStream):
                data = decode_stream(stream, self.resolve)
                n = int(self.resolve(stream.get("N", 0)) or 0)
                first = int(self.resolve(stream.get("First", 0)) or 0)
                header = _Lexer(data)
                pairs = []
                for _ in range(n):
                    obj_num = header.parse()
                    obj_off = header.parse()
                    if isinstance(obj_num, int) and isinstance(obj_off, int):
                        pairs.append((obj_num, obj_off))
                for obj_num, obj_off in pairs:
                    try:
                        objects[obj_num] = _Lexer(data, first + obj_off).parse()
                    except PdfError:
                        objects[obj_num] = None
            self._objstm[container] = objects
        return self._objstm[container].get(num)

    def resolve(self, value: Any) -> Any:
        """Follow indirect references (bounded) to the object they name."""
        hops = 0
        while isinstance(value, PdfRef) and hops < 32:
            value = self.get(value.num)
            hops += 1
        return value

    # ---- pages --------------------------------------------------------------------
    def pages(self) -> list[dict[str, Any]]:
        """Page dictionaries in document order, with inherited attributes filled in."""
        root = self.resolve(self.trailer.get("Root"))
        out: list[dict[str, Any]] = []
        if isinstance(root, dict):
            self._walk(self.resolve(root.get("Pages")), {}, out, set(), 0)
        if not out:  # no usable tree: every /Type /Page object, in file order
            for num in sorted(self.xref):
                obj = self.get(num)
                if isinstance(obj, dict) and obj.get("Type") == "Page":
                    out.append(dict(obj))
        return out

    def _walk(
        self,
        node: Any,
        inherited: dict[str, Any],
        out: list[dict[str, Any]],
        seen: set[int],
        depth: int,
    ) -> None:
        if not isinstance(node, dict) or depth > 64:
            return
        attrs = dict(inherited)
        for key in ("Resources", "MediaBox", "CropBox", "Rotate"):
            if key in node:
                attrs[key] = node[key]
        kids = self.resolve(node.get("Kids"))
        if node.get("Type") == "Pages" or isinstance(kids, list):
            for kid in kids or []:
                if isinstance(kid, PdfRef):
                    if kid.num in seen:
                        continue
                    seen.add(kid.num)
                self._walk(self.resolve(kid), attrs, out, seen, depth + 1)
            return
        page = dict(node)
        for key, value in attrs.items():
            page.setdefault(key, value)
        out.append(page)

    def info(self) -> dict[str, Any]:
        info = self.resolve(self.trailer.get("Info"))
        return info if isinstance(info, dict) else {}
