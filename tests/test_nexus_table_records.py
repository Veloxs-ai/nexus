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

"""Typed, column-masked row records for uploads (XLSX, CSV) and database tables."""

from __future__ import annotations

import io
import zipfile

import pytest

from nexus import NexusClient

try:
    from nexus.processing.spreadsheet_values import classify_format, excel_serial_to_iso
except (ImportError, ModuleNotFoundError):
    from nexus_processing.spreadsheet_values import classify_format, excel_serial_to_iso

NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
STYLES = (
    f'<styleSheet {NS}><numFmts count="1"><numFmt numFmtId="164" formatCode="yyyy-mm-dd hh:mm"/>'
    '</numFmts><cellXfs count="4"><xf numFmtId="0"/><xf numFmtId="14"/><xf numFmtId="164"/>'
    '<xf numFmtId="4"/></cellXfs></styleSheet>'
)


def _inline(ref: str, text: str) -> str:
    return f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>'


def _num(ref: str, value: str, style: int = 0) -> str:
    return f'<c r="{ref}" s="{style}"><v>{value}</v></c>'


def make_workbook(sheets: dict[str, list[str]], date1904: bool = False) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        entries = "".join(
            f'<sheet name="{name}" sheetId="{i + 1}" r:id="rId{i + 1}"/>'
            for i, name in enumerate(sheets)
        )
        pr = '<workbookPr date1904="1"/>' if date1904 else ""
        zf.writestr(
            "xl/workbook.xml",
            f'<workbook {NS} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">{pr}<sheets>{entries}</sheets></workbook>',
        )
        rels = "".join(
            f'<Relationship Id="rId{i + 1}" Type="worksheet" Target="worksheets/sheet{i + 1}.xml"/>'
            for i in range(len(sheets))
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>',
        )
        zf.writestr("xl/styles.xml", STYLES)
        for i, rows in enumerate(sheets.values()):
            zf.writestr(
                f"xl/worksheets/sheet{i + 1}.xml",
                f"<worksheet {NS}><sheetData>{''.join(rows)}</sheetData></worksheet>",
            )
    return buf.getvalue()


ORDERS = [
    '<row r="1">'
    + _inline("A1", "Order ID")
    + _inline("B1", "Ordered")
    + _inline("C1", "Shipped")
    + _inline("D1", "Amount")
    + _inline("E1", "Email")
    + "</row>",
    '<row r="2">'
    + _num("A2", "4155551234")
    + _num("B2", "45352", 1)
    + _num("C2", "45352.5", 2)
    + _num("D2", "1234.5", 3)
    + _inline("E2", "jane@example.com")
    + "</row>",
    '<row r="3">'
    + _num("A3", "4155551235")
    + _num("B3", "45383", 1)
    + _num("C3", "45383.25", 2)
    + _num("D3", "100", 3)
    + _inline("E3", "joe@example.com")
    + "</row>",
]
REGIONS = [
    '<row r="1">' + _inline("A1", "Region") + "</row>",
    '<row r="2">' + _inline("A2", "North") + "</row>",
]


def test_number_formats_mark_dates():
    assert classify_format("yyyy-mm-dd") == "date"
    assert classify_format("[$-409]mmmm d, yyyy") == "date"
    assert classify_format("h:mm AM/PM") == "time"
    assert classify_format("yyyy-mm-dd hh:mm") == "datetime"
    assert classify_format("#,##0.00") is None and classify_format('0 "days"') is None
    assert excel_serial_to_iso(45352) == "2024-03-01"
    assert excel_serial_to_iso(43890, "date", date1904=True) == "2024-03-01"


def test_xlsx_rows_become_typed_masked_records_with_iso_dates():
    client = NexusClient()
    doc = client.process_spreadsheet(
        "wb", "orders.xlsx", make_workbook({"Orders": ORDERS, "Regions": REGIONS})
    )
    orders = [c for c in doc.chunks if c.metadata.get("sheet") == "Orders"]
    records = [c.metadata["record"] for c in orders]
    assert records[0] == {
        "Order ID": 4155551234,
        "Ordered": "2024-03-01",
        "Shipped": "2024-03-01T12:00:00",
        "Amount": 1234.5,
        "Email": "[EMAIL]",
        "sheet": "Orders",
    }
    # exact count / sum / filter over the records
    assert len(records) == 2 and sum(r["Amount"] for r in records) == 1334.5
    assert [r["Order ID"] for r in records if r["Ordered"].startswith("2024-04")] == [4155551235]
    # text agrees with the record: dates readable, ids intact, PII masked
    assert "Ordered: 2024-03-01" in orders[0].text and "4155551234" in orders[0].text
    assert "jane@example.com" not in orders[0].text and "data" in orders[0].metadata
    assert "jane@example.com" not in str(orders[0].metadata)


def test_xlsx_1904_date_system():
    rows = [
        '<row r="1">' + _inline("A1", "Day") + "</row>",
        '<row r="2">' + _num("A2", "43890", 1) + "</row>",
    ]
    doc = NexusClient().process_spreadsheet(
        "wb", "mac.xlsx", make_workbook({"S": rows}, date1904=True)
    )
    assert doc.chunks[0].metadata["record"] == {"Day": "2024-03-01"}


CSV = (
    "Quarterly export\n"
    "order_id;zip;amount;email;placed\n"
    "4155551234;02139;1,234.50;jane@example.com;2024-03-01\n"
    "4155551235;10001;100;joe@example.com;2024-04-02\n"
    "4155551236;94105;65.5;;2024-04-03\n"
)


def test_csv_rows_become_typed_records():
    doc = NexusClient().process_document("c", "orders.csv", CSV)
    records = [r for c in doc.chunks for r in c.metadata["records"]]
    assert len(records) == 3
    assert sum(r["amount"] for r in records) == 1400.0
    assert records[0] == {
        "order_id": "4155551234",
        "zip": "02139",
        "amount": 1234.5,
        "email": "[EMAIL]",
        "placed": "2024-03-01",
    }
    assert records[2]["email"] is None
    assert doc.chunks[0].text.startswith("Columns: order_id, zip, amount, email, placed")
    assert "[Row ID: 1] order_id: 4155551234 | zip: 02139 | amount: 1,234.50" in doc.chunks[0].text
    assert doc.chunks[0].metadata["row_range"][0] == 1


def test_database_rows_carry_masked_records_with_exact_ids():
    rows = [
        {
            "id": 1,
            "order_id": "4155551234",
            "amount": 9876543210.5,
            "phone": "9876543210",
            "ts": 1700000000,
        },
        {
            "id": 2,
            "order_id": "4155551235",
            "amount": 12.0,
            "phone": "9876543211",
            "ts": 1700000100,
        },
    ]
    doc = NexusClient().process_mysql_table("orders", rows)
    assert [c.metadata["record"]["order_id"] for c in doc.chunks] == ["4155551234", "4155551235"]
    assert doc.chunks[0].metadata["record"]["phone"] == "[PHONE]"
    assert "order_id: 4155551234" in doc.chunks[0].text and "ts: 1700000000" in doc.chunks[0].text
    assert "amount: 9876543210.5" in doc.chunks[0].text and "9876543210 " not in doc.chunks[0].text


def test_split_row_keeps_its_record_on_the_first_part_only():
    rows = [{"id": 7, "body": "renewal " * 900}]
    doc = NexusClient().process_mysql_table("notes", rows)
    assert len(doc.chunks) > 1
    assert "record" in doc.chunks[0].metadata
    assert all("record" not in c.metadata for c in doc.chunks[1:])
    assert all(c.text.startswith("[Table: notes | PK: 7]") for c in doc.chunks)


def test_mongo_documents_carry_masked_records():
    docs = [{"_id": {"$oid": "65f0c1a2b3c4d5e6f7a8b9c0"}, "email": "a@x.io", "total": 10}]
    doc = NexusClient().process_mongo_collection("orders", docs)
    assert doc.chunks[0].metadata["record"] == {
        "_id": "65f0c1a2b3c4d5e6f7a8b9c0",
        "email": "[EMAIL]",
        "total": 10,
    }


@pytest.mark.parametrize("shallow", [True, False])
def test_records_are_raw_only_when_guardrails_are_off(shallow):
    doc = NexusClient().process_document("c", "o.csv", CSV, shallow_mode=shallow)
    email = doc.chunks[0].metadata["records"][0]["email"]
    assert email == ("jane@example.com" if shallow else "[EMAIL]")
