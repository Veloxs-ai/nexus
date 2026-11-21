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

"""Re-joining adjacent chunks into one passage.

Chunkers repeat context on purpose: ``chunk_markdown`` prefixes every chunk with its
``Section: A > B`` breadcrumb and overlaps consecutive chunks; ``token_budget.fit_text``
repeats a ``Columns: ...``, ``[...]`` or Markdown table header on every part. When a
reader puts consecutive chunks back together (a passage of neighbours, a section of an
outline), those repeats are noise. ``join_adjacent`` removes them; ``stitch`` joins a run.
"""

from __future__ import annotations

from collections.abc import Iterable

from .token_budget import split_header

__all__ = ["join_adjacent", "stitch"]


def join_adjacent(prev: str, nxt: str, *, max_overlap: int = 300, min_overlap: int = 21) -> str:
    """``prev`` followed by ``nxt`` without ``nxt``'s repeated header and the overlap.

    The repeated header is any header ``split_header`` recognises (``Section:``,
    ``Columns:``, a leading ``[...]`` tag, a Markdown table header) when ``prev`` starts
    with the same header. The overlap is the longest suffix of ``prev`` (``min_overlap``
    to ``max_overlap`` characters) that starts ``nxt``.
    """
    header, _sep, body = split_header(nxt)
    if header and prev.startswith(header):
        nxt = body
    for size in range(min(max_overlap, len(prev), len(nxt)), min_overlap - 1, -1):
        if prev.endswith(nxt[:size]):
            return prev + nxt[size:]
    return prev + "\n" + nxt


def stitch(texts: Iterable[str], *, max_overlap: int = 300) -> str:
    """Join consecutive chunk texts with ``join_adjacent``."""
    out: str | None = None
    for text in texts:
        out = text if out is None else join_adjacent(out, text, max_overlap=max_overlap)
    return out or ""
