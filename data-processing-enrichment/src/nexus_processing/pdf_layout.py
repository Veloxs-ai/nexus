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

"""PDF page layout: lines, running headers and footers, headings, page text.

Works on positioned text runs from ``pdf_content`` (or on plain page texts from another
extractor, where positions and sizes are unknown):

- ``runs_to_lines`` joins runs on one baseline into lines, inserting a space where the
  gap between runs is wider than a fraction of the font size; a two-column page is read
  column by column (``pdf_columns``);
- ``remove_running_lines`` drops lines that repeat in the top or bottom band of most
  pages (running headers, footers, page numbers; digits are masked when comparing, so
  "Page 3 of 10" repeats too);
- ``heading_sizes`` finds the body font size (the most used) and ranks larger sizes as
  heading levels; ``page_markdown`` renders a page's lines as Markdown with ``#``
  headings and paragraph breaks, and re-joins words hyphenated across lines.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from .pdf_columns import GUTTER_GAP, MIN_SIDE_LINES, column_lines
from .pdf_content import TextRun

__all__ = [
    "Line",
    "heading_sizes",
    "hyphenated_words",
    "lines_from_text",
    "page_markdown",
    "remove_running_lines",
    "runs_to_lines",
]

SPACE_GAP = 0.15  # x gap between runs, in font sizes, that is a word break
HEADING_RATIO = 1.15
BAND_LINES = 2
_DIGITS = re.compile(r"\d+")
_SPACES = re.compile(r"\s+")
_HYPHEN = re.compile(r"([^\W\d_])-\n([^\W\d_])")
_WORD_END = re.compile(r"[^\W\d_]{1,64}$")
_WORD_START = re.compile(r"[^\W\d_]{1,64}")
_COMPOUND = re.compile(r"[^\W\d_]+-[^\W\d_]+")


@dataclass
class Line:
    text: str
    size: float = 0.0  # 0 when unknown (plain text)
    y: float = 0.0
    x: float = 0.0
    end_x: float = 0.0


def runs_to_lines(runs: Iterable[TextRun], page_width: float = 0.0) -> list[Line]:
    """Lines in reading order (see the module docstring). With ``page_width`` a two-column
    page is read column by column (``pdf_columns``); otherwise in content-stream order."""
    runs = list(runs)
    lines, wide = _joined(runs, None)
    # Only a page whose baselines hold gutter-wide gaps can have glued columns.
    if page_width and wide >= MIN_SIDE_LINES:
        ordered = column_lines(runs, page_width, _join)
        if ordered is not None:
            return ordered
    return lines


def _join(runs: Iterable[TextRun], max_gap: float | None = None) -> list[Line]:
    """Runs joined into lines by baseline; ``max_gap`` (font sizes) starts a new line at a
    wider gap between runs on the same baseline."""
    return _joined(runs, max_gap)[0]


def _joined(runs: Iterable[TextRun], max_gap: float | None) -> tuple[list[Line], int]:
    """``(lines, number of joins across a gap wider than GUTTER_GAP font sizes)``."""
    wide = 0
    lines: list[Line] = []
    cur: Line | None = None
    for run in runs:
        size = run.size or 1.0
        same_line = (
            cur is not None
            and abs(run.y - cur.y) <= 0.5 * max(1.0, min(size, cur.size or size))
            and run.x >= cur.end_x - 0.6 * size
            and (max_gap is None or run.x - cur.end_x <= max_gap * size)
        )
        if same_line and cur is not None:
            gap = run.x - cur.end_x
            if gap > GUTTER_GAP * size:
                wide += 1
            if (
                gap > SPACE_GAP * size
                and not cur.text.endswith(" ")
                and not run.text.startswith(" ")
            ):
                cur.text += " "
            cur.text += run.text
            cur.end_x = max(cur.end_x, run.end_x)
            cur.size = max(cur.size, size) if run.text.strip() else cur.size
        else:
            cur = Line(run.text, size if run.text.strip() else 0.0, run.y, run.x, run.end_x)
            lines.append(cur)
    out = []
    for line in lines:
        line.text = _SPACES.sub(" ", line.text).strip()
        if line.text:
            out.append(line)
    return out, wide


def lines_from_text(text: str) -> list[Line]:
    """Plain page text as lines (positions and sizes unknown)."""
    return [Line(_SPACES.sub(" ", ln).strip()) for ln in (text or "").splitlines() if ln.strip()]


def _key(text: str) -> str:
    return _DIGITS.sub("#", _SPACES.sub(" ", text.lower())).strip()


def _band(lines: list[Line]) -> list[Line]:
    if not lines:
        return []
    ordered = sorted(lines, key=lambda ln: -ln.y) if any(line.y for line in lines) else lines
    return ordered[:BAND_LINES] + ordered[-BAND_LINES:]


def _numbers(text: str) -> list[int]:
    return [int(d) for d in _DIGITS.findall(text)[:6] if len(d) < 7]


def _numbered_candidate(text: str) -> bool:
    """Short lines with a number, like ``Page 3 of 10`` or ``Annual Report | 17``."""
    return len(text) <= 40 and len(text.split()) <= 5 and bool(_DIGITS.search(text))


def remove_running_lines(
    pages: list[list[Line]], min_pages: int = 3, share: float = 0.5
) -> tuple[list[list[Line]], int]:
    """Pages without their running headers/footers; returns ``(pages, lines removed)``.

    A line in the top or bottom band of a page is a running line when the same text is in
    the band of at least ``share`` of the pages, or when it differs only by a number that
    follows the page number (``Page 3 of 10``, ``- 4 -``, ``Report 2024 | 17``).
    """
    if len(pages) < min_pages:
        return pages, 0
    needed = max(min_pages, math.ceil(share * len(pages)))
    exact: Counter[str] = Counter()
    offsets: dict[str, Counter[int]] = {}
    for number, lines in enumerate(pages, start=1):
        band = _band(lines)
        exact.update({_SPACES.sub(" ", line.text.lower()).strip() for line in band})
        for key in {_key(line.text) for line in band if _numbered_candidate(line.text)}:
            seen = {
                n - number for line in band if _key(line.text) == key for n in _numbers(line.text)
            }
            offsets.setdefault(key, Counter()).update(seen)
    running_exact = {key for key, count in exact.items() if count >= needed and key}
    running_numbered = {
        key for key, counts in offsets.items() if counts and max(counts.values()) >= needed
    }
    if not running_exact and not running_numbered:
        return pages, 0
    removed = 0
    out = []
    for lines in pages:
        band = {id(line) for line in _band(lines)}
        kept = [
            line
            for line in lines
            if not (
                id(line) in band
                and (
                    _SPACES.sub(" ", line.text.lower()).strip() in running_exact
                    or _key(line.text) in running_numbered
                )
            )
        ]
        removed += len(lines) - len(kept)
        out.append(kept)
    return out, removed


def heading_sizes(
    pages: Iterable[list[Line]], max_levels: int = 3
) -> tuple[float, dict[float, int]]:
    """``(body size, {rounded heading size: level})``; no headings when sizes are unknown or
    when "headings" would be most of the text."""
    weights: Counter[float] = Counter()
    lines_by_size: Counter[float] = Counter()
    total_lines = 0
    for lines in pages:
        for line in lines:
            if line.size > 0:
                size = round(line.size * 2) / 2
                weights[size] += len(line.text)
                lines_by_size[size] += 1
                total_lines += 1
    if not weights:
        return 0.0, {}
    body = weights.most_common(1)[0][0]
    larger = sorted((s for s in weights if s >= body * HEADING_RATIO), reverse=True)
    heading_lines = sum(lines_by_size[s] for s in larger)
    if not larger or heading_lines > 0.3 * total_lines:
        return body, {}
    return body, {size: min(i + 1, max_levels) for i, size in enumerate(larger)}


def _is_heading(line: Line, levels: dict[float, int]) -> int:
    if not levels or line.size <= 0:
        return 0
    level = levels.get(round(line.size * 2) / 2, 0)
    text = line.text
    if (
        not level
        or len(text) > 150
        or not any(c.isalpha() for c in text)
        or text.endswith((".", ",", ";"))
    ):
        return 0
    return level


def hyphenated_words(pages: Iterable[list[Line]]) -> frozenset[str]:
    """Lower-cased hyphenated compounds written on one line anywhere in the document
    (``user-level``): the same compound broken at its hyphen across a line keeps it."""
    found: set[str] = set()
    for lines in pages:
        for line in lines:
            if "-" in line.text:
                found.update(m.group(0).lower() for m in _COMPOUND.finditer(line.text))
    return frozenset(found)


def page_markdown(
    lines: list[Line], levels: dict[float, int], compounds: frozenset[str] = frozenset()
) -> tuple[str, list[tuple[int, str]]]:
    """``(Markdown text, [(level, heading)])`` of one page's lines. A word hyphenated at a
    line end is re-joined (``infor-`` / ``mation``) unless the document writes that
    hyphenated form elsewhere (``compounds`` from ``hyphenated_words``)."""
    out: list[str] = []
    headings: list[tuple[int, str]] = []
    prev: Line | None = None
    for line in lines:
        level = _is_heading(line, levels)
        if level:
            headings.append((level, line.text))
            out.append(("\n\n" if out else "") + "#" * level + " " + line.text + "\n\n")
            prev = None
            continue
        if prev is not None:
            height = max(prev.size, line.size, 1.0)
            gap = prev.y - line.y if prev.y and line.y else 0.0
            new_para = gap > 1.8 * height or gap < -height  # big drop, or a jump back up (column)
            out.append("\n\n" if new_para else "\n")
        elif out and not out[-1].endswith("\n"):
            out.append("\n")
        out.append(line.text)
        prev = line
    text = "".join(out)

    def join(m: re.Match[str]) -> str:
        if not m.group(2).islower():
            return m.group(0)
        if compounds:
            left = _WORD_END.search(text, max(0, m.start() - 63), m.start() + 1)
            right = _WORD_START.match(text, m.end() - 1)
            if left and right and f"{left.group(0)}-{right.group(0)}".lower() in compounds:
                return f"{m.group(1)}-{m.group(2)}"  # a real compound: keep its hyphen
        return m.group(1) + m.group(2)

    text = _HYPHEN.sub(join, text)
    return re.sub(r"\n{3,}", "\n\n", text).strip(), headings
