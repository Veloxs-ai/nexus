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

"""Streaming SpreadsheetML: worksheet rows and shared strings without a full DOM.

``iter_rows`` reads a worksheet with ``ElementTree.iterparse`` straight from the zip
member and frees each row once read, so memory is one row instead of the whole sheet
(a 200k-row sheet no longer needs ~1 GB of element objects). Tags are matched as
qualified names, cells are direct children of a row, and column letters are converted
once per distinct letter run. ``pick_header`` skips sparse title rows above the header;
``unique_headers`` keeps every column when header names repeat.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator
from typing import Any

from .spreadsheet_values import WorkbookStyles

__all__ = ["iter_rows", "pick_header", "shared_strings", "unique_headers"]

_DIGITS = "0123456789"


def _namespace(tag: str) -> str:
    return tag[: tag.index("}") + 1] if tag.startswith("{") else ""


def _column(letters: str) -> int:
    idx = 0
    for char in letters.upper():
        if "A" <= char <= "Z":
            idx = idx * 26 + (ord(char) - 64)
    return max(0, idx - 1)


def _rich_text(elem: ET.Element, t_tag: str, r_tag: str) -> str:
    """Text of a shared or inline string: plain ``t`` and rich-text runs ``r/t``;
    phonetic guides (``rPh``) are readings, not content, so they are left out."""
    parts: list[str] = []
    for child in elem:
        if child.tag == t_tag:
            if child.text:
                parts.append(child.text)
        elif child.tag == r_tag:
            for t in child.iter(t_tag):
                if t.text:
                    parts.append(t.text)
    return "".join(parts)


def shared_strings(zf: zipfile.ZipFile, path: str = "xl/sharedStrings.xml") -> list[str]:
    """The shared string table, read incrementally (a malformed tail keeps what was read)."""
    strings: list[str] = []
    try:
        with zf.open(path) as fh:
            root = None
            si = t_tag = r_tag = ""
            for event, elem in ET.iterparse(fh, events=("start", "end")):
                if root is None:
                    root = elem
                    ns = _namespace(elem.tag)
                    si, t_tag, r_tag = ns + "si", ns + "t", ns + "r"
                    continue
                if event == "end" and elem.tag == si:
                    strings.append(_rich_text(elem, t_tag, r_tag))
                    root.clear()
    except (ET.ParseError, KeyError, OSError, zipfile.BadZipFile):
        pass
    return strings


def iter_rows(
    zf: zipfile.ZipFile, path: str, strings: list[str], styles: WorkbookStyles
) -> Iterator[tuple[int, dict[int, Any]]]:
    """``(row number, {column index: value})`` for every non-empty row, in file order.

    Values follow the cell type: shared strings, booleans as ``TRUE``/``FALSE``, inline
    strings, numbers typed by ``styles`` (date formats become ISO text) and formula
    text, errors and ISO dates kept as text. A malformed tail ends the sheet early."""
    letters_cache: dict[str, int] = {}
    with zf.open(path) as fh:
        parser = ET.iterparse(fh, events=("start", "end"))
        row_tag = c_tag = v_tag = is_tag = t_tag = r_tag = ""
        parent: ET.Element | None = None
        last_start: ET.Element | None = None
        prev_row = 0
        try:
            for event, elem in parser:
                if event == "start":
                    if not row_tag:
                        ns = _namespace(elem.tag)
                        row_tag, c_tag, v_tag = ns + "row", ns + "c", ns + "v"
                        is_tag, t_tag, r_tag = ns + "is", ns + "t", ns + "r"
                    elif elem.tag == row_tag and parent is None:
                        parent = last_start
                    last_start = elem
                    continue
                if elem.tag != row_tag:
                    continue
                r_attr = elem.get("r")
                try:
                    row_idx = int(r_attr) if r_attr else prev_row + 1
                except ValueError:
                    row_idx = prev_row + 1
                prev_row = row_idx
                cells: dict[int, Any] = {}
                col = 0
                for cell in elem:
                    if cell.tag != c_tag:
                        continue
                    ref = cell.get("r", "")
                    letters = ref.rstrip(_DIGITS)
                    if letters and len(letters) < len(ref) and letters.isalpha():
                        col = letters_cache.get(letters, -1)
                        if col < 0:
                            col = letters_cache[letters] = _column(letters)
                    kind = cell.get("t", "n")
                    v = cell.find(v_tag)
                    inline = cell.find(is_tag)
                    val: Any = ""
                    if kind == "s" and v is not None and v.text:
                        try:
                            idx = int(v.text)
                            val = strings[idx] if idx < len(strings) else v.text
                        except ValueError:
                            val = v.text
                    elif kind == "b" and v is not None:
                        val = "TRUE" if v.text == "1" else "FALSE"
                    elif kind == "inlineStr" or inline is not None:
                        val = _rich_text(inline if inline is not None else cell, t_tag, r_tag)
                    elif v is not None and v.text is not None:
                        raw = v.text.strip()
                        val = styles.value(raw, cell.get("s")) if kind in ("n", "") else raw
                    if val != "":
                        cells[col] = val
                    col += 1
                elem.clear()
                if parent is not None:
                    parent.clear()  # drop the emptied rows too: memory stays one row
                if cells:
                    yield row_idx, cells
        except ET.ParseError:
            return


def pick_header(rows: list[dict[int, Any]], look: int = 10) -> int:
    """Index of the header among the leading rows: a row with at most two text cells
    that fills under 60% of the width of the rows below it is a title, not a header.
    A full header row is never skipped, and at least one data row stays below it."""
    start = 0
    while start < min(look, len(rows) - 2):
        row = rows[start]
        width = max(len(r) for r in rows[start + 1 : start + 1 + look])
        sparse = len(row) <= 2 and len(row) < math.ceil(0.6 * width)
        if not (sparse and all(isinstance(v, str) for v in row.values())):
            break
        start += 1
    return start


def unique_headers(names: list[str]) -> list[str]:
    """Header names with repeats numbered (``Amount``, ``Amount_2``) so no column's
    values overwrite another's in a row record."""
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        unique, n = name, 2
        while unique in seen:
            unique, n = f"{name}_{n}", n + 1
        seen.add(unique)
        out.append(unique)
    return out
