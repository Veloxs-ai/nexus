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

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "PresentationMetadata",
    "PresentationPayload",
    "SheetData",
    "SlideData",
    "SpreadsheetMetadata",
    "SpreadsheetPayload",
    "SpreadsheetRowChunk",
    "process_presentation_binary",
    "process_spreadsheet_binary",
]

_COORD_RE = re.compile(r"^([A-Za-z]+)(\d+)$")


def _local_tag(elem: ET.Element) -> str:
    """Returns local XML tag without namespace prefix."""
    return elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag


def _col_letter_to_index(col_str: str) -> int:
    """Converts spreadsheet column letter (e.g. 'A', 'Z', 'AA') to 0-based index."""
    idx = 0
    for char in col_str.upper():
        if "A" <= char <= "Z":
            idx = idx * 26 + (ord(char) - ord("A") + 1)
    return max(0, idx - 1)


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


def process_spreadsheet_binary(
    raw_bytes: bytes,
    filename: str = "workbook.xlsx",
) -> SpreadsheetPayload:
    """Parses an Excel (.xlsx) OpenXML archive into structured sheets and row narratives.

    Zero third-party dependencies: relies strictly on standard library
    ``zipfile`` and ``xml.etree.ElementTree``.

    Args:
        raw_bytes: Binary bytes of the .xlsx file.
        filename: Optional descriptive filename for narrative groundings.

    Returns:
        SpreadsheetPayload containing workbook metadata, sheets, and tabular row chunks.

    Raises:
        ValueError: If archive is corrupted or not a valid XLSX container.
    """
    if not raw_bytes:
        raise ValueError("Cannot process empty spreadsheet bytes.")

    try:
        zf = zipfile.ZipFile(io.BytesIO(raw_bytes))
    except (zipfile.BadZipFile, io.UnsupportedOperation) as exc:
        raise ValueError(f"Corrupted or invalid XLSX archive: {exc}") from exc

    namelist = set(zf.namelist())

    # 1. Parse Shared Strings Table (xl/sharedStrings.xml)
    shared_strings: list[str] = []
    if "xl/sharedStrings.xml" in namelist:
        try:
            sst_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in sst_root.iter():
                if _local_tag(si) == "si":
                    parts = [t.text or "" for t in si.iter() if _local_tag(t) == "t" and t.text]
                    shared_strings.append("".join(parts))
        except ET.ParseError:
            pass

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

    # 4. Parse Worksheets
    for sheet_name, sheet_path in sheet_targets:
        if sheet_path not in namelist:
            continue
        try:
            ws_root = ET.fromstring(zf.read(sheet_path))
        except ET.ParseError:
            continue

        # Extract rows and sparse cells
        raw_rows: dict[int, dict[int, Any]] = {}
        max_col_idx = 0

        for row_elem in ws_root.iter():
            if _local_tag(row_elem) != "row":
                continue
            r_attr = row_elem.attrib.get("r")
            try:
                row_idx = int(r_attr) if r_attr else len(raw_rows) + 1
            except ValueError:
                row_idx = len(raw_rows) + 1

            row_cells: dict[int, Any] = {}
            current_col_idx = 0

            for cell_elem in row_elem.iter():
                if _local_tag(cell_elem) != "c":
                    continue
                cell_ref = cell_elem.attrib.get("r", "")
                m = _COORD_RE.match(cell_ref)
                col_idx = _col_letter_to_index(m.group(1)) if m else current_col_idx

                current_col_idx = col_idx + 1
                max_col_idx = max(max_col_idx, col_idx)

                # Parse cell value
                cell_type = cell_elem.attrib.get("t", "n")
                v_elem = next((ch for ch in cell_elem if _local_tag(ch) == "v"), None)
                is_elem = next((ch for ch in cell_elem if _local_tag(ch) == "is"), None)

                val: Any = ""
                if cell_type == "s" and v_elem is not None and v_elem.text:
                    try:
                        str_idx = int(v_elem.text)
                        val = (
                            shared_strings[str_idx]
                            if str_idx < len(shared_strings)
                            else v_elem.text
                        )
                    except ValueError:
                        val = v_elem.text
                elif cell_type == "b" and v_elem is not None:
                    val = "TRUE" if v_elem.text == "1" else "FALSE"
                elif cell_type == "inlineStr" or is_elem is not None:
                    parts = [
                        t.text or ""
                        for t in (is_elem if is_elem is not None else cell_elem).iter()
                        if _local_tag(t) == "t" and t.text
                    ]
                    val = "".join(parts)
                elif v_elem is not None and v_elem.text is not None:
                    raw_v = v_elem.text.strip()
                    try:
                        val = float(raw_v) if "." in raw_v else int(raw_v)
                    except ValueError:
                        val = raw_v

                if val != "":
                    row_cells[col_idx] = val
                    total_populated_cells += 1

            if row_cells:
                raw_rows[row_idx] = row_cells

        if not raw_rows:
            processed_sheets.append(
                SheetData(
                    sheet_name=sheet_name,
                    total_rows=0,
                    total_columns=0,
                    headers=[],
                    rows=[],
                )
            )
            continue

        sorted_row_indices = sorted(raw_rows.keys())
        first_row_idx = sorted_row_indices[0]
        header_row_map = raw_rows[first_row_idx]

        num_cols = max(max_col_idx + 1, max(header_row_map.keys(), default=0) + 1)
        headers: list[str] = [
            str(header_row_map.get(c_idx, f"Column_{c_idx + 1}")) for c_idx in range(num_cols)
        ]

        sheet_row_chunks: list[SpreadsheetRowChunk] = []

        # If more than 1 row, row 1 is header, subsequent are data rows.
        # If only 1 row exists, treat row 1 itself as data.
        data_row_indices = (
            sorted_row_indices[1:] if len(sorted_row_indices) > 1 else sorted_row_indices
        )

        for r_num in data_row_indices:
            r_data = raw_rows[r_num]
            row_dict: dict[str, Any] = {}
            narrative_items: list[str] = []

            for c_idx in range(num_cols):
                h_name = headers[c_idx]
                if c_idx in r_data:
                    c_val = r_data[c_idx]
                    row_dict[h_name] = c_val
                    narrative_items.append(f"{h_name}: {c_val}")

            row_narrative = (
                f"[Workbook: {filename} | Sheet: {sheet_name} | Row {r_num}] "
                + " | ".join(narrative_items)
            )

            chunk = SpreadsheetRowChunk(
                sheet_name=sheet_name,
                row_index=r_num,
                data=row_dict,
                narrative_text=row_narrative,
            )
            sheet_row_chunks.append(chunk)
            all_chunks.append(chunk)

        total_rows_all_sheets += len(raw_rows)
        processed_sheets.append(
            SheetData(
                sheet_name=sheet_name,
                total_rows=len(raw_rows),
                total_columns=num_cols,
                headers=headers,
                rows=sheet_row_chunks,
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
) -> PresentationPayload:
    """Parses a PowerPoint (.pptx) OpenXML archive into structured slide representations.

    Extracts slide titles, body content, and speaker notes with zero dependencies
    via standard library ``zipfile`` and ``xml.etree.ElementTree``.

    Args:
        raw_bytes: Binary bytes of the .pptx file.
        filename: Optional descriptive filename for narrative groundings.

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

    # Fallback to sorting slides in zip if presentation.xml is missing or sparse
    if not ordered_slide_paths:
        ordered_slide_paths = sorted(
            [
                name
                for name in namelist
                if name.startswith("ppt/slides/slide") and name.endswith(".xml")
            ]
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

        # 4. Extract Slide Title and Body Text
        title = ""
        body_paragraphs: list[str] = []
        shape_count = 0

        for sp in slide_root.iter():
            if _local_tag(sp) != "sp":
                continue
            shape_count += 1

            # Check if this shape is a title
            is_title = False
            for ph in sp.iter():
                if _local_tag(ph) == "ph":
                    ph_type = ph.attrib.get("type", "")
                    if ph_type in ("title", "ctrTitle"):
                        is_title = True
                        break

            # Collect text within shape
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

            if is_title and not title:
                title = combined_sp_text
            elif not title and idx == 1 and not body_paragraphs:
                # First text on slide 1 if no explicit title
                title = combined_sp_text
            else:
                body_paragraphs.append(combined_sp_text)

        if not title:
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
