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

"""Bounds for very large rows and documents.

``cap_record_values(record, max_chars)`` cuts long text values of a row record (the record a
chunk carries for exact table answers) and says what it cut in a marker key, so a row with a
5 MB cell does not put 5 MB of JSON on a chunk; the full text stays in the chunk texts, which
are searchable. ``cap_document(chunks, max_chars)`` keeps a document's chunks up to a total
number of characters and reports what it left out, instead of doing unbounded work.
"""

from __future__ import annotations

from typing import Any

__all__ = ["DEFAULT_RECORD_CHARS", "TRUNCATED_KEY", "cap_document", "cap_record_values"]

DEFAULT_RECORD_CHARS = 4000
TRUNCATED_KEY = "_truncated"


def _cap(value: Any, max_chars: int, path: str, cut: dict[str, int]) -> Any:
    if isinstance(value, str):
        if len(value) > max_chars:
            cut[path] = len(value)
            return value[:max_chars]
        return value
    if isinstance(value, dict):
        out = None
        for key, inner in value.items():
            capped = _cap(inner, max_chars, f"{path}.{key}" if path else str(key), cut)
            if capped is not inner:
                if out is None:
                    out = dict(value)
                out[key] = capped
        return value if out is None else out
    if isinstance(value, list):
        items = None
        for i, inner in enumerate(value):
            capped = _cap(inner, max_chars, f"{path}.{i}" if path else str(i), cut)
            if capped is not inner:
                if items is None:
                    items = list(value)
                items[i] = capped
        return value if items is None else items
    return value


def cap_record_values(
    record: dict[str, Any],
    max_chars: int = DEFAULT_RECORD_CHARS,
    *,
    marker: str = TRUNCATED_KEY,
) -> dict[str, Any]:
    """``record`` with every text value longer than ``max_chars`` cut to its first
    ``max_chars`` characters, at any depth (objects and lists), plus
    ``record[marker] = {"field.path": original length}`` for what was cut (merged with a
    marker already there). The record is returned as is (same object) when nothing is cut;
    otherwise only the changed objects are copied, the caller's record is not modified."""
    if not isinstance(record, dict) or max_chars is None or max_chars < 0:
        return record
    limit = int(max_chars)
    for value in record.values():  # the common flat row with short values: nothing to cut
        if isinstance(value, (dict, list)) or (isinstance(value, str) and len(value) > limit):
            break
    else:
        return record
    cut: dict[str, int] = {}
    capped = _cap(record, int(max_chars), "", cut)  # the marker holds numbers only
    if not cut:
        return record
    previous = record.get(marker)
    capped[marker] = {**(previous if isinstance(previous, dict) else {}), **cut}
    return capped


def cap_document(
    chunks: list[dict[str, Any]],
    max_chars: int | None,
    *,
    text_key: str = "text",
    metadata_key: str = "metadata",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The leading ``chunks`` whose texts total at most ``max_chars`` characters, and a report
    ``{"truncated", "chars", "kept_chars", "dropped_chunks"}``. The chunk that crosses the
    limit keeps its first characters up to the limit and gets ``metadata["truncated"] = True``;
    later chunks are left out. ``max_chars`` None (or no excess) returns ``chunks`` unchanged."""
    lengths = [len(str(c.get(text_key) or "")) for c in chunks]
    total = sum(lengths)
    report: dict[str, Any] = {
        "truncated": False,
        "chars": total,
        "kept_chars": total,
        "dropped_chunks": 0,
    }
    if max_chars is None or total <= max_chars:
        return chunks, report
    kept: list[dict[str, Any]] = []
    room = max(0, int(max_chars))
    for chunk, length in zip(chunks, lengths, strict=True):
        if room <= 0:
            break
        if length <= room:
            kept.append(chunk)
            room -= length
            continue
        meta = chunk.get(metadata_key)
        part = dict(chunk)
        part[text_key] = str(chunk.get(text_key) or "")[:room]
        part[metadata_key] = {**(meta if isinstance(meta, dict) else {}), "truncated": True}
        kept.append(part)
        room = 0
    report.update(
        truncated=True,
        kept_chars=sum(len(str(c.get(text_key) or "")) for c in kept),
        dropped_chunks=len(chunks) - len(kept),
    )
    return kept, report
