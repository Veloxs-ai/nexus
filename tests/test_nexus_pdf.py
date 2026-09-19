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
import zlib

from nexus.client import NexusClient


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

        page_dict = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content_id} 0 R >>"
        )
        objects[page_id] = page_dict.encode("ascii")

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


def test_nexus_client_process_pdf():
    client = NexusClient(in_memory_only=True)

    pages = [
        "Executive Summary: Contact CEO at alice@corp.com or card 4532-0150-1234-5678 for billing.",
        "Engineering Overview: Nexus runs in-memory 3072D vector projections with zero bloat.",
    ]

    pdf_bytes = make_test_pdf(pages)

    doc = client.process_pdf(
        pdf_id="pdf_annual_report",
        name="annual_report.pdf",
        pdf_bytes=pdf_bytes,
        metadata={"division": "finance"},
    )

    assert doc.document_id == "pdf_annual_report"
    assert doc.file_type == "pdf"
    assert len(doc.chunks) == 2

    # Check Page 1 PII masking
    chunk_0 = doc.chunks[0]
    assert chunk_0.chunk_id == "pdf_annual_report:0"
    assert "[Page 1]" in chunk_0.text
    assert "[EMAIL]" in chunk_0.text
    assert chunk_0.metadata["page_number"] == 1
    assert chunk_0.metadata["width_pts"] == 612.0
    assert chunk_0.metadata["is_pdf"] is True
    assert len(chunk_0.embedding) == 3072

    # Verify IEEE 754 L2 unit normalization
    norm = math.sqrt(sum(x * x for x in chunk_0.embedding))
    assert abs(norm - 1.0) < 1e-7

    # Check Page 2
    chunk_1 = doc.chunks[1]
    assert chunk_1.chunk_id == "pdf_annual_report:1"
    assert "[Page 2]" in chunk_1.text
    assert "Engineering Overview" in chunk_1.text

    # Verify 5-stage telemetry trace
    assert len(doc.execution_trace) == 5
    for idx, trace in enumerate(doc.execution_trace, start=1):
        assert trace.step_number == idx
        assert trace.status == "completed"
        assert trace.duration_ms >= 0.0

    assert doc.execution_trace[0].stage_name == "PDF Header & Object Graph Parsing"
    assert doc.execution_trace[1].stage_name == "FlateDecode Stream Decompression (zlib)"
    assert doc.execution_trace[2].stage_name == "PostScript Text Operator Decoding (BT/ET/Tj/TJ)"
    assert doc.execution_trace[3].stage_name == "Safety Guardrails & PII Sanitization"
    assert doc.execution_trace[4].stage_name == "Page-Grounded 3072D Vector Projection"

    # Verify indexing and retrieval
    client.index_document(doc, collection="executive_docs")
    results = client.search("Engineering Overview 3072D", limit=5)
    assert len(results) >= 1
    assert any("pdf_annual_report:1" in r.id for r in results)


def test_nexus_client_process_document_pdf_routing():
    client = NexusClient(in_memory_only=True)
    pdf_bytes = make_test_pdf(["Page 1: Seamless routing test content."])

    doc = client.process_document(
        document_id="pdf_routed_01",
        name="specification.pdf",
        text=pdf_bytes,
        file_type="pdf",
    )

    assert doc.document_id == "pdf_routed_01"
    assert doc.file_type == "pdf"
    assert len(doc.chunks) == 1
    assert "[Page 1]" in doc.chunks[0].text
    assert len(doc.chunks[0].embedding) == 3072
    assert len(doc.execution_trace) == 5
