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

import io
import zipfile

import pytest

from nexus_processing.office import (
    process_presentation_binary,
    process_spreadsheet_binary,
)


def make_test_xlsx() -> bytes:
    """Generates a valid minimal XLSX archive containing shared strings, numbers, and booleans."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Finance" sheetId="1" r:id="rId1"/>
    <sheet name="Engineering" sheetId="2" r:id="rId2"/>
  </sheets>
</workbook>""",
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
                Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
                Target="worksheets/sheet2.xml"/>
</Relationships>""",
        )
        zf.writestr(
            "xl/sharedStrings.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="4" uniqueCount="4">
  <si><t>Department</t></si>
  <si><t>Budget</t></si>
  <si><t>Approved</t></si>
  <si><t>Operations</t></si>
</sst>""",
        )
        # Sheet 1: Finance
        zf.writestr(
            "xl/worksheets/sheet1.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1">
      <c r="A1" t="s"><v>0</v></c>
      <c r="B1" t="s"><v>1</v></c>
      <c r="C1" t="s"><v>2</v></c>
    </row>
    <row r="2">
      <c r="A2" t="s"><v>3</v></c>
      <c r="B2"><v>150000.50</v></c>
      <c r="C2" t="b"><v>1</v></c>
    </row>
  </sheetData>
</worksheet>""",
        )
        # Sheet 2: Engineering (with inline string)
        zf.writestr(
            "xl/worksheets/sheet2.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1">
      <c r="A1" t="inlineStr"><is><t>Team</t></is></c>
      <c r="B1" t="inlineStr"><is><t>Headcount</t></is></c>
    </row>
    <row r="2">
      <c r="A2" t="inlineStr"><is><t>Core Engine</t></is></c>
      <c r="B2"><v>24</v></c>
    </row>
  </sheetData>
</worksheet>""",
        )
    return buf.getvalue()


def make_test_pptx() -> bytes:
    """Generates a valid minimal PPTX archive with two slides and speaker notes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "ppt/presentation.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
                xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:sldIdLst>
    <p:sldId id="256" r:id="rId1"/>
    <p:sldId id="257" r:id="rId2"/>
  </p:sldIdLst>
</p:presentation>""",
        )
        zf.writestr(
            "ppt/_rels/presentation.xml.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"
                Target="slides/slide1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"
                Target="slides/slide2.xml"/>
</Relationships>""",
        )
        # Slide 1: Architecture Overview with notes
        zf.writestr(
            "ppt/slides/slide1.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:sp>
        <p:nvSpPr><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr>
        <p:txBody><a:p><a:r><a:t>Nexus Architecture Overview</a:t></a:r></a:p></p:txBody>
      </p:sp>
      <p:sp>
        <p:txBody>
          <a:p><a:r><a:t>Decoupled layered architecture with pure Python engines.</a:t></a:r></a:p>
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
          <a:p>
            <a:r><a:t>Emphasize zero-dependency footprint and 3072D unified vectors.</a:t></a:r>
          </a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:notes>""",
        )
        # Slide 2: Benchmark Results (no notes)
        zf.writestr(
            "ppt/slides/slide2.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:sp>
        <p:nvSpPr><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr>
        <p:txBody><a:p><a:r><a:t>Benchmark Performance</a:t></a:r></a:p></p:txBody>
      </p:sp>
      <p:sp>
        <p:txBody>
          <a:p><a:r><a:t>Throughput exceeds 10,000 documents per minute.</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:sld>""",
        )
    return buf.getvalue()


def test_process_spreadsheet_validation():
    """Validates error handling for empty or malformed spreadsheet data."""
    with pytest.raises(ValueError, match="Cannot process empty spreadsheet bytes"):
        process_spreadsheet_binary(b"")

    with pytest.raises(ValueError, match="Corrupted or invalid XLSX archive"):
        process_spreadsheet_binary(b"NOT_A_ZIP_ARCHIVE")


def test_process_spreadsheet_success():
    """Validates full spreadsheet parsing, multi-sheet handling, and narrative row generation."""
    raw = make_test_xlsx()
    payload = process_spreadsheet_binary(raw, filename="test_book.xlsx")

    assert payload.metadata.format == "xlsx"
    assert payload.metadata.total_sheets == 2
    assert payload.metadata.sheet_names == ["Finance", "Engineering"]
    assert payload.metadata.total_rows == 4
    assert payload.metadata.total_cells >= 7

    # Sheet 1: Finance
    sheet1 = payload.sheets[0]
    assert sheet1.sheet_name == "Finance"
    assert sheet1.headers == ["Department", "Budget", "Approved"]
    assert len(sheet1.rows) == 1
    row1 = sheet1.rows[0]
    assert row1.row_index == 2
    assert row1.data["Department"] == "Operations"
    assert row1.data["Budget"] == 150000.5
    assert row1.data["Approved"] == "TRUE"
    assert "[Workbook: test_book.xlsx | Sheet: Finance | Row 2]" in row1.narrative_text

    # Sheet 2: Engineering
    sheet2 = payload.sheets[1]
    assert sheet2.sheet_name == "Engineering"
    assert sheet2.headers == ["Team", "Headcount"]
    assert len(sheet2.rows) == 1
    row2 = sheet2.rows[0]
    assert row2.data["Team"] == "Core Engine"
    assert row2.data["Headcount"] == 24


def test_process_presentation_validation():
    """Validates error handling for empty or malformed presentation data."""
    with pytest.raises(ValueError, match="Cannot process empty presentation bytes"):
        process_presentation_binary(b"")

    with pytest.raises(ValueError, match="Corrupted or invalid PPTX archive"):
        process_presentation_binary(b"NOT_A_ZIP_ARCHIVE")


def test_process_presentation_success():
    """Validates slide graph extraction, speaker notes linking, and narrative formatting."""
    raw = make_test_pptx()
    payload = process_presentation_binary(raw, filename="deck.pptx")

    assert payload.metadata.format == "pptx"
    assert payload.metadata.total_slides == 2
    assert payload.metadata.slide_titles == [
        "Nexus Architecture Overview",
        "Benchmark Performance",
    ]
    assert len(payload.slides) == 2

    # Slide 1 (has speaker notes)
    s1 = payload.slides[0]
    assert s1.slide_number == 1
    assert s1.title == "Nexus Architecture Overview"
    assert "Decoupled layered architecture" in s1.body_text
    assert "Emphasize zero-dependency footprint" in s1.speaker_notes
    assert "[Presentation: deck.pptx | Slide 1: Nexus Architecture Overview]" in s1.narrative_text
    assert "Speaker Notes: Emphasize zero-dependency footprint" in s1.narrative_text

    # Slide 2 (no speaker notes)
    s2 = payload.slides[1]
    assert s2.slide_number == 2
    assert s2.title == "Benchmark Performance"
    assert "Throughput exceeds 10,000" in s2.body_text
    assert s2.speaker_notes == ""
