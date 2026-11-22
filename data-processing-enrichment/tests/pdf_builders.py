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

"""Builders of small, valid PDFs for the reader tests (standard library only)."""

from __future__ import annotations

import zlib


def _obj_bytes(value: str | bytes) -> bytes:
    return value.encode("latin-1") if isinstance(value, str) else value


def build_pdf(
    objects: dict[int, bytes | str],
    root: int = 1,
    xref_stream: bool = False,
    compress_into: dict[int, list[int]] | None = None,
    info: int | None = None,
    trailer: str = "",
) -> bytes:
    """A PDF with ``objects`` (number -> body); a classic xref table, or an xref stream.

    ``compress_into``: ``{container number: [object numbers]}`` puts those objects in an
    object stream (``/ObjStm``); requires ``xref_stream``.
    """
    objects = {k: _obj_bytes(v) for k, v in objects.items()}
    in_stream: dict[int, tuple[int, int]] = {}
    for container, members in (compress_into or {}).items():
        header, body = [], b""
        for index, num in enumerate(members):
            header.append(f"{num} {len(body)}")
            body += objects.pop(num) + b"\n"
            in_stream[num] = (container, index)
        head = " ".join(header).encode() + b"\n"
        data = zlib.compress(head + body)
        objects[container] = (
            f"<< /Type /ObjStm /N {len(members)} /First {len(head)} /Length {len(data)} "
            "/Filter /FlateDecode >>\n"
            "stream\n".encode()
            + data
            + b"\nendstream"
        )
    out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets: dict[int, int] = {}
    for num in sorted(objects):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode() + objects[num] + b"\nendobj\n"
    size = max([*objects, *in_stream]) + 2
    trailer_extra = (f" /Info {info} 0 R" if info else "") + trailer
    if not xref_stream:
        start = len(out)
        out += f"xref\n0 {size - 1}\n0000000000 65535 f \n".encode()
        for num in range(1, size - 1):
            out += f"{offsets.get(num, 0):010d} 00000 {'n' if num in offsets else 'f'} \n".encode()
        out += f"trailer\n<< /Size {size - 1} /Root {root} 0 R{trailer_extra} >>\n".encode()
        out += f"startxref\n{start}\n%%EOF\n".encode()
        return bytes(out)
    xref_num = size - 1
    offsets[xref_num] = len(out)
    rows = bytearray()
    for num in range(size):
        if num in offsets:
            rows += bytes([1]) + offsets[num].to_bytes(4, "big") + bytes([0])
        elif num in in_stream:
            container, index = in_stream[num]
            rows += bytes([2]) + container.to_bytes(4, "big") + bytes([index])
        else:
            rows += bytes([0, 0, 0, 0, 0, 0])
    data = zlib.compress(bytes(rows))
    out += (
        f"{xref_num} 0 obj\n<< /Type /XRef /Size {size} /W [1 4 1] /Root {root} 0 R{trailer_extra} "
        f"/Length {len(data)} /Filter /FlateDecode >>\nstream\n".encode()
        + data
        + b"\nendstream\nendobj\n"
    )
    out += f"startxref\n{offsets[xref_num]}\n%%EOF\n".encode()
    return bytes(out)


def stream(content: bytes, compress: bool = True, extra: str = "") -> bytes:
    data = zlib.compress(content) if compress else content
    flt = " /Filter /FlateDecode" if compress else ""
    return f"<< /Length {len(data)}{flt}{extra} >>\nstream\n".encode() + data + b"\nendstream"


def text_pages(
    pages: list[list[tuple[float, float, float, str]]], font: str = "/F1"
) -> dict[int, bytes | str]:
    """Objects of a document whose pages show ``(x, y, size, text)`` lines in Helvetica."""
    objects: dict[int, bytes | str] = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        3: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    }
    kids = []
    num = 4
    for lines in pages:
        ops = []
        for x, y, size, text in lines:
            safe = (
                text.encode("cp1252")
                .replace(b"\\", b"\\\\")
                .replace(b"(", b"\\(")
                .replace(b")", b"\\)")
            )
            ops.append(f"BT {font} {size} Tf 1 0 0 1 {x} {y} Tm (".encode() + safe + b") Tj ET")
        objects[num + 1] = stream(b"\n".join(ops))
        objects[num] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {num + 1} 0 R "
            f"/Resources << /Font << /F1 3 0 R >> >> >>"
        )
        kids.append(f"{num} 0 R")
        num += 2
    objects[2] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    return objects
