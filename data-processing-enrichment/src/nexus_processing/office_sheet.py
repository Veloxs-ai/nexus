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

"""Spreadsheet payload model, row narratives and legacy ``.xls`` (BIFF) workbooks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .spreadsheet_values import xls_cell_value


@dataclass
class SpreadsheetRowChunk:
    """Grounded tabular chunk representing a row or row group within a sheet."""

    sheet_name: str
    row_index: int
    data: dict[str, Any]
    narrative_text: str


@dataclass
class SheetData:
    """Processed sheet data containing tabular rows and metadata."""

    sheet_name: str
    total_rows: int
    total_columns: int
    headers: list[str]
    rows: list[SpreadsheetRowChunk] = field(default_factory=list)
    context: list[str] = field(default_factory=list)  # title rows above the header


@dataclass
class SpreadsheetMetadata:
    """High-level metadata for an Excel spreadsheet workbook."""

    filename: str
    format: str  # "xlsx"
    sheet_names: list[str]
    total_sheets: int
    total_rows: int
    total_cells: int
    file_size_bytes: int


@dataclass
class SpreadsheetPayload:
    """Comprehensive processed spreadsheet workbook payload."""

    metadata: SpreadsheetMetadata
    sheets: list[SheetData] = field(default_factory=list)
    all_chunks: list[SpreadsheetRowChunk] = field(default_factory=list)


def _display(value: Any) -> str:
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return str(value)


def spreadsheet_row_text(
    filename: str, sheet_name: str, row_index: int, data: dict[str, Any]
) -> str:
    """Row narrative: ``[Workbook: f | Sheet: s | Row n] Col: value | ...``."""
    return f"[Workbook: {filename} | Sheet: {sheet_name} | Row {row_index}] " + " | ".join(
        f"{header}: {_display(value)}" for header, value in data.items()
    )


def _is_legacy_xls(raw_bytes: bytes, filename: str) -> bool:
    """Detects whether bytes or filename denote a legacy Microsoft Excel (.xls / BIFF) file."""
    if raw_bytes.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return True
    lower = filename.lower()
    return lower.endswith(".xls") and not lower.endswith(".xlsx")


def _process_legacy_xls_fallback(raw_bytes: bytes, filename: str) -> SpreadsheetPayload:
    """Zero-dependency fallback for legacy .xls files when xlrd is not installed.

    Extracts textual and tabular sequences from OLE2 / BIFF binary streams,
    providing structured spreadsheet chunks for downstream indexing.
    """
    ascii_matches = re.findall(rb"[\x20-\x7E]{3,}", raw_bytes)
    utf16_matches = re.findall(rb"(?:[\x20-\x7E]\x00){2,}", raw_bytes)

    extracted_lines: list[str] = []
    ignored_patterns = {
        b"Root Entry",
        b"Workbook",
        b"Book",
        b"\x05DocumentSummaryInformation",
        b"\x05SummaryInformation",
        b"CompObj",
    }

    for m in ascii_matches:
        if m not in ignored_patterns:
            try:
                decoded = m.decode("latin-1").strip()
                if len(decoded) >= 2 and not decoded.startswith("_"):
                    extracted_lines.append(decoded)
            except Exception:
                pass

    for m in utf16_matches:
        try:
            decoded = m.decode("utf-16le").strip()
            if len(decoded) >= 2 and decoded not in extracted_lines and not decoded.startswith("_"):
                extracted_lines.append(decoded)
        except Exception:
            pass

    row_chunks: list[SpreadsheetRowChunk] = []
    chunk_size = 5
    sheet_name = "Sheet1"
    headers = [f"Col_{i + 1}" for i in range(chunk_size)]

    for idx, i in enumerate(range(0, len(extracted_lines), chunk_size), 1):
        row_slice = extracted_lines[i : i + chunk_size]
        row_dict = {f"Col_{j + 1}": val for j, val in enumerate(row_slice)}
        narrative = f"[Workbook: {filename} | Sheet: {sheet_name} | Row {idx}] " + " | ".join(
            f"Col_{j + 1}: {val}" for j, val in enumerate(row_slice)
        )
        row_chunks.append(
            SpreadsheetRowChunk(
                sheet_name=sheet_name,
                row_index=idx,
                data=row_dict,
                narrative_text=narrative,
            )
        )

    meta = SpreadsheetMetadata(
        filename=filename,
        format="xls",
        sheet_names=[sheet_name],
        total_sheets=1,
        total_rows=len(row_chunks),
        total_cells=len(extracted_lines),
        file_size_bytes=len(raw_bytes),
    )
    sheet_data = SheetData(
        sheet_name=sheet_name,
        total_rows=len(row_chunks),
        total_columns=chunk_size,
        headers=headers,
        rows=row_chunks,
    )
    return SpreadsheetPayload(
        metadata=meta,
        sheets=[sheet_data],
        all_chunks=row_chunks,
    )


def _process_legacy_xls(raw_bytes: bytes, filename: str) -> SpreadsheetPayload:
    """Parses legacy Microsoft Excel (.xls / BIFF8) workbooks.

    Leverages xlrd if available in the runtime environment (with full cell type
    and formula support), falling back gracefully to pure-Python OLE2 stream extraction.
    """
    try:
        import xlrd

        wb = xlrd.open_workbook(file_contents=raw_bytes)
        processed_sheets: list[SheetData] = []
        all_chunks: list[SpreadsheetRowChunk] = []
        total_populated_cells = 0
        total_rows_all_sheets = 0

        for s_idx in range(wb.nsheets):
            sheet = wb.sheet_by_index(s_idx)
            sheet_name = sheet.name or f"Sheet{s_idx + 1}"
            num_rows = sheet.nrows
            num_cols = sheet.ncols
            if num_rows == 0:
                continue

            headers: list[str] = []
            for c in range(num_cols):
                val = xls_cell_value(xlrd, sheet, 0, c, wb.datemode)
                headers.append(str(val).strip() if val != "" else f"col_{c}")

            sheet_row_chunks: list[SpreadsheetRowChunk] = []
            for r in range(1, num_rows):
                row_dict: dict[str, Any] = {}
                for c in range(num_cols):
                    val = xls_cell_value(xlrd, sheet, r, c, wb.datemode)
                    if val != "" and val is not None:
                        total_populated_cells += 1
                        header = headers[c] if c < len(headers) else f"col_{c}"
                        row_dict[header] = val

                if not row_dict:
                    continue

                row_narrative = spreadsheet_row_text(filename, sheet_name, r + 1, row_dict)
                chunk = SpreadsheetRowChunk(
                    sheet_name=sheet_name,
                    row_index=r + 1,
                    data=row_dict,
                    narrative_text=row_narrative,
                )
                sheet_row_chunks.append(chunk)
                all_chunks.append(chunk)

            total_rows_all_sheets += len(sheet_row_chunks)
            processed_sheets.append(
                SheetData(
                    sheet_name=sheet_name,
                    total_rows=num_rows,
                    total_columns=num_cols,
                    headers=headers,
                    rows=sheet_row_chunks,
                )
            )

        meta = SpreadsheetMetadata(
            filename=filename,
            format="xls",
            sheet_names=[s.sheet_name for s in processed_sheets],
            total_sheets=len(processed_sheets),
            total_rows=total_rows_all_sheets,
            total_cells=total_populated_cells,
            file_size_bytes=len(raw_bytes),
        )
        return SpreadsheetPayload(
            metadata=meta,
            sheets=processed_sheets,
            all_chunks=all_chunks,
        )
    except ImportError:
        return _process_legacy_xls_fallback(raw_bytes, filename)
    except Exception:
        return _process_legacy_xls_fallback(raw_bytes, filename)
