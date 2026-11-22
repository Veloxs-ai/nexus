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

"""PowerPoint presentations (``.pptx``) to slide chunks."""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from typing import Any

from .office_zip import _extract_images_from_zip, _get_rel_id, _local_tag


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
                                    t.text for t in tc.iter() if _local_tag(t) == "t" and t.text
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

                if (is_title and not title) or (not title and idx == 1 and not body_paragraphs):
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
    image_texts = _extract_images_from_zip(zf, "ppt/media/", ocr_provider, auto_extract)
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
