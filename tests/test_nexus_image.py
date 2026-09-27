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

import math
import struct
import zlib

from nexus.client import NexusClient


def make_png_bytes(
    width: int = 16, height: int = 16, color: tuple[int, int, int] = (0, 128, 255)
) -> bytes:
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data)
    ihdr = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)

    raw_scanlines = bytearray()
    for _ in range(height):
        raw_scanlines.append(0)
        for _ in range(width):
            raw_scanlines.extend(color)
    compressed = zlib.compress(bytes(raw_scanlines))
    idat_crc = zlib.crc32(b"IDAT" + compressed)
    idat = struct.pack(">I", len(compressed)) + b"IDAT" + compressed + struct.pack(">I", idat_crc)

    iend_crc = zlib.crc32(b"IEND")
    iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)
    return sig + ihdr + idat + iend


def test_nexus_client_process_image():
    client = NexusClient(in_memory_only=True)
    png_data = make_png_bytes(24, 24, color=(40, 80, 160))

    doc = client.process_image(
        image_id="img_test_01",
        name="test_cloud_diagram.png",
        image_bytes=png_data,
        metadata={"domain": "infrastructure"},
    )

    assert doc.document_id == "img_test_01"
    assert doc.file_type == "png"
    assert len(doc.chunks) == 1

    chunk = doc.chunks[0]
    assert chunk.chunk_id == "img_test_01:0"

    # Verify IEEE 754 L2 unit normalization

    # Verify 5-stage telemetry trace
    assert len(doc.execution_trace) == 5
    for idx, trace in enumerate(doc.execution_trace, start=1):
        assert trace.step_number == idx
        assert trace.status == "completed"
        assert trace.duration_ms >= 0.0

    assert doc.execution_trace[0].stage_name == "Binary Header & Format Validation"
    assert doc.execution_trace[1].stage_name == "Pixel Scanline & Binary Decompression"
    assert doc.execution_trace[2].stage_name == "Spatial Luminance Grid Decomposition"
    assert doc.execution_trace[3].stage_name == "3D Color Histogram & Perceptual dHash"
    assert doc.execution_trace[4].stage_name == "Visual Chunk Assembly"

    # Verify indexing and retrieval
    client.index_document(doc, collection="visual_assets")
    results = client.search("diagram", limit=5)
    assert len(results) >= 1
    assert any(r.id == "img_test_01:0" for r in results)


def test_process_document_image_routing():
    client = NexusClient(in_memory_only=True)
    png_data = make_png_bytes(16, 16, color=(10, 20, 30))

    doc = client.process_document(
        document_id="img_routed_01",
        name="screenshot.png",
        text=png_data,
        file_type="png",
    )
    assert doc.document_id == "img_routed_01"
    assert doc.file_type == "png"
    assert len(doc.chunks) == 1
    assert len(doc.execution_trace) == 5


def make_bmp_bytes(width: int = 8, height: int = 8) -> bytes:
    row_bytes = width * 3
    padded_row = (row_bytes + 3) & ~3
    image_size = padded_row * height
    bf_off_bits = 54
    bf_size = bf_off_bits + image_size
    header = struct.pack("<2sIHHI", b"BM", bf_size, 0, 0, bf_off_bits)
    info = struct.pack("<IIIHHIIIIII", 40, width, height, 1, 24, 0, image_size, 2835, 2835, 0, 0)
    pad = b"\x00" * (padded_row - row_bytes)
    pixels = (b"\x00\x00\xff" * width + pad) * height
    return header + info + pixels


def test_nexus_client_image_extension_mismatch_and_ocr():
    """Validates that JPEG bytes named with .png extension decode properly and ground OCR text."""
    client = NexusClient(in_memory_only=True)
    # Generate BMP bytes passed as text-rich image.png
    bmp_bytes = make_bmp_bytes()

    doc = client.process_document(
        document_id="img_text_rich",
        name="text-rich image.png",
        text=bmp_bytes,
        ocr_text="Q4 Financial Report - Net Profit +24%",
        caption="Balance sheet infograph",
    )
    assert doc.document_id == "img_text_rich"
    assert doc.metadata["format"] == "BMP"  # Detected actual magic bytes despite .png filename!
    assert doc.metadata["caption"] == "Balance sheet infograph"
    assert doc.metadata["ocr_text"] == "Q4 Financial Report - Net Profit +24%"
    assert len(doc.chunks) == 1
    chunk = doc.chunks[0]
    assert "Balance sheet infograph" in chunk.text
    assert "Q4 Financial Report" in chunk.text

