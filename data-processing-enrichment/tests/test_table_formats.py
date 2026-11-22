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

"""CSV header detection and exact numbers, streaming XLSX, DOCX runs/cells/headings."""

from __future__ import annotations

import io
import zipfile
from xml.sax.saxutils import escape

from nexus_processing.csv_table import parse_csv_table
from nexus_processing.office import process_spreadsheet_binary, process_word_binary

_SML = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
_W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, body in files.items():
            z.writestr(name, body)
    return buf.getvalue()


def _xlsx(rows_xml: str, strings: list[str] | None = None) -> bytes:
    files = {
        "[Content_Types].xml": "<Types/>",
        "xl/worksheets/sheet1.xml": (
            f"<worksheet {_SML}><sheetData>{rows_xml}</sheetData></worksheet>"
        ),
    }
    if strings is not None:
        files["xl/sharedStrings.xml"] = f"<sst {_SML}>" + "".join(strings) + "</sst>"
    return _zip(files)


def _row(r: int, *cells: str) -> str:
    cols = "ABCDEFGH"
    body = "".join(
        f'<c r="{cols[i]}{r}" t="inlineStr"><is><t>{escape(v)}</t></is></c>'
        if not v.isdigit()
        else f'<c r="{cols[i]}{r}"><v>{v}</v></c>'
        for i, v in enumerate(cells)
        if v
    )
    return f'<row r="{r}">{body}</row>'


def _docx(body: str, styles: str | None = None, extra: dict[str, str] | None = None) -> bytes:
    files = {
        "[Content_Types].xml": "<Types/>",
        "word/document.xml": f"<w:document {_W}><w:body>{body}</w:body></w:document>",
    }
    if styles:
        files["word/styles.xml"] = f"<w:styles {_W}>{styles}</w:styles>"
    files.update(extra or {})
    return _zip(files)


# ---- CSV --------------------------------------------------------------------------------
def test_csv_title_with_delimiter_is_not_the_header():
    table = parse_csv_table('Report, Q3\n\nid,desc\n1,"a, b"\n2,c\n')
    assert table.columns == ["id", "desc"]
    assert table.rows == [{"id": "1", "desc": "a, b"}, {"id": "2", "desc": "c"}]


def test_csv_title_wider_header_and_no_title_unchanged():
    titled = parse_csv_table("Customer export, 2026-11-01\nid,name,city\n1,Ann,Rome\n")
    assert titled.columns == ["id", "name", "city"]
    plain = parse_csv_table("id,name,city\n1,Ann,Rome\n")
    assert plain.columns == ["id", "name", "city"] and plain.rows == titled.rows


def test_csv_header_above_ragged_rows_is_kept():
    table = parse_csv_table("a,b,c\n1,2,3,4\n5,6,7,8\n")
    assert table.columns == ["a", "b", "c"]
    assert table.rows[0] == {"a": "1", "b": "2", "c": "3", "_extra": "4"}


def test_csv_blank_line_after_text_header_is_not_a_title():
    table = parse_csv_table("a,b\n\n1,2\n3,4\n")
    assert table.columns == ["a", "b"] and len(table.rows) == 2


def test_csv_big_integers_stay_exact():
    table = parse_csv_table("name,qty\nx,9007199254740993\ny,12345678901234567890\nz,1,234\n")
    assert [r["qty"] for r in table.typed_rows[:2]] == [9007199254740993, 12345678901234567890]


def test_csv_blank_line_inside_quoted_cell_is_kept_and_crlf_works():
    table = parse_csv_table('id,notes\r\n1,"Line one\r\n\r\nLine three"\r\n2,ok\r\n')
    assert table.rows[0]["notes"] == "Line one\n\nLine three"
    assert table.rows[1] == {"id": "2", "notes": "ok"}


def test_csv_duplicate_and_blank_header_names_match_dictreader():
    table = parse_csv_table("a,a,,b\n1,2,3,4\n")
    assert table.columns == ["a", "a", "b"]
    assert table.rows == [{"a": "2", "b": "4"}]


# ---- XLSX -------------------------------------------------------------------------------
def test_xlsx_duplicate_headers_keep_every_column():
    data = _xlsx(_row(1, "Region", "Amount", "Amount") + _row(2, "North", "10", "20"))
    sheet = process_spreadsheet_binary(data, "s.xlsx", auto_extract=False).sheets[0]
    assert sheet.headers == ["Region", "Amount", "Amount_2"]
    assert sheet.rows[0].data == {"Region": "North", "Amount": 10, "Amount_2": 20}


def test_xlsx_title_row_becomes_context_not_header():
    rows = _row(1, "Quarterly sales export") + _row(2, "Region", "Amount", "Code")
    rows += _row(3, "North", "10", "C-1") + _row(4, "South", "20", "C-2")
    payload = process_spreadsheet_binary(_xlsx(rows), "s.xlsx", auto_extract=False)
    sheet = payload.sheets[0]
    assert sheet.headers == ["Region", "Amount", "Code"]
    assert sheet.context == ["Quarterly sales export"]
    assert [r.row_index for r in sheet.rows] == [3, 4]
    title = payload.all_chunks[0]
    assert title.data == {"title": "Quarterly sales export"} and "Title" in title.narrative_text
    assert sheet.total_rows == 4 and payload.metadata.total_cells == 1 + 3 + 3 + 3


def test_xlsx_full_header_with_numbers_is_never_skipped():
    rows = (
        _row(1, "Region", "2025", "2026") + _row(2, "North", "1", "2") + _row(3, "South", "3", "4")
    )
    sheet = process_spreadsheet_binary(_xlsx(rows), "s.xlsx", auto_extract=False).sheets[0]
    assert sheet.headers == ["Region", "2025", "2026"] and len(sheet.rows) == 2


def test_xlsx_stray_far_cell_does_not_create_thousands_of_columns():
    rows = _row(1, "a", "b") + _row(2, "1", "2")
    rows += '<row r="3"><c r="XFD3" t="inlineStr"><is><t>stray</t></is></c></row>'
    sheet = process_spreadsheet_binary(_xlsx(rows), "s.xlsx", auto_extract=False).sheets[0]
    assert sheet.headers == ["a", "b", "Column_16384"]
    assert sheet.rows[-1].data == {"Column_16384": "stray"}


def test_xlsx_shared_strings_skip_phonetic_runs_and_rows_without_r():
    strings = [
        "<si><t>Plain</t></si>",
        "<si><r><t>Ri</t></r><r><t>ch</t></r></si>",
        '<si><t>東京</t><rPh sb="0" eb="2"><t>トウキョウ</t></rPh></si>',
    ]
    rows = (
        '<row><c t="s"><v>0</v></c><c t="s"><v>1</v></c></row>'
        '<row><c t="s"><v>2</v></c><c t="b"><v>1</v></c></row>'
    )
    sheet = process_spreadsheet_binary(_xlsx(rows, strings), "s.xlsx", auto_extract=False).sheets[0]
    assert sheet.headers == ["Plain", "Rich"]
    assert sheet.rows[0].data == {"Plain": "東京", "Rich": "TRUE"} and sheet.rows[0].row_index == 2


def test_xlsx_single_row_sheet_is_data():
    sheet = process_spreadsheet_binary(
        _xlsx(_row(1, "only", "row")), "s.xlsx", auto_extract=False
    ).sheets[0]
    assert sheet.total_rows == 1 and sheet.rows[0].data == {"only": "only", "row": "row"}


# ---- DOCX -------------------------------------------------------------------------------
def test_docx_tabs_and_breaks_separate_words_but_tab_stops_do_not():
    body = (
        '<w:p><w:pPr><w:tabs><w:tab w:val="left" w:pos="720"/></w:tabs></w:pPr>'
        "<w:r><w:t>Employee:</w:t></w:r><w:r><w:tab/><w:t>Kim</w:t></w:r>"
        "<w:r><w:br/><w:t>Grade</w:t><w:noBreakHyphen/><w:t>2</w:t></w:r></w:p>"
    )
    payload = process_word_binary(_docx(body), "d.docx", auto_extract=False)
    assert payload.chunks[0].text == "Employee:\tKim\nGrade-2"


def test_docx_cell_paragraphs_spans_and_pipes():
    cell = (
        "<w:tc><w:p><w:r><w:t>top</w:t></w:r></w:p><w:p><w:r><w:t>bottom</w:t></w:r></w:p></w:tc>"
    )
    wide = (
        '<w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr><w:p><w:r><w:t>a|b</w:t></w:r></w:p></w:tc>'
    )
    last = "<w:tc><w:p><w:r><w:t>z</w:t></w:r></w:p></w:tc>"
    body = f"<w:tbl><w:tr>{cell}{last}{last}</w:tr><w:tr>{wide}{last}</w:tr></w:tbl>"
    table = process_word_binary(_docx(body), "d.docx", auto_extract=False).chunks[0].text
    assert table.splitlines()[0] == "| top bottom | z | z |"
    assert table.splitlines()[2] == "| a\\|b |  | z |"


def test_docx_localised_heading_style_and_outline_level():
    styles = (
        '<w:style w:type="paragraph" w:styleId="berschrift1"><w:name w:val="heading 1"/></w:style>'
        '<w:style w:type="paragraph" w:styleId="Custom"><w:name w:val="Mine"/>'
        '<w:pPr><w:outlineLvl w:val="1"/></w:pPr></w:style>'
    )
    body = (
        '<w:p><w:pPr><w:pStyle w:val="berschrift1"/></w:pPr><w:r><w:t>Einleitung</w:t></w:r></w:p>'
        '<w:p><w:pPr><w:pStyle w:val="Custom"/></w:pPr><w:r><w:t>Teil</w:t></w:r></w:p>'
        '<w:p><w:pPr><w:outlineLvl w:val="2"/></w:pPr><w:r><w:t>Direct</w:t></w:r></w:p>'
        "<w:p><w:r><w:t>Body text.</w:t></w:r></w:p>"
    )
    chunks = process_word_binary(_docx(body, styles), "d.docx", auto_extract=False).chunks
    assert [(c.item_type, c.heading_level) for c in chunks[:3]] == [
        ("heading", 1),
        ("heading", 2),
        ("heading", 3),
    ]
    assert chunks[3].section_title == "Einleitung > Teil > Direct"


def test_docx_header_runs_join_without_false_spaces():
    header = (
        f"<w:hdr {_W}><w:p><w:r><w:t>Conf</w:t></w:r><w:r><w:t>idential</w:t></w:r></w:p></w:hdr>"
    )
    data = _docx("<w:p><w:r><w:t>x</w:t></w:r></w:p>", extra={"word/header1.xml": header})
    meta = process_word_binary(data, "d.docx", auto_extract=False).metadata
    assert meta.header_texts == ["Confidential"]
