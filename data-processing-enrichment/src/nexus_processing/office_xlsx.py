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

"""Excel workbooks (``.xlsx``, and legacy ``.xls`` through ``office_sheet``) to row-group chunks."""

from __future__ import annotations

import io
import itertools
import xml.etree.ElementTree as ET
import zipfile
from typing import Any

from .office_sheet import (
    SheetData,
    SpreadsheetMetadata,
    SpreadsheetPayload,
    SpreadsheetRowChunk,
    _is_legacy_xls,
    _process_legacy_xls,
    spreadsheet_row_text,
)
from .office_zip import _extract_images_from_zip, _get_rel_id, _local_tag
from .spreadsheet_values import WorkbookStyles
from .xlsx_stream import iter_rows as xlsx_iter_rows
from .xlsx_stream import pick_header
from .xlsx_stream import shared_strings as xlsx_shared_strings


def process_spreadsheet_binary(
    raw_bytes: bytes,
    filename: str = "workbook.xlsx",
    ocr_provider: Any = None,
    auto_extract: bool = True,
) -> SpreadsheetPayload:
    """Parses an Excel (.xlsx or legacy .xls) archive into structured sheets and row narratives.

    Zero third-party dependencies: relies strictly on standard library
    ``zipfile`` and ``xml.etree.ElementTree`` for modern .xlsx, with seamless
    xlrd / OLE2 fallback for legacy .xls files.

    Args:
        raw_bytes: Binary bytes of the .xlsx or .xls file.
        filename: Optional descriptive filename for narrative groundings.
        ocr_provider: Optional OCRProvider for extracting text from embedded images.
        auto_extract: When True (default), attempts OCR on embedded images.

    Returns:
        SpreadsheetPayload containing workbook metadata, sheets, and tabular row chunks.

    Raises:
        ValueError: If archive is corrupted or not a valid spreadsheet container.
    """
    if not raw_bytes:
        raise ValueError("Cannot process empty spreadsheet bytes.")

    if _is_legacy_xls(raw_bytes, filename):
        return _process_legacy_xls(raw_bytes, filename)

    try:
        zf = zipfile.ZipFile(io.BytesIO(raw_bytes))
    except (zipfile.BadZipFile, io.UnsupportedOperation) as exc:
        raise ValueError(f"Corrupted or invalid XLSX archive: {exc}") from exc

    namelist = set(zf.namelist())
    styles = WorkbookStyles.from_zip(zf)  # date number formats: serials become ISO dates

    # 1. Shared Strings Table (xl/sharedStrings.xml), read incrementally
    shared_strings: list[str] = []
    if "xl/sharedStrings.xml" in namelist:
        shared_strings = xlsx_shared_strings(zf)

    # 2. Parse Workbook relationships (xl/_rels/workbook.xml.rels)
    wb_rels: dict[str, str] = {}
    if "xl/_rels/workbook.xml.rels" in namelist:
        try:
            rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
            for rel in rels_root.iter():
                if _local_tag(rel) == "Relationship":
                    r_id = rel.attrib.get("Id")
                    target = rel.attrib.get("Target")
                    if r_id and target:
                        normalized_target = target.lstrip("/")
                        if not normalized_target.startswith("xl/"):
                            normalized_target = f"xl/{normalized_target}"
                        wb_rels[r_id] = normalized_target
        except ET.ParseError:
            pass

    # 3. Parse Workbook Definition (xl/workbook.xml)
    sheet_targets: list[tuple[str, str]] = []  # (sheet_name, zip_path)
    if "xl/workbook.xml" in namelist:
        try:
            wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
            for sheet in wb_root.iter():
                if _local_tag(sheet) == "sheet":
                    sheet_name = sheet.attrib.get("name", "Sheet")
                    r_id = _get_rel_id(sheet.attrib)
                    target_path = wb_rels.get(r_id, "") if r_id else ""
                    if target_path and target_path in namelist:
                        sheet_targets.append((sheet_name, target_path))
        except ET.ParseError:
            pass

    # Fallback if workbook.xml is missing or failed to resolve
    if not sheet_targets:
        sheet_files = sorted(
            [
                name
                for name in namelist
                if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
            ]
        )
        for idx, s_path in enumerate(sheet_files, 1):
            sheet_targets.append((f"Sheet{idx}", s_path))

    processed_sheets: list[SheetData] = []
    all_chunks: list[SpreadsheetRowChunk] = []
    total_populated_cells = 0
    total_rows_all_sheets = 0

    # 4. Worksheets, streamed row by row (memory is one row, not the sheet's DOM)
    for sheet_name, sheet_path in sheet_targets:
        if sheet_path not in namelist:
            continue
        rows = xlsx_iter_rows(zf, sheet_path, shared_strings, styles)
        lead: list[tuple[int, dict[int, Any]]] = []
        for item in rows:  # leading rows decide where the header is
            lead.append(item)
            if len(lead) >= 12:
                break
        if not lead:
            processed_sheets.append(
                SheetData(sheet_name=sheet_name, total_rows=0, total_columns=0, headers=[])
            )
            continue
        start = pick_header([cells for _, cells in lead]) if len(lead) > 1 else 0
        context = [" ".join(str(v) for v in cells.values()) for _, cells in lead[:start]]
        header_row_map = lead[start][1]
        # A sheet with one row is data, not a header.
        data_rows: Any = lead[start + 1 :] if len(lead) > start + 1 else lead[start:]
        if len(lead) >= 12:
            data_rows = itertools.chain(data_rows, rows)
        names: dict[int, str] = {}  # column index -> header name, columns with data only
        taken: set[str] = set()

        def column_name(c_idx: int, _names=names, _taken=taken, _map=header_row_map) -> str:
            base = str(_map.get(c_idx, f"Column_{c_idx + 1}"))
            name, n = base, 2
            while name in _taken:  # repeated header names keep every column
                name, n = f"{base}_{n}", n + 1
            _taken.add(name)
            _names[c_idx] = name
            return name

        for c_idx in sorted(header_row_map):
            column_name(c_idx)
        sheet_row_chunks: list[SpreadsheetRowChunk] = []
        populated = sum(len(cells) for _, cells in lead[: start + 1])
        row_count = start + 1
        last_index = lead[start][0]
        ordered = True
        for r_num, r_data in data_rows:
            if r_data is header_row_map:  # one-row sheet: the row is its own data
                populated -= len(r_data)
                row_count -= 1
            populated += len(r_data)
            row_count += 1
            ordered = ordered and r_num > last_index
            last_index = r_num
            row_dict = {
                (names.get(c_idx) or column_name(c_idx)): r_data[c_idx] for c_idx in sorted(r_data)
            }
            sheet_row_chunks.append(
                SpreadsheetRowChunk(
                    sheet_name=sheet_name,
                    row_index=r_num,
                    data=row_dict,
                    narrative_text=spreadsheet_row_text(filename, sheet_name, r_num, row_dict),
                )
            )
        if not ordered:  # rows out of order or repeated: sort, the last copy of a row wins
            latest = {chunk.row_index: chunk for chunk in sheet_row_chunks}
            sheet_row_chunks = [latest[k] for k in sorted(latest)]
        headers = [names[c] for c in sorted(names)]
        total_populated_cells += populated
        total_rows_all_sheets += row_count
        for (r_num, _cells), text in zip(lead[:start], context, strict=True):
            all_chunks.append(
                SpreadsheetRowChunk(
                    sheet_name=sheet_name,
                    row_index=r_num,
                    data={"title": text},
                    narrative_text=f"[Workbook: {filename} | Sheet: {sheet_name} | Title] {text}",
                )
            )
        all_chunks.extend(sheet_row_chunks)
        processed_sheets.append(
            SheetData(
                sheet_name=sheet_name,
                total_rows=row_count,
                total_columns=len(headers),
                headers=headers,
                rows=sheet_row_chunks,
                context=context,
            )
        )

    # Extract text from embedded images in xl/media/
    image_texts = _extract_images_from_zip(zf, "xl/media/", ocr_provider, auto_extract)
    if image_texts:
        img_combined = "\n".join(image_texts)
        all_chunks.append(
            SpreadsheetRowChunk(
                sheet_name="[Embedded Images]",
                row_index=0,
                data={},
                narrative_text=(f"[Workbook: {filename} | Embedded Images]\n{img_combined}"),
            )
        )

    meta = SpreadsheetMetadata(
        filename=filename,
        format="xlsx",
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
