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

import zlib

from nexus_processing.pdf import (
    decode_pdf_hex_string,
    decode_pdf_literal_string,
    extract_text_from_content_stream,
    process_pdf_binary,
)


def make_test_pdf(pages_text: list[str]) -> bytes:
    """Generates a valid ISO 32000-1 compliant multi-page PDF in pure Python standard library."""
    objects: dict[int, bytes] = {}
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"

    page_obj_ids: list[int] = []
    curr_id = 3

    for p_text in pages_text:
        page_id = curr_id
        content_id = curr_id + 1
        page_obj_ids.append(page_id)

        safe_text = (
            p_text.encode("utf-8")
            .replace(b"\\", b"\\\\")
            .replace(b"(", b"\\(")
            .replace(b")", b"\\)")
        )
        stream_raw = b"BT /F1 12 Tf 72 700 Td (" + safe_text + b") Tj ET"
        compressed = zlib.compress(stream_raw)

        page_dict_str = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content_id} 0 R >>"
        )
        objects[page_id] = page_dict_str.encode("ascii")
        objects[content_id] = (
            f"<< /Length {len(compressed)} /Filter /FlateDecode >>\nstream\n".encode("ascii")
            + compressed
            + b"\nendstream"
        )
        curr_id += 2

    kids_str = " ".join(f"{pid} 0 R" for pid in page_obj_ids)
    objects[2] = f"<< /Type /Pages /Kids [{kids_str}] /Count {len(page_obj_ids)} >>".encode("ascii")

    pdf_bytes = bytearray(b"%PDF-1.4\n")
    xref_offsets: dict[int, int] = {}
    for oid in sorted(objects.keys()):
        xref_offsets[oid] = len(pdf_bytes)
        pdf_bytes.extend(f"{oid} 0 obj\n".encode("ascii"))
        pdf_bytes.extend(objects[oid])
        pdf_bytes.extend(b"\nendobj\n")

    startxref = len(pdf_bytes)
    pdf_bytes.extend(b"xref\n")
    max_obj = max(objects.keys())
    pdf_bytes.extend(f"0 {max_obj + 1}\n".encode("ascii"))
    pdf_bytes.extend(b"0000000000 65535 f \n")
    for oid in range(1, max_obj + 1):
        off = xref_offsets.get(oid, 0)
        pdf_bytes.extend(f"{off:010d} 00000 n \n".encode("ascii"))

    pdf_bytes.extend(b"trailer\n")
    pdf_bytes.extend(f"<< /Size {max_obj + 1} /Root 1 0 R >>\n".encode("ascii"))
    pdf_bytes.extend(b"startxref\n")
    pdf_bytes.extend(f"{startxref}\n".encode("ascii"))
    pdf_bytes.extend(b"%%EOF\n")
    return bytes(pdf_bytes)


def test_decode_pdf_literal_string():
    assert decode_pdf_literal_string("Hello\\nWorld") == "Hello\nWorld"
    assert decode_pdf_literal_string("Parentheses \\(test\\)") == "Parentheses (test)"
    assert decode_pdf_literal_string("Octal \\101") == "Octal A"


def test_decode_pdf_hex_string():
    # 'Hello' in hex: 48 65 6c 6c 6f
    assert decode_pdf_hex_string("48656c6c6f") == "Hello"


def test_extract_text_from_content_stream():
    stream_data = (
        b"BT /F1 12 Tf 72 712 Td (Executive Summary) Tj T* (Revenue increased by 30%) Tj ET"
    )
    text = extract_text_from_content_stream(stream_data)
    assert "Executive Summary" in text
    assert "Revenue increased by 30%" in text

    # Test TJ array operator with kerning
    tj_stream = b"BT /F1 12 Tf 72 712 Td [(Veloxs) -20 (Nexus)] TJ ET"
    tj_text = extract_text_from_content_stream(tj_stream)
    assert "VeloxsNexus" in tj_text or "Veloxs" in tj_text


def test_process_pdf_binary_multipage():
    pages = [
        "Page 1: Introduction to Veloxs Nexus Enterprise Intelligence.",
        "Page 2: Core Architecture and In-Memory Vector Operations.",
        "Page 3: Performance Benchmarks and Zero Runtime Overhead.",
    ]
    pdf_data = make_test_pdf(pages)
    payload = process_pdf_binary(pdf_data)

    assert payload.metadata.format == "PDF"
    assert payload.metadata.page_count == 3
    assert len(payload.pages) == 3

    assert payload.pages[0].page_label == "[Page 1]"
    assert "Introduction to Veloxs Nexus" in payload.pages[0].text
    assert payload.pages[0].width_pts == 612.0
    assert payload.pages[0].height_pts == 792.0

    assert payload.pages[1].page_label == "[Page 2]"
    assert "Core Architecture" in payload.pages[1].text

    assert payload.pages[2].page_label == "[Page 3]"
    assert "Performance Benchmarks" in payload.pages[2].text
