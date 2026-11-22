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

"""Scanned PDF pages: the page image, ready for OCR.

A page without a text layer is a scan: one large image drawn over the page. This module
turns that image XObject into an encoded image an OCR engine accepts:

- DCT (JPEG) and JPX (JPEG 2000) data are already image files;
- Flate/LZW/raw samples are wrapped as a PNG (``zlib`` and ``struct`` only) for 8-bit
  gray, RGB and CMYK (converted to RGB) and 1-bit images, honouring ``/Decode [1 0]``;
- CCITT G3/G4 fax data is wrapped in a minimal TIFF header (``struct`` only);
- JBIG2 cannot be decoded without a package: ``page_image`` reports it as unsupported.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from operator import add
from typing import Any

from .pdf_content import PdfImage
from .pdf_filters import apply_filters, stream_filters
from .pdf_reader import PdfDocument

__all__ = ["PageImage", "page_image", "page_images"]

MIN_PAGE_SHARE = 0.25  # an image covering less of the page is a figure, not a scan
MIN_TILE_SHARE = 0.02  # a tile of a page scanned in strips or blocks; smaller ones are icons
MAX_TILES = 24


@dataclass
class PageImage:
    data: bytes | None  # an encoded image (JPEG, JPEG 2000, PNG or TIFF), None if unsupported
    format: str  # jpeg | jp2 | png | tiff | jbig2 | unknown
    width: int
    height: int


def _png(width: int, height: int, mode: str, samples: bytes) -> bytes:
    channels = {"L": 1, "RGB": 3, "1": 1}[mode]
    bit_depth = 1 if mode == "1" else 8
    color_type = 0 if channels == 1 else 2
    row = (width * channels * bit_depth + 7) // 8
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        raw += samples[y * row : (y + 1) * row].ljust(row, b"\0")

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body))
            + kind
            + body
            + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, bit_depth, color_type, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        + chunk(b"IEND", b"")
    )


_INK = bytes(255 - min(255, s) for s in range(511))  # 255 - min(255, ink + black)
_INVERT = bytes(range(255, -1, -1))


def _cmyk_to_rgb(samples: bytes) -> bytes:
    """Naive CMYK -> RGB (``255 - min(255, c + k)`` per channel), channel by channel with
    C-level ``map`` over strided slices instead of a Python loop per pixel."""
    n = len(samples) // 4
    samples = samples[: 4 * n]
    black = samples[3::4]
    out = bytearray(3 * n)
    for channel in range(3):
        out[channel::3] = bytes(map(_INK.__getitem__, map(add, samples[channel::4], black)))
    return bytes(out)


def _tiff_ccitt(width: int, height: int, data: bytes, parms: dict[str, Any]) -> bytes:
    k = int(parms.get("K", 0) or 0)
    compression = 4 if k < 0 else 3  # T.6 (G4) or T.4 (G3)
    black_is_1 = bool(parms.get("BlackIs1", False))
    entries = [
        (256, 4, width),
        (257, 4, height),
        (258, 3, 1),
        (259, 3, compression),
        (262, 3, 1 if black_is_1 else 0),
        (273, 4, 0),
        (277, 3, 1),
        (278, 4, height),
        (279, 4, len(data)),
    ]
    if compression == 3:
        entries.append((292, 4, 1 if k > 0 else 0))
    entries.sort()
    ifd_offset = 8
    data_offset = ifd_offset + 2 + 12 * len(entries) + 4
    ifd = struct.pack("<H", len(entries))
    for tag, kind, value in entries:
        if tag == 273:
            value = data_offset
        if kind == 3:
            ifd += struct.pack("<HHIHH", tag, kind, 1, value, 0)
        else:
            ifd += struct.pack("<HHII", tag, kind, 1, value)
    ifd += struct.pack("<I", 0)
    return b"II*\x00" + struct.pack("<I", ifd_offset) + ifd + data


def _encode(doc: PdfDocument, image: PdfImage) -> PageImage:
    stream = image.stream
    resolve = doc.resolve
    width = int(resolve(stream.get("Width")) or 0)
    height = int(resolve(stream.get("Height")) or 0)
    filters = stream_filters(stream.dict, resolve)
    names = [name for name, _ in filters]
    data = apply_filters(stream.raw, filters, stop_at_image=True)
    last = names[-1] if names else ""
    if last in ("DCTDecode", "DCT"):
        return PageImage(data, "jpeg", width, height)
    if last == "JPXDecode":
        return PageImage(data, "jp2", width, height)
    if last == "JBIG2Decode":
        return PageImage(None, "jbig2", width, height)
    if last in ("CCITTFaxDecode", "CCF"):
        parms = filters[-1][1]
        cols = int(parms.get("Columns", width) or width)
        rows = int(parms.get("Rows", height) or height)
        return PageImage(_tiff_ccitt(cols, rows, data, parms), "tiff", cols, rows)
    bpc = int(resolve(stream.get("BitsPerComponent")) or 8)
    space = resolve(stream.get("ColorSpace"))
    space_name = str(space[0] if isinstance(space, list) and space else space or "DeviceGray")
    if isinstance(space, list) and space_name == "ICCBased" and len(space) > 1:
        icc = resolve(space[1])
        n = int(resolve(icc.get("N")) or 1) if hasattr(icc, "get") else 1
        space_name = {1: "DeviceGray", 3: "DeviceRGB", 4: "DeviceCMYK"}.get(n, "DeviceGray")
    if stream.get("ImageMask") or bpc == 1:
        decode = resolve(stream.get("Decode"))
        samples = data
        # 0 is black in a gray image and paints (black) in a stencil mask; [1 0] inverts.
        if isinstance(decode, list) and decode[:1] == [1]:
            samples = bytes(samples).translate(_INVERT)
        return PageImage(_png(width, height, "1", samples), "png", width, height)
    if bpc != 8:
        return PageImage(None, "unknown", width, height)
    if space_name in ("DeviceRGB", "CalRGB"):
        return PageImage(_png(width, height, "RGB", data), "png", width, height)
    if space_name == "DeviceCMYK":
        return PageImage(_png(width, height, "RGB", _cmyk_to_rgb(data)), "png", width, height)
    if space_name in ("DeviceGray", "CalGray"):
        return PageImage(_png(width, height, "L", data), "png", width, height)
    return PageImage(None, "unknown", width, height)


def _encoded(doc: PdfDocument, image: PdfImage) -> PageImage:
    try:
        return _encode(doc, image)
    except Exception:
        return PageImage(None, "unknown", 0, 0)


def page_images(doc: PdfDocument, images: list[PdfImage], page_area: float) -> list[PageImage]:
    """The images that carry a text-less page's content, in reading order.

    One image covering ``MIN_PAGE_SHARE`` of the page is the scan (``page_image``). A page
    scanned in strips or tiles has no such image; its tiles (each at least
    ``MIN_TILE_SHARE`` of the page, together at least ``MIN_PAGE_SHARE``) are returned top
    to bottom, left to right, each image once. ``[]`` when the page has neither.
    """
    single = page_image(doc, images, page_area)
    if single is not None or not images or not page_area:
        return [single] if single is not None else []
    seen: set[int] = set()
    tiles: list[PdfImage] = []
    for image in images:
        key = image.ref if image.ref is not None else id(image.stream)
        if image.area >= MIN_TILE_SHARE * page_area and key not in seen:
            seen.add(key)
            tiles.append(image)
    if not tiles or sum(t.area for t in tiles) < MIN_PAGE_SHARE * page_area:
        return []
    tiles.sort(key=lambda t: (-round(t.top, 1), t.left))
    return [_encoded(doc, t) for t in tiles[:MAX_TILES]]


def page_image(doc: PdfDocument, images: list[PdfImage], page_area: float) -> PageImage | None:
    """The scan image of a page (its largest image, when it covers enough of the page)."""
    if not images:
        return None
    largest = max(images, key=lambda im: im.area)
    if page_area and largest.area < MIN_PAGE_SHARE * page_area:
        return None
    return _encoded(doc, largest)
