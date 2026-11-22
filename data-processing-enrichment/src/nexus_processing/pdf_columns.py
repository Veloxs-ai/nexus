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

"""Reading order of two-column pages (papers, newsletters, statements with side notes).

A PDF draws text in whatever order its producer chose. Many producers draw a two-column
page row by row, so joining runs by baseline glues the left and right columns into one
line ("left half of a sentence right half of another"). ``column_lines`` finds a vertical
gutter that body lines on both sides respect and returns the page's lines in reading
order: full-width lines (titles, figures' captions, footers) in place, and between them
the left column top to bottom, then the right column.

A page is treated as two columns only when the evidence is strong: both sides hold at
least a fifth of the text and several lines, most lines on each side fill their column
(prose, not a sparse table), and almost no text crosses the gutter. Otherwise it returns
None and the caller keeps the stream order.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

__all__ = ["column_lines"]

GUTTER_GAP = 1.5  # a gap wider than this (in font sizes) between runs on a baseline may be a gutter
MIN_SIDE_SHARE = 0.2  # each column holds at least this share of the page's characters
MIN_SIDE_LINES = 6
MAX_CROSSING_SHARE = 0.08  # characters on lines that cross the gutter (full-width lines)
FULL_LINE = 0.7  # a column line "fills" its column at this share of the column width
MIN_FULL_SHARE = 0.5  # share of a column's lines that must fill it (prose, not a table)


def _width(seg: Any) -> float:
    return seg.end_x - seg.x


def _gutter(segs: Sequence[Any]) -> float | None:
    total = sum(len(s.text) for s in segs) or 1
    x0, x1 = min(s.x for s in segs), max(s.end_x for s in segs)
    best: tuple[float, float] | None = None
    steps = 80
    for i in range(steps + 1):
        g = x0 + (x1 - x0) * (0.3 + 0.4 * i / steps)
        crossing = sum(len(s.text) for s in segs if s.x < g - 1 and s.end_x > g + 1)
        if best is None or crossing < best[0]:
            best = (crossing, g)
    if best is None or best[0] > MAX_CROSSING_SHARE * total:
        return None
    # Centre the gutter in the empty band around the best position.
    g = best[1]
    left_end = max((s.end_x for s in segs if s.end_x <= g + 1), default=g)
    right_start = min((s.x for s in segs if s.x >= g - 1), default=g)
    return (left_end + right_start) / 2 if right_start >= left_end else g


def _fills(side: Sequence[Any], lo: float, hi: float) -> bool:
    width = hi - lo
    if width <= 0:
        return False
    full = sum(1 for s in side if _width(s) >= FULL_LINE * width)
    return full >= MIN_FULL_SHARE * len(side)


def column_lines(
    runs: Sequence[Any], page_width: float, join: Callable[[Sequence[Any], float], list[Any]]
) -> list[Any] | None:
    """Lines of a two-column page in reading order, or None when the page is not one.

    ``join(runs, max_gap)`` joins runs into lines, starting a new line at gaps wider than
    ``max_gap`` font sizes (``pdf_layout._join``).
    """
    if not runs or page_width <= 0:
        return None
    segs = [s for s in join(runs, GUTTER_GAP) if s.text.strip()]
    if len(segs) < 2 * MIN_SIDE_LINES:
        return None
    g = _gutter(segs)
    if g is None:
        return None
    left = [s for s in segs if s.end_x <= g + 1]
    right = [s for s in segs if s.x >= g - 1 and s.end_x > g + 1]
    crossing = [s for s in segs if s.x < g - 1 and s.end_x > g + 1]
    total = sum(len(s.text) for s in segs) or 1
    for side in (left, right):
        if len(side) < MIN_SIDE_LINES or sum(len(s.text) for s in side) < MIN_SIDE_SHARE * total:
            return None
    if not _fills(left, min(s.x for s in left), g) or not _fills(
        right, g, max(s.end_x for s in right)
    ):
        return None
    # Full-width lines split the page into bands; each band reads left column, then right.
    cuts = sorted({round(s.y, 1) for s in crossing}, reverse=True)
    out: list[Any] = []

    def band(hi: float | None, lo: float | None) -> None:
        def inside(s: Any) -> bool:
            return (hi is None or s.y < hi) and (lo is None or s.y >= lo)

        for side in (left, right):
            out.extend(sorted((s for s in side if inside(s)), key=lambda s: (-s.y, s.x)))

    upper: float | None = None
    for cut in cuts:
        band(upper, cut)
        out.extend(sorted((s for s in crossing if round(s.y, 1) == cut), key=lambda s: s.x))
        upper = cut
    band(upper, None)
    return out
