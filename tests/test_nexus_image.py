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
    assert len(chunk.embedding) == 3072

    # Verify IEEE 754 L2 unit normalization
    norm = math.sqrt(sum(x * x for x in chunk.embedding))
    assert abs(norm - 1.0) < 1e-7

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
    assert doc.execution_trace[4].stage_name == "3072D Multi-Gram Visual Vector Projection"

    # Verify indexing and retrieval
    client.index_document(doc, collection="visual_assets")
    results = client.search("diagram", limit=5)
    assert len(results) >= 1
    assert any(r.id == "img_test_01:0" for r in results)


def test_nexus_client_embed_image():
    client = NexusClient(in_memory_only=True)
    png_data = make_png_bytes(8, 8, color=(255, 128, 0))

    vec = client.embed_image(png_data, format_hint="png")
    assert len(vec) == 3072
    norm = math.sqrt(sum(x * x for x in vec))
    assert abs(norm - 1.0) < 1e-7


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
    assert len(doc.chunks[0].embedding) == 3072
    assert len(doc.execution_trace) == 5
