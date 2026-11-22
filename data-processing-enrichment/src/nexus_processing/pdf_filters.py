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

"""PDF stream filters (ISO 32000-1 §7.4), standard library only.

Flate (zlib, with PNG and TIFF predictors), LZW, ASCIIHex, ASCII85 and RunLength.
Image codecs (DCT/JPEG, JPX/JPEG 2000, CCITT fax, JBIG2) are not decoded here: the
encoded bytes are returned for an image library or OCR.
"""

from __future__ import annotations

import re
import zlib
from operator import add
from typing import Any

__all__ = ["IMAGE_FILTERS", "MAX_DECODED_STREAM", "apply_filters", "stream_filters"]

MAX_DECODED_STREAM = 64 * 1024 * 1024  # a single decoded stream may not exceed this (zip bombs)

IMAGE_FILTERS = {"DCTDecode", "DCT", "JPXDecode", "CCITTFaxDecode", "CCF", "JBIG2Decode"}


def _flate(data: bytes) -> bytes:
    """Inflate; a damaged stream keeps what inflated before the damage."""
    decomp = zlib.decompressobj()
    out = bytearray()
    for i in range(0, len(data), 4096):
        try:
            out += decomp.decompress(data[i : i + 4096])
        except zlib.error:
            break
        if len(out) > MAX_DECODED_STREAM or decomp.eof:
            break
    return bytes(out[:MAX_DECODED_STREAM])


_BYTE_SUM = bytes(s & 0xFF for s in range(511))  # (a + b) & 0xFF for two bytes


def _predict(data: bytes, parms: dict[str, Any]) -> bytes:
    predictor = int(parms.get("Predictor", 1) or 1)
    if predictor < 2:
        return data
    colors = int(parms.get("Colors", 1) or 1)
    bpc = int(parms.get("BitsPerComponent", 8) or 8)
    columns = int(parms.get("Columns", 1) or 1)
    bpp = max(1, colors * bpc // 8)
    row_len = (colors * bpc * columns + 7) // 8
    if predictor == 2:  # TIFF: horizontal differencing (8-bit components)
        out = bytearray(data)
        for start in range(0, len(out), row_len):
            for i in range(start + bpp, min(start + row_len, len(out))):
                out[i] = (out[i] + out[i - bpp]) & 0xFF
        return bytes(out)
    out = bytearray()
    prev = bytearray(row_len)
    step = row_len + 1
    for start in range(0, len(data) - row_len, step):
        kind = data[start]
        row = bytearray(data[start + 1 : start + step])
        if kind == 1:
            for i in range(bpp, len(row)):
                row[i] = (row[i] + row[i - bpp]) & 0xFF
        elif kind == 2:  # Up: no dependency inside the row, so C-level map + table
            row = bytearray(map(_BYTE_SUM.__getitem__, map(add, row, prev)))
        elif kind == 3:
            for i in range(len(row)):
                left = row[i - bpp] if i >= bpp else 0
                row[i] = (row[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif kind == 4:
            for i in range(len(row)):
                a = row[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                row[i] = (row[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 0xFF
        out += row
        prev = row
    return bytes(out)


def _ascii_hex(data: bytes) -> bytes:
    digits = re.sub(rb"[^0-9A-Fa-f]", b"", data.split(b">", 1)[0])
    if len(digits) % 2:
        digits += b"0"
    return bytes.fromhex(digits.decode("ascii"))


def _ascii85(data: bytes) -> bytes:
    body = data.strip()
    if body.startswith(b"<~"):
        body = body[2:]
    body = body.split(b"~>", 1)[0]
    body = re.sub(rb"\s", b"", body)
    out = bytearray()
    group: list[int] = []
    for c in body:
        if c == 0x7A and not group:  # 'z'
            out += b"\0\0\0\0"
            continue
        if c < 33 or c > 117:
            continue
        group.append(c - 33)
        if len(group) == 5:
            value = 0
            for g in group:
                value = value * 85 + g
            out += (value & 0xFFFFFFFF).to_bytes(4, "big")
            group = []
    if group:
        missing = 5 - len(group)
        value = 0
        for g in group + [84] * missing:
            value = value * 85 + g
        out += (value & 0xFFFFFFFF).to_bytes(4, "big")[: 4 - missing]
    return bytes(out)


def _lzw(data: bytes, early_change: int = 1) -> bytes:
    out = bytearray()
    table = [bytes([i]) for i in range(256)] + [b"", b""]
    width = 9
    prev: bytes | None = None
    bits = 0
    nbits = 0
    for byte in data:
        bits = (bits << 8) | byte
        nbits += 8
        while nbits >= width:
            nbits -= width
            code = (bits >> nbits) & ((1 << width) - 1)
            if code == 256:  # clear
                table = table[:258]
                width = 9
                prev = None
                continue
            if code == 257:  # end of data
                return bytes(out)
            if code < len(table):
                entry = table[code]
                if prev is not None:
                    table.append(prev + entry[:1])
            elif prev is not None:
                entry = prev + prev[:1]
                table.append(entry)
            else:
                return bytes(out)
            out += entry
            prev = entry
            if len(table) + early_change >= (1 << width) and width < 12:
                width += 1
            if len(out) > MAX_DECODED_STREAM:
                return bytes(out)
    return bytes(out)


def _run_length(data: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i < len(data):
        n = data[i]
        if n == 128:
            break
        if n < 128:
            out += data[i + 1 : i + 2 + n]
            i += n + 2
        else:
            out += data[i + 1 : i + 2] * (257 - n)
            i += 2
    return bytes(out)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def stream_filters(
    stream_dict: dict[str, Any], resolve: Any = None
) -> list[tuple[str, dict[str, Any]]]:
    """``[(filter name, decode parameters), ...]`` of a stream dictionary."""
    resolve = resolve or (lambda x: x)
    names = [str(resolve(f)) for f in _as_list(resolve(stream_dict.get("Filter")))]
    parms = [
        resolve(p) or {}
        for p in _as_list(resolve(stream_dict.get("DecodeParms") or stream_dict.get("DP")))
    ]
    return [
        (n, parms[i] if i < len(parms) and isinstance(parms[i], dict) else {})
        for i, n in enumerate(names)
    ]


def apply_filters(
    data: bytes, filters: list[tuple[str, dict[str, Any]]], stop_at_image: bool = True
) -> bytes:
    """Decode ``data`` through ``filters``; stops at an image codec when ``stop_at_image`` (or at
    an unknown filter) and returns the bytes still encoded for it."""
    for name, p in filters:
        if name in ("FlateDecode", "Fl"):
            data = _predict(_flate(data), p)
        elif name in ("LZWDecode", "LZW"):
            data = _predict(_lzw(data, int(p.get("EarlyChange", 1))), p)
        elif name in ("ASCIIHexDecode", "AHx"):
            data = _ascii_hex(data)
        elif name in ("ASCII85Decode", "A85"):
            data = _ascii85(data)
        elif name in ("RunLengthDecode", "RL"):
            data = _run_length(data)
        elif name in IMAGE_FILTERS and stop_at_image:
            return data
        else:
            return data
    return data
