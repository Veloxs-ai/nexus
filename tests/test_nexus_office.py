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

import io
import math
import zipfile

from nexus.client import NexusClient


def make_test_xlsx() -> bytes:
    """Generates a valid minimal XLSX archive containing shared strings, numbers, and PII."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Employees" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>""",
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
                Target="worksheets/sheet1.xml"/>
</Relationships>""",
        )
        zf.writestr(
            "xl/sharedStrings.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="4" uniqueCount="4">
  <si><t>Full Name</t></si>
  <si><t>Email</t></si>
  <si><t>Alice Smith</t></si>
  <si><t>alice.smith@example.com</t></si>
</sst>""",
        )
        zf.writestr(
            "xl/worksheets/sheet1.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1">
      <c r="A1" t="s"><v>0</v></c>
      <c r="B1" t="s"><v>1</v></c>
    </row>
    <row r="2">
      <c r="A2" t="s"><v>2</v></c>
      <c r="B2" t="s"><v>3</v></c>
    </row>
  </sheetData>
</worksheet>""",
        )
    return buf.getvalue()


def make_test_pptx() -> bytes:
    """Generates a valid minimal PPTX archive with a slide and speaker notes containing PII."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "ppt/presentation.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
                xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:sldIdLst>
    <p:sldId id="256" r:id="rId1"/>
  </p:sldIdLst>
</p:presentation>""",
        )
        zf.writestr(
            "ppt/_rels/presentation.xml.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"
                Target="slides/slide1.xml"/>
</Relationships>""",
        )
        zf.writestr(
            "ppt/slides/slide1.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:sp>
        <p:nvSpPr><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr>
        <p:txBody><a:p><a:r><a:t>Executive Roadmap 2026</a:t></a:r></a:p></p:txBody>
      </p:sp>
      <p:sp>
        <p:txBody>
          <a:p>
            <a:r><a:t>Contact lead: lead.architect@example.com for architecture reviews.</a:t></a:r>
          </a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:sld>""",
        )
        zf.writestr(
            "ppt/slides/_rels/slide1.xml.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdNotes1"
                Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide"
                Target="../notesSlides/notesSlide1.xml"/>
</Relationships>""",
        )
        zf.writestr(
            "ppt/notesSlides/notesSlide1.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:notes xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
         xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:sp>
        <p:nvSpPr><p:nvPr><p:ph type="body"/></p:nvPr></p:nvSpPr>
        <p:txBody>
          <a:p><a:r><a:t>Private notes: Verify funding runway before Q4.</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:notes>""",
        )
    return buf.getvalue()


def test_nexus_client_process_spreadsheet():
    """Validates NexusClient.process_spreadsheet execution traces and 3072D vector projections."""
    client = NexusClient()
    raw = make_test_xlsx()

    doc = client.process_spreadsheet(
        spreadsheet_id="doc_sheet_1",
        name="staff.xlsx",
        spreadsheet_bytes=raw,
        metadata={"department": "HR"},
        enable_guardrails=True,
    )

    assert doc.document_id == "doc_sheet_1"
    assert doc.file_type == "spreadsheet"
    assert doc.metadata["total_sheets"] == 1
    assert doc.metadata["department"] == "HR"
    assert len(doc.chunks) == 1

    # 5-stage trace validation
    assert len(doc.execution_trace) == 5
    stage_names = [t.stage_name for t in doc.execution_trace]
    assert stage_names == [
        "OPC Archive Decompression & Workbook Discovery",
        "Shared Strings & XML Schema Resolution",
        "Worksheet Tabular Framing & Cell Parsing",
        "Safety Guardrails & PII Sanitization",
        "Sheet-Grounded 3072D Vector Projection",
    ]
    for t in doc.execution_trace:
        assert t.status == "completed"
        assert t.duration_ms >= 0.0

    # Chunk and 3072D vector validation
    chunk = doc.chunks[0]
    assert chunk.metadata["sheet_name"] == "Employees"
    assert chunk.metadata["department"] == "HR"
    assert chunk.embedding is not None
    assert len(chunk.embedding) == 3072
    l2_norm = math.sqrt(sum(x * x for x in chunk.embedding))
    assert math.isclose(l2_norm, 1.0, rel_tol=1e-5)

    # PII sanitization check (email masked)
    assert "alice.smith@example.com" not in chunk.text
    assert "[EMAIL]" in chunk.text


def test_nexus_client_process_presentation():
    """Validates NexusClient.process_presentation slide graph, speaker notes,
    and 3072D vector projection.
    """
    client = NexusClient()
    raw = make_test_pptx()

    doc = client.process_presentation(
        presentation_id="doc_pres_1",
        name="strategy.pptx",
        presentation_bytes=raw,
        metadata={"confidential": True},
        enable_guardrails=True,
    )

    assert doc.document_id == "doc_pres_1"
    assert doc.file_type == "presentation"
    assert doc.metadata["total_slides"] == 1
    assert doc.metadata["confidential"] is True
    assert len(doc.chunks) == 1

    # 5-stage trace validation
    assert len(doc.execution_trace) == 5
    stage_names = [t.stage_name for t in doc.execution_trace]
    assert stage_names == [
        "OPC Archive Decompression & Slide Graph Discovery",
        "Slide XML & DrawingML Text Extraction",
        "Speaker Notes & Hierarchy Resolution",
        "Safety Guardrails & PII Sanitization",
        "Slide-Grounded 3072D Vector Projection",
    ]
    for t in doc.execution_trace:
        assert t.status == "completed"

    chunk = doc.chunks[0]
    assert chunk.metadata["title"] == "Executive Roadmap 2026"
    assert chunk.metadata["has_speaker_notes"] is True
    assert "Private notes: Verify funding runway" in chunk.text
    assert "[EMAIL]" in chunk.text

    # 3072D vector norm verification
    assert len(chunk.embedding) == 3072
    l2_norm = math.sqrt(sum(x * x for x in chunk.embedding))
    assert math.isclose(l2_norm, 1.0, rel_tol=1e-5)


def test_nexus_client_process_document_office_routing():
    """Validates auto-routing in NexusClient.process_document for xlsx and pptx formats."""
    client = NexusClient()

    xlsx_bytes = make_test_xlsx()
    doc_xlsx = client.process_document(
        document_id="auto_xlsx",
        text=xlsx_bytes,
        name="budget.xlsx",
    )
    assert doc_xlsx.file_type == "spreadsheet"
    assert doc_xlsx.metadata["total_sheets"] == 1
    assert len(doc_xlsx.chunks) == 1

    pptx_bytes = make_test_pptx()
    doc_pptx = client.process_document(
        document_id="auto_pptx",
        text=pptx_bytes,
        name="deck.pptx",
    )
    assert doc_pptx.file_type == "presentation"
    assert doc_pptx.metadata["total_slides"] == 1
    assert len(doc_pptx.chunks) == 1
