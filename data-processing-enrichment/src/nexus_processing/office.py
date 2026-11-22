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

"""Zero-dependency Microsoft Office OpenXML (XLSX & PPTX) processors."""

from __future__ import annotations

import hashlib
import io
import itertools
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from typing import Any

from .docx_text import (
    block_texts,
    cell_span,
    cell_text,
    heading_levels,
    outline_level,
    paragraph_text,
)
from .spreadsheet_values import WorkbookStyles, xls_cell_value
from .xlsx_stream import iter_rows as xlsx_iter_rows
from .xlsx_stream import pick_header
from .xlsx_stream import shared_strings as xlsx_shared_strings

__all__ = [
    "PresentationMetadata",
    "PresentationPayload",
    "SheetData",
    "SlideData",
    "SpreadsheetMetadata",
    "SpreadsheetPayload",
    "SpreadsheetRowChunk",
    "WordMetadata",
    "WordPayload",
    "WordSectionChunk",
    "process_presentation_binary",
    "process_spreadsheet_binary",
    "process_word_binary",
    "spreadsheet_row_text",
]


def _local_tag(elem: ET.Element) -> str:
    """Returns local XML tag without namespace prefix."""
    return elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag


# Image extensions recognized in OpenXML media folders
_IMAGE_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff", ".tif", ".webp",
})


def _extract_images_from_zip(
    zf: zipfile.ZipFile,
    media_prefix: str,
    ocr_provider: Any = None,
    auto_extract: bool = True,
) -> list[str]:
    """Extracts text from embedded images in an Office ZIP archive.

    Uses ``process_image_binary`` from images.py so improvements to image
    processing automatically benefit all document formats (PPTX, DOCX, XLSX).

    Args:
        zf: Open ZipFile of the Office document.
        media_prefix: Path prefix for media files (e.g. "ppt/media/").
        ocr_provider: Optional OCRProvider for text extraction from images.
        auto_extract: When True, auto-detects OCR provider if not passed.

    Returns:
        List of extracted text strings from embedded images.
    """
    from .images import process_image_binary

    image_texts: list[str] = []
    seen: dict[bytes, Any] = {}  # the same picture embedded twice is OCR'd once
    for name in zf.namelist():
        if not name.startswith(media_prefix):
            continue
        ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in _IMAGE_EXTENSIONS:
            continue
        try:
            img_bytes = zf.read(name)
            if not img_bytes:
                continue
            digest = hashlib.sha1(img_bytes).digest()
            payload = seen.get(digest)
            if payload is None:
                payload = seen[digest] = process_image_binary(
                    img_bytes,
                    filename=name.split("/")[-1],
                    ocr_provider=ocr_provider,
                    auto_extract=auto_extract,
                )
            parts: list[str] = []
            basename = name.split("/")[-1]
            if payload.metadata.ocr_text:
                parts.append(payload.metadata.ocr_text)
            if payload.metadata.caption:
                parts.append(payload.metadata.caption)
            if parts:
                image_texts.append(
                    f"[Image: {basename}] " + " ".join(parts)
                )
            else:
                w = payload.metadata.width
                h = payload.metadata.height
                image_texts.append(
                    f"[Embedded Image: {basename} {w}x{h}px]"
                )
        except Exception:
            continue
    return image_texts


def _get_rel_id(attrib: dict[str, str]) -> str | None:
    """Extracts relationship ID (e.g. 'rId1') from element attributes."""
    for k, v in attrib.items():
        local_k = k.split("}")[-1] if "}" in k else k
        if "relationships" in k.lower() or k.startswith("r:") or ("}" in k and local_k == "id"):
            return v
    return attrib.get("r:id")


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


@dataclass
class SlideData:
    """Processed slide data containing title, content, speaker notes, and narrative."""

    slide_number: int
    title: str
    body_text: str
    speaker_notes: str
    shape_count: int
    word_count: int
    narrative_text: str


@dataclass
class PresentationMetadata:
    """High-level metadata for a PowerPoint presentation."""

    filename: str
    format: str  # "pptx"
    total_slides: int
    total_words: int
    slide_titles: list[str]
    file_size_bytes: int


@dataclass
class PresentationPayload:
    """Comprehensive processed presentation payload."""

    metadata: PresentationMetadata
    slides: list[SlideData] = field(default_factory=list)


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
    headers = [f"Col_{i+1}" for i in range(chunk_size)]

    for idx, i in enumerate(range(0, len(extracted_lines), chunk_size), 1):
        row_slice = extracted_lines[i : i + chunk_size]
        row_dict = {f"Col_{j+1}": val for j, val in enumerate(row_slice)}
        narrative = (
            f"[Workbook: {filename} | Sheet: {sheet_name} | Row {idx}] "
            + " | ".join(f"Col_{j+1}: {val}" for j, val in enumerate(row_slice))
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
    image_texts = _extract_images_from_zip(
        zf, "xl/media/", ocr_provider, auto_extract
    )
    if image_texts:
        img_combined = "\n".join(image_texts)
        all_chunks.append(
            SpreadsheetRowChunk(
                sheet_name="[Embedded Images]",
                row_index=0,
                data={},
                narrative_text=(
                    f"[Workbook: {filename} | Embedded Images]\n"
                    f"{img_combined}"
                ),
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


def process_presentation_binary(
    raw_bytes: bytes,
    filename: str = "presentation.pptx",
    ocr_provider: Any = None,
    auto_extract: bool = True,
) -> PresentationPayload:
    """Parses a PowerPoint (.pptx) OpenXML archive into structured slide representations.

    Extracts slide titles, body content, speaker notes, and embedded image text
    via standard library ``zipfile`` and ``xml.etree.ElementTree``.

    Args:
        raw_bytes: Binary bytes of the .pptx file.
        filename: Optional descriptive filename for narrative groundings.
        ocr_provider: Optional OCRProvider for extracting text from embedded images.
        auto_extract: When True (default), attempts OCR on embedded images.

    Returns:
        PresentationPayload containing deck metadata and slide objects with speaker notes.

    Raises:
        ValueError: If archive is corrupted or not a valid PPTX container.
    """
    if not raw_bytes:
        raise ValueError("Cannot process empty presentation bytes.")

    try:
        zf = zipfile.ZipFile(io.BytesIO(raw_bytes))
    except (zipfile.BadZipFile, io.UnsupportedOperation) as exc:
        raise ValueError(f"Corrupted or invalid PPTX archive: {exc}") from exc

    namelist = set(zf.namelist())

    # 1. Parse Presentation relationships (ppt/_rels/presentation.xml.rels)
    pres_rels: dict[str, str] = {}
    if "ppt/_rels/presentation.xml.rels" in namelist:
        try:
            rels_root = ET.fromstring(zf.read("ppt/_rels/presentation.xml.rels"))
            for rel in rels_root.iter():
                if _local_tag(rel) == "Relationship":
                    r_id = rel.attrib.get("Id")
                    target = rel.attrib.get("Target")
                    if r_id and target:
                        normalized_target = target.lstrip("/")
                        if not normalized_target.startswith("ppt/"):
                            normalized_target = f"ppt/{normalized_target}"
                        pres_rels[r_id] = normalized_target
        except ET.ParseError:
            pass

    # 2. Parse Presentation XML (ppt/presentation.xml) for slide ordering
    ordered_slide_paths: list[str] = []
    if "ppt/presentation.xml" in namelist:
        try:
            pres_root = ET.fromstring(zf.read("ppt/presentation.xml"))
            for sld_id in pres_root.iter():
                if _local_tag(sld_id) == "sldId":
                    r_id = _get_rel_id(sld_id.attrib)
                    target_path = pres_rels.get(r_id, "") if r_id else ""
                    if target_path and target_path in namelist:
                        ordered_slide_paths.append(target_path)
        except ET.ParseError:
            pass

    if not ordered_slide_paths:
        def _slide_num(path: str) -> int:
            m = re.search(r"slide(\d+)\.xml", path)
            return int(m.group(1)) if m else 0

        ordered_slide_paths = sorted(
            [
                name
                for name in namelist
                if name.startswith("ppt/slides/slide") and name.endswith(".xml")
            ],
            key=_slide_num,
        )

    slides: list[SlideData] = []
    slide_titles: list[str] = []
    total_words = 0

    for idx, slide_path in enumerate(ordered_slide_paths, 1):
        if slide_path not in namelist:
            continue
        try:
            slide_root = ET.fromstring(zf.read(slide_path))
        except ET.ParseError:
            continue

        # 3. Locate Speaker Notes for this slide
        # Path: ppt/slides/_rels/slide{N}.xml.rels -> notesSlide{N}.xml
        slide_dir, slide_base = slide_path.rsplit("/", 1)
        rels_path = f"{slide_dir}/_rels/{slide_base}.rels"
        notes_path: str | None = None

        if rels_path in namelist:
            try:
                s_rels_root = ET.fromstring(zf.read(rels_path))
                for rel in s_rels_root.iter():
                    if _local_tag(rel) == "Relationship":
                        rel_type = rel.attrib.get("Type", "")
                        if rel_type.endswith("notesSlide"):
                            target = rel.attrib.get("Target", "")
                            if target:
                                # Resolve relative path (e.g. "../notesSlides/notesSlide1.xml")
                                norm_target = target.replace("../", "ppt/").lstrip("/")
                                if not norm_target.startswith("ppt/"):
                                    norm_target = f"ppt/{norm_target}"
                                if norm_target in namelist:
                                    notes_path = norm_target
                                    break
            except ET.ParseError:
                pass

        # Fallback convention check for notesSlide
        if not notes_path:
            candidate_notes = f"ppt/notesSlides/notesSlide{idx}.xml"
            if candidate_notes in namelist:
                notes_path = candidate_notes

        speaker_notes = ""
        if notes_path and notes_path in namelist:
            try:
                notes_root = ET.fromstring(zf.read(notes_path))
                notes_paras: list[str] = []
                for sp in notes_root.iter():
                    if _local_tag(sp) != "sp":
                        continue
                    # Check if shape is notes body
                    is_body = False
                    for ph in sp.iter():
                        if _local_tag(ph) == "ph" and ph.attrib.get("type") in ("body", None):
                            is_body = True
                            break
                    text_parts: list[str] = []
                    for t in sp.iter():
                        if _local_tag(t) == "t" and t.text:
                            text_parts.append(t.text)
                    if text_parts and (is_body or not notes_paras):
                        full_sp_text = " ".join(text_parts).strip()
                        if full_sp_text and not full_sp_text.isdigit():
                            notes_paras.append(full_sp_text)
                speaker_notes = "\n".join(notes_paras).strip()
            except ET.ParseError:
                pass

        # 4. Extract Slide Title, Body Text, Tables, and Grouped Shapes
        title = ""
        body_paragraphs: list[str] = []
        shape_count = 0

        # Step A: Identify explicit title shape first
        for sp in slide_root.iter():
            if _local_tag(sp) == "sp":
                shape_count += 1
                for ph in sp.iter():
                    if _local_tag(ph) == "ph":
                        ph_type = ph.attrib.get("type", "")
                        if ph_type in ("title", "ctrTitle") and not title:
                            t_nodes = [t.text for t in sp.iter() if _local_tag(t) == "t" and t.text]
                            sp_t = " ".join(t_nodes).strip()
                            if sp_t:
                                title = sp_t
                                break

        # Step B: Extract Tables (<a:tbl>)
        for tbl in slide_root.iter():
            if _local_tag(tbl) == "tbl":
                shape_count += 1
                table_rows: list[str] = []
                for tr in tbl.iter():
                    if _local_tag(tr) == "tr":
                        row_cells: list[str] = []
                        for tc in tr.iter():
                            if _local_tag(tc) == "tc":
                                cell_texts = [
                                    t.text for t in tc.iter()
                                    if _local_tag(t) == "t" and t.text
                                ]
                                cell_str = " ".join(cell_texts).strip().replace("|", "\\|")
                                row_cells.append(cell_str if cell_str else "-")
                        if any(c != "-" for c in row_cells):
                            table_rows.append("| " + " | ".join(row_cells) + " |")
                            if len(table_rows) == 1:  # first row is the header: a Markdown table
                                table_rows.append("|" + " --- |" * len(row_cells))
                if table_rows:
                    body_paragraphs.append("[Table]\n" + "\n".join(table_rows))

        # Step C: Extract text from all shapes, groups, and text frames
        for sp in slide_root.iter():
            tag = _local_tag(sp)
            if tag in ("sp", "grpSp", "graphicFrame"):
                if tag != "sp":
                    shape_count += 1
                # Skip if contains table (already processed in Step B)
                if any(_local_tag(sub) == "tbl" for sub in sp.iter()):
                    continue

                is_title = False
                for ph in sp.iter():
                    if _local_tag(ph) == "ph":
                        ph_type = ph.attrib.get("type", "")
                        if ph_type in ("title", "ctrTitle"):
                            is_title = True
                            break

                para_texts: list[str] = []
                for p in sp.iter():
                    if _local_tag(p) == "p":
                        t_nodes = [t.text for t in p.iter() if _local_tag(t) == "t" and t.text]
                        line_text = "".join(t_nodes).strip()
                        if line_text:
                            para_texts.append(line_text)

                combined_sp_text = "\n".join(para_texts).strip()
                if not combined_sp_text:
                    continue

                if (is_title and not title) or (
                    not title and idx == 1 and not body_paragraphs
                ):
                    title = combined_sp_text
                elif combined_sp_text != title and combined_sp_text not in body_paragraphs:
                    body_paragraphs.append(combined_sp_text)

        if not title and not body_paragraphs:
            # Text outside any shape (hand-made or converted slides): never drop it.
            loose = " ".join(
                t.text.strip() for t in slide_root.iter() if _local_tag(t) == "t" and t.text
            )
            if loose.strip():
                body_paragraphs.append(loose.strip())

        if not title:
            if body_paragraphs:
                first_line = body_paragraphs[0].split("\n")[0].strip()
                if len(first_line) < 100:
                    title = first_line
                    remaining = "\n".join(body_paragraphs[0].split("\n")[1:]).strip()
                    if remaining:
                        body_paragraphs[0] = remaining
                    else:
                        body_paragraphs.pop(0)
                else:
                    title = f"Slide {idx}"
            else:
                title = f"Slide {idx}"

        body_text = "\n".join(body_paragraphs).strip()
        slide_titles.append(title)

        # Build narrative grounding
        narrative_parts = [f"[Presentation: {filename} | Slide {idx}: {title}]"]
        if body_text:
            narrative_parts.append(body_text)
        if speaker_notes:
            narrative_parts.append(f"Speaker Notes: {speaker_notes}")
        narrative_text = "\n".join(narrative_parts)

        words_in_slide = len(narrative_text.split())
        total_words += words_in_slide

        slide_data = SlideData(
            slide_number=idx,
            title=title,
            body_text=body_text,
            speaker_notes=speaker_notes,
            shape_count=shape_count,
            word_count=words_in_slide,
            narrative_text=narrative_text,
        )
        slides.append(slide_data)

    # Extract SmartArt diagram text from ppt/diagrams/dataN.xml
    smartart_texts: list[str] = []
    for zname in zf.namelist():
        if zname.startswith("ppt/diagrams/data") and zname.endswith(".xml"):
            try:
                dgm_root = ET.fromstring(zf.read(zname))
                # DrawingML diagram namespace
                dgm_ns = "http://schemas.openxmlformats.org/drawingml/2006/diagram"
                a_ns = "http://schemas.openxmlformats.org/drawingml/2006/main"
                for pt_elem in dgm_root.iter(f"{{{dgm_ns}}}pt"):
                    for t_elem in pt_elem.iter(f"{{{a_ns}}}t"):
                        if t_elem.text and t_elem.text.strip():
                            smartart_texts.append(t_elem.text.strip())
            except Exception:
                pass

    if smartart_texts and slides:
        last_slide = slides[-1]
        smartart_combined = "\n".join(smartart_texts)
        last_slide.body_text += f"\n\n[SmartArt Data]\n{smartart_combined}"
        last_slide.narrative_text += f"\n\n[SmartArt Data]\n{smartart_combined}"
        extra_words = len(smartart_combined.split())
        last_slide.word_count += extra_words
        total_words += extra_words

    # Extract text from embedded images in ppt/media/
    image_texts = _extract_images_from_zip(
        zf, "ppt/media/", ocr_provider, auto_extract
    )
    if image_texts and slides:
        img_combined = "\n".join(image_texts)
        last_slide = slides[-1]
        last_slide.body_text += f"\n\n{img_combined}"
        last_slide.narrative_text += f"\n\n{img_combined}"
        extra_words = len(img_combined.split())
        last_slide.word_count += extra_words
        total_words += extra_words

    metadata = PresentationMetadata(
        filename=filename,
        format="pptx",
        total_slides=len(slides),
        total_words=total_words,
        slide_titles=slide_titles,
        file_size_bytes=len(raw_bytes),
    )

    return PresentationPayload(
        metadata=metadata,
        slides=slides,
    )


@dataclass
class WordSectionChunk:
    """A grounded section or paragraph chunk from a Word (.docx) document."""

    chunk_id: str
    section_title: str
    heading_level: int
    item_type: str  # "paragraph", "table", "heading", "list_item"
    index: int
    text: str
    narrative_text: str
    word_count: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WordMetadata:
    """Metadata summary of a processed Word (.docx) document."""

    filename: str
    format: str  # "docx"
    total_paragraphs: int
    total_tables: int
    total_headings: int
    total_words: int
    headings: list[str] = field(default_factory=list)
    file_size_bytes: int = 0
    title: str = ""
    author: str = ""
    header_texts: list[str] = field(default_factory=list)
    footer_texts: list[str] = field(default_factory=list)


@dataclass
class WordPayload:
    """Container for processed Word (.docx) document output."""

    metadata: WordMetadata
    chunks: list[WordSectionChunk]



def group_word_sections(chunks: list[WordSectionChunk], filename: str, max_chars: int = 1200) -> list[WordSectionChunk]:
    """Merge a section's heading, paragraphs and list items into section-sized chunks.

    One chunk per paragraph produced heading-only chunks and hundreds of tiny
    fragments per document, which wastes vectors and scatters an answer across
    many hits. Consecutive body items of the same section are packed up to
    ``max_chars``; the heading travels with its section; tables stay separate.
    """
    grouped: list[WordSectionChunk] = []
    body: list[WordSectionChunk] = []
    heading: WordSectionChunk | None = None

    def flush() -> None:
        nonlocal body, heading
        if not body:
            return
        first = body[0]
        lines = ([heading.text] if heading is not None and heading.section_title == first.section_title else [])
        lines += [c.text for c in body]
        text = "\n".join(lines)
        grouped.append(
            WordSectionChunk(
                chunk_id=first.chunk_id,
                section_title=first.section_title,
                heading_level=first.heading_level,
                item_type="section",
                index=first.index,
                text=text,
                narrative_text=f"[Document: {filename} | Section: {first.section_title}]\n{text}",
                word_count=sum(c.word_count for c in body),
                metadata={"paragraphs": len(body), "first_index": first.index, "last_index": body[-1].index},
            )
        )
        body = []
        heading = None

    for chunk in chunks:
        if chunk.item_type == "heading":
            flush()
            if heading is not None:
                grouped.append(heading)  # heading with no body of its own
            heading = chunk
            continue
        if chunk.item_type in ("paragraph", "list_item"):
            size = sum(len(c.text) + 1 for c in body)
            if body and (chunk.section_title != body[0].section_title or size + len(chunk.text) > max_chars):
                flush()
            body.append(chunk)
            continue
        flush()
        if heading is not None:
            grouped.append(heading)
            heading = None
        grouped.append(chunk)
    flush()
    if heading is not None:
        grouped.append(heading)
    return grouped


def _body_blocks(body: Any) -> Any:
    """Paragraphs and tables of a document body in order, including those inside block-level
    content controls (``w:sdt``/``w:sdtContent``), where Word templates often keep the text."""
    for elem in body:
        if _local_tag(elem) == "sdt":
            for part in elem:
                if _local_tag(part) == "sdtContent":
                    yield from _body_blocks(part)
        else:
            yield elem


def process_word_binary(
    raw_bytes: bytes,
    filename: str = "document.docx",
    ocr_provider: Any = None,
    auto_extract: bool = True,
) -> WordPayload:
    """Extracts headings, paragraphs, tables, and embedded image text from Word (.docx)."""
    if not raw_bytes.startswith(b"PK\x03\x04"):
        raise ValueError(f"Invalid DOCX container for '{filename}': missing ZIP magic header.")

    try:
        archive = zipfile.ZipFile(io.BytesIO(raw_bytes))
    except Exception as exc:
        raise ValueError(f"Failed to decompress DOCX archive '{filename}': {exc}") from exc

    namelist = set(archive.namelist())
    if "word/document.xml" not in namelist:
        raise ValueError(f"Corrupted DOCX container '{filename}': missing word/document.xml.")

    doc_title = ""
    doc_author = ""
    if "docProps/core.xml" in namelist:
        try:
            core_tree = ET.fromstring(archive.read("docProps/core.xml"))
            for elem in core_tree.iter():
                tag = _local_tag(elem)
                if tag == "title" and elem.text:
                    doc_title = elem.text.strip()
                elif tag == "creator" and elem.text:
                    doc_author = elem.text.strip()
        except Exception:
            pass

    try:
        doc_tree = ET.fromstring(archive.read("word/document.xml"))
    except Exception as exc:
        raise ValueError(f"Failed to parse word/document.xml in '{filename}': {exc}") from exc

    body = None
    for child in doc_tree.iter():
        if _local_tag(child) == "body":
            body = child
            break

    if body is None:
        return WordPayload(
            metadata=WordMetadata(
                filename=filename,
                format="docx",
                total_paragraphs=0,
                total_tables=0,
                total_headings=0,
                total_words=0,
                file_size_bytes=len(raw_bytes),
                title=doc_title,
                author=doc_author,
            ),
            chunks=[],
        )

    style_levels: dict[str, int] = {}
    if "word/styles.xml" in namelist:
        style_levels = heading_levels(archive.read("word/styles.xml"))

    chunks: list[WordSectionChunk] = []
    headings: list[str] = []
    current_section = doc_title or "Document Overview"
    current_heading_level = 0
    heading_stack: list[tuple[int, str]] = []  # (level, text): "Section" is the full path
    total_paragraphs = 0
    total_tables = 0
    total_words = 0
    chunk_seq = 0

    for elem in _body_blocks(body):
        tag = _local_tag(elem)

        if tag == "p":
            p_style = ""
            is_list = False
            p_outline: int | None = None
            for p_child in elem:
                c_tag = _local_tag(p_child)
                if c_tag == "pPr":
                    p_outline = outline_level(p_child)
                    for pr_node in p_child:
                        pr_tag = _local_tag(pr_node)
                        if pr_tag == "pStyle":
                            for k, v in pr_node.attrib.items():
                                attr_name = k.split("}")[-1] if "}" in k else k
                                if attr_name == "val":
                                    p_style = v
                        elif pr_tag == "numPr":
                            is_list = True

            p_text = paragraph_text(elem).strip()
            if not p_text:
                continue

            total_paragraphs += 1
            words_in_p = len(p_text.split())
            total_words += words_in_p
            chunk_seq += 1

            # Detect headings
            is_heading = False
            h_level = 0
            if p_style:
                style_lower = p_style.lower()
                if "heading" in style_lower:
                    is_heading = True
                    digits = [c for c in p_style if c.isdigit()]
                    h_level = int(digits[0]) if digits else 1
                elif style_lower in ("title", "subtitle"):
                    is_heading = True
                    h_level = 1 if style_lower == "title" else 2
                elif p_style in style_levels:  # localised style ids (Überschrift1, Titre1)
                    is_heading = True
                    h_level = style_levels[p_style]
            if not is_heading and p_outline:
                is_heading = True
                h_level = p_outline

            if is_heading:
                heading_stack = [(lvl, txt) for lvl, txt in heading_stack if lvl < h_level]
                heading_stack.append((h_level, p_text))
                current_section = " > ".join(txt for _, txt in heading_stack)
                current_heading_level = h_level
                headings.append(p_text)
                narrative = f"[Document: {filename} | Heading (Level {h_level}): {p_text}]"
                chunks.append(
                    WordSectionChunk(
                        chunk_id=f"p_{chunk_seq}",
                        section_title=p_text,
                        heading_level=h_level,
                        item_type="heading",
                        index=total_paragraphs,
                        text=p_text,
                        narrative_text=narrative,
                        word_count=words_in_p,
                        metadata={"style": p_style, "heading_level": h_level},
                    )
                )
            elif is_list:
                list_text = f"• {p_text}"
                narrative = (
                    f"[Document: {filename} | Section: {current_section} | List Item]\n{list_text}"
                )
                chunks.append(
                    WordSectionChunk(
                        chunk_id=f"p_{chunk_seq}",
                        section_title=current_section,
                        heading_level=current_heading_level,
                        item_type="list_item",
                        index=total_paragraphs,
                        text=list_text,
                        narrative_text=narrative,
                        word_count=words_in_p,
                        metadata={"style": p_style, "is_list": True},
                    )
                )
            else:
                narrative = (
                    f"[Document: {filename} | Section: {current_section} "
                    f"| Para {total_paragraphs}]\n"
                    f"{p_text}"
                )
                chunks.append(
                    WordSectionChunk(
                        chunk_id=f"p_{chunk_seq}",
                        section_title=current_section,
                        heading_level=current_heading_level,
                        item_type="paragraph",
                        index=total_paragraphs,
                        text=p_text,
                        narrative_text=narrative,
                        word_count=words_in_p,
                        metadata={"style": p_style},
                    )
                )

        elif tag == "tbl":
            total_tables += 1
            chunk_seq += 1
            table_rows_data: list[list[str]] = []

            for tr in elem:
                if _local_tag(tr) == "tr":
                    row_cells: list[str] = []
                    for tc in tr:
                        if _local_tag(tc) == "tc":
                            row_cells.append(cell_text(tc))
                            # a merged cell keeps the columns after it aligned
                            row_cells.extend([""] * (cell_span(tc) - 1))
                    if row_cells:
                        table_rows_data.append(row_cells)

            if table_rows_data:
                col_count = max(len(r) for r in table_rows_data)
                formatted_rows: list[str] = []
                for r_idx, r in enumerate(table_rows_data):
                    padded_r = r + [""] * (col_count - len(r))
                    formatted_rows.append("| " + " | ".join(padded_r) + " |")
                    if r_idx == 0:
                        formatted_rows.append("| " + " | ".join(["---"] * col_count) + " |")

                tbl_text = "\n".join(formatted_rows)
                tbl_words = len(tbl_text.split())
                total_words += tbl_words

                narrative = (
                    f"[Document: {filename} | Section: {current_section} | Table {total_tables}]\n"
                    f"{tbl_text}"
                )
                chunks.append(
                    WordSectionChunk(
                        chunk_id=f"tbl_{chunk_seq}",
                        section_title=current_section,
                        heading_level=current_heading_level,
                        item_type="table",
                        index=total_tables,
                        text=tbl_text,
                        narrative_text=narrative,
                        word_count=tbl_words,
                        metadata={"row_count": len(table_rows_data), "col_count": col_count},
                    )
                )

    # Extract headers and footers for document metadata
    header_texts: list[str] = []
    footer_texts: list[str] = []
    for zname in archive.namelist():
        if zname.startswith("word/header") and zname.endswith(".xml"):
            try:
                hdr_root = ET.fromstring(archive.read(zname))
                hdr_parts = [t.strip() for t in block_texts(hdr_root) if t.strip()]
                if hdr_parts:
                    header_texts.append(" ".join(hdr_parts))
            except Exception:
                pass
        elif zname.startswith("word/footer") and zname.endswith(".xml"):
            try:
                ftr_root = ET.fromstring(archive.read(zname))
                ftr_parts = [t.strip() for t in block_texts(ftr_root) if t.strip()]
                if ftr_parts:
                    footer_texts.append(" ".join(ftr_parts))
            except Exception:
                pass

    # Extract footnotes and endnotes
    footnote_texts: list[str] = []
    for fn_file in ("word/footnotes.xml", "word/endnotes.xml"):
        if fn_file in archive.namelist():
            try:
                fn_root = ET.fromstring(archive.read(fn_file))
                for fn_elem in fn_root.iter():
                    if _local_tag(fn_elem) in ("footnote", "endnote"):
                        fn_id = fn_elem.get(
                            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}id",
                            fn_elem.get("id", ""),
                        )
                        # Skip separator footnotes (id 0 and 1)
                        if fn_id in ("0", "1", "-1"):
                            continue
                        fn_parts = [t.strip() for t in block_texts(fn_elem) if t.strip()]
                        if fn_parts:
                            footnote_texts.append(" ".join(fn_parts))
            except Exception:
                pass

    if footnote_texts:
        chunk_seq += 1
        fn_text = "\n".join(footnote_texts)
        fn_words = len(fn_text.split())
        total_words += fn_words
        narrative = f"[Document: {filename} | Footnotes]\n{fn_text}"
        chunks.append(
            WordSectionChunk(
                chunk_id=f"fn_{chunk_seq}",
                section_title="Footnotes",
                heading_level=0,
                item_type="paragraph",
                index=total_paragraphs + 1,
                text=fn_text,
                narrative_text=narrative,
                word_count=fn_words,
            )
        )

    # Extract text from embedded images in word/media/
    image_texts = _extract_images_from_zip(
        archive, "word/media/", ocr_provider, auto_extract
    )
    if image_texts:
        chunk_seq += 1
        img_combined = "\n".join(image_texts)
        img_words = len(img_combined.split())
        total_words += img_words
        narrative = f"[Document: {filename} | Embedded Images]\n{img_combined}"
        chunks.append(
            WordSectionChunk(
                chunk_id=f"img_{chunk_seq}",
                section_title="Embedded Images",
                heading_level=0,
                item_type="paragraph",
                index=total_paragraphs + 2,
                text=img_combined,
                narrative_text=narrative,
                word_count=img_words,
            )
        )

    metadata = WordMetadata(
        filename=filename,
        format="docx",
        total_paragraphs=total_paragraphs,
        total_tables=total_tables,
        total_headings=len(headings),
        total_words=total_words,
        headings=headings,
        file_size_bytes=len(raw_bytes),
        title=doc_title,
        author=doc_author,
        header_texts=header_texts,
        footer_texts=footer_texts,
    )

    return WordPayload(
        metadata=metadata,
        chunks=chunks,
    )
