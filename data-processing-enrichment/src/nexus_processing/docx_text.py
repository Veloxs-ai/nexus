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

"""WordprocessingML text: runs in reading order, table cells, heading styles.

``paragraph_text`` walks a paragraph's runs in order and keeps the separators Word stores
as elements instead of characters: ``w:tab`` and ``w:ptab`` become a tab, ``w:br`` and
``w:cr`` a line break, ``w:noBreakHyphen`` a hyphen. Tab stops in ``w:pPr`` are not
runs, so they are never mistaken for text. ``cell_text`` joins the paragraphs of a table
cell with a space (``top`` / ``bottom`` stay two words) and escapes ``|`` for Markdown
tables. ``heading_levels`` reads ``styles.xml`` so localised heading styles
(``Überschrift1``, ``Titre1``) and outline levels count as headings.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Iterator

__all__ = [
    "block_texts",
    "cell_span",
    "cell_text",
    "heading_levels",
    "outline_level",
    "paragraph_text",
]

_BREAK = {"tab": "\t", "ptab": "\t", "br": "\n", "cr": "\n", "noBreakHyphen": "-"}
_SKIP_BLOCK = frozenset({"pPr", "tcPr", "trPr", "tblPr", "tblGrid", "sectPr", "rPr"})


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _val(elem: ET.Element) -> str | None:
    for key, value in elem.attrib.items():
        if _local(key) == "val":
            return value
    return None


def paragraph_text(paragraph: ET.Element) -> str:
    """Text of a paragraph (or any element) with tabs and line breaks kept."""
    parts: list[str] = []
    for run in paragraph.iter():
        if _local(run.tag) != "r":
            continue
        for child in run:
            tag = _local(child.tag)
            if tag == "t":
                if child.text:
                    parts.append(child.text)
            else:
                sep = _BREAK.get(tag)
                if sep:
                    parts.append(sep)
    return "".join(parts)


def block_texts(elem: ET.Element) -> Iterator[str]:
    """Paragraph texts under ``elem`` in order, never descending into a paragraph twice."""
    for child in elem:
        tag = _local(child.tag)
        if tag == "p":
            yield paragraph_text(child)
        elif tag not in _SKIP_BLOCK:
            yield from block_texts(child)


def cell_text(cell: ET.Element) -> str:
    """A table cell as one line: paragraphs joined with a space, ``|`` escaped."""
    words = [" ".join(text.split()) for text in block_texts(cell)]
    return " ".join(w for w in words if w).replace("|", "\\|")


def cell_span(cell: ET.Element) -> int:
    """How many grid columns a cell covers (``w:gridSpan``), at least 1."""
    for prop in cell:
        if _local(prop.tag) != "tcPr":
            continue
        for item in prop:
            if _local(item.tag) == "gridSpan":
                try:
                    return max(1, int(_val(item) or 1))
                except ValueError:
                    return 1
    return 1


def outline_level(ppr: ET.Element) -> int | None:
    """Heading level (1-9) from ``w:outlineLvl`` in paragraph properties, if any."""
    for item in ppr:
        if _local(item.tag) == "outlineLvl":
            try:
                level = int(_val(item) or 9)
            except ValueError:
                return None
            return level + 1 if 0 <= level < 9 else None
    return None


def heading_levels(styles_xml: bytes) -> dict[str, int]:
    """Style id -> heading level for styles named ``heading N`` / ``Title`` / ``Subtitle``
    or carrying an outline level, so ids in any language are recognised."""
    try:
        root = ET.fromstring(styles_xml)
    except ET.ParseError:
        return {}
    levels: dict[str, int] = {}
    for style in root.iter():
        if _local(style.tag) != "style":
            continue
        style_id = next((v for k, v in style.attrib.items() if _local(k) == "styleId"), "")
        if not style_id:
            continue
        level: int | None = None
        for child in style:
            tag = _local(child.tag)
            if tag == "name":
                name = (_val(child) or "").strip().lower()
                if name.startswith("heading") and name[7:].strip().isdigit():
                    level = int(name[7:].strip())
                elif name == "title":
                    level = 1
                elif name == "subtitle":
                    level = 2
            elif tag == "pPr" and level is None:
                level = outline_level(child)
        if level:
            levels[style_id] = level
    return levels
