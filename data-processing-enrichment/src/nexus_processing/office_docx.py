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

"""Word documents (``.docx``) to paragraph, list and table chunks."""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile
from typing import Any

from .docx_text import (
    block_texts,
    cell_span,
    cell_text,
    heading_levels,
    outline_level,
    paragraph_text,
)
from .office_word import WordMetadata, WordPayload, WordSectionChunk, _body_blocks
from .office_zip import _extract_images_from_zip, _local_tag


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
    image_texts = _extract_images_from_zip(archive, "word/media/", ocr_provider, auto_extract)
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
