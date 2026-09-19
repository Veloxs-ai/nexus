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

import struct
import zlib

from nexus_processing.images import (
    decode_bmp,
    decode_png,
    detect_image_format,
    process_image_binary,
)


def make_test_png(
    width: int = 8, height: int = 8, color: tuple[int, int, int] = (255, 0, 0)
) -> bytes:
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data)
    ihdr = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)

    raw_scanlines = bytearray()
    for _ in range(height):
        raw_scanlines.append(0)  # filter type 0
        for _ in range(width):
            raw_scanlines.extend(color)
    compressed = zlib.compress(bytes(raw_scanlines))
    idat_crc = zlib.crc32(b"IDAT" + compressed)
    idat = struct.pack(">I", len(compressed)) + b"IDAT" + compressed + struct.pack(">I", idat_crc)

    iend_crc = zlib.crc32(b"IEND")
    iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)
    return sig + ihdr + idat + iend


def make_test_bmp(
    width: int = 8, height: int = 8, color: tuple[int, int, int] = (0, 255, 0)
) -> bytes:
    row_bytes = ((width * 3 + 3) // 4) * 4
    pixel_data_size = row_bytes * height
    file_size = 54 + pixel_data_size
    header = struct.pack("<2sIHHI", b"BM", file_size, 0, 0, 54)
    dib = struct.pack(
        "<IIIHHIIIIII", 40, width, height, 1, 24, 0, pixel_data_size, 2835, 2835, 0, 0
    )

    pixels = bytearray()
    padding = b"\x00" * (row_bytes - width * 3)
    b, g, r = color[2], color[1], color[0]
    for _ in range(height):
        for _ in range(width):
            pixels.extend([b, g, r])
        pixels.extend(padding)
    return header + dib + bytes(pixels)


def test_detect_image_format():
    png_bytes = make_test_png(4, 4)
    bmp_bytes = make_test_bmp(4, 4)
    fake_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00"

    assert detect_image_format(png_bytes) == "png"
    assert detect_image_format(bmp_bytes) == "bmp"
    assert detect_image_format(fake_jpeg) == "jpeg"
    assert detect_image_format(b"not_an_image") == "unknown"


def test_decode_png():
    png_bytes = make_test_png(12, 10, color=(100, 150, 200))
    meta, pixels = decode_png(png_bytes)

    assert meta.format == "PNG"
    assert meta.width == 12
    assert meta.height == 10
    assert meta.aspect_ratio == 1.2
    assert len(pixels) > 0


def test_decode_bmp():
    bmp_bytes = make_test_bmp(16, 8, color=(50, 100, 150))
    meta, pixels = decode_bmp(bmp_bytes)

    assert meta.format == "BMP"
    assert meta.width == 16
    assert meta.height == 8
    assert meta.aspect_ratio == 2.0
    assert len(pixels) > 0


def test_process_image_binary_features():
    png_bytes = make_test_png(16, 16, color=(200, 50, 25))
    payload = process_image_binary(png_bytes)

    assert payload.metadata.format == "PNG"
    assert len(payload.spatial_grid) == 64  # 8x8 spatial grid
    assert len(payload.color_histogram) == 64  # 4x4x4 color cube
    assert len(payload.luminance_histogram) == 32
    assert len(payload.edge_signature) == 16  # 64-bit hex dHash
    assert "PNG" in payload.narrative_summary
    assert "Dimensions: 16x16" in payload.narrative_summary
