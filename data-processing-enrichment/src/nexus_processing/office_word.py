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

"""Word document payload model and section grouping."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .office_zip import _local_tag


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


def group_word_sections(
    chunks: list[WordSectionChunk], filename: str, max_chars: int = 1200
) -> list[WordSectionChunk]:
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
        lines = (
            [heading.text]
            if heading is not None and heading.section_title == first.section_title
            else []
        )
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
                metadata={
                    "paragraphs": len(body),
                    "first_index": first.index,
                    "last_index": body[-1].index,
                },
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
            if body and (
                chunk.section_title != body[0].section_title or size + len(chunk.text) > max_chars
            ):
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
