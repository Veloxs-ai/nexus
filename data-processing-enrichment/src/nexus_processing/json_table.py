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

"""JSON documents as tables: the record array inside an API dump becomes rows.

Most JSON files indexed for retrieval are exports: ``{"data": [...200 records...],
"meta": {...}}``, ``{"results": {"items": [...]}}`` or a bare ``[...]``. Chunking them as
pretty-printed text gives one huge chunk (or one chunk per record) with no records to
count or total, and ``indent=2`` spends ~40% of the characters on spaces.

``json_table`` finds the **largest array of objects at any depth**, flattens each object
to dotted keys (``customer.name``) and returns it as rows, plus the remaining scalar
fields as ``key.path: value`` context lines. Callers chunk the rows like CSV rows (with
``csv_table.group_rows``) and attach them as ``metadata.records``. ``compact_json`` is
the token-cheap serialisation for everything else.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "JsonTable",
    "compact_json",
    "find_record_array",
    "flatten_json",
    "json_table",
    "parse_json",
]

MIN_ROWS = 2
MAX_FLATTEN_DEPTH = 4
MAX_CONTEXT_LINES = 200
_SCALARS = (str, int, float, bool)


@dataclass
class JsonTable:
    """Rows of the largest record array of a JSON document."""

    path: str  # where the array is: "data[]", "results.items[]", "[]"
    columns: list[str]
    rows: list[dict[str, Any]] = field(default_factory=list)
    context: list[str] = field(default_factory=list)  # "key.path: value" for the other fields


def parse_json(text: str) -> Any:
    """``json.loads`` that tolerates a Markdown code fence around the payload; raises
    ``ValueError`` when the text is not JSON."""
    cleaned = text.strip().lstrip("﻿")
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def compact_json(value: Any) -> str:
    """Single-line JSON without padding (non-ASCII kept as is)."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _is_record_array(value: Any) -> bool:
    if not isinstance(value, list) or len(value) < MIN_ROWS:
        return False
    objects = sum(1 for v in value if isinstance(v, dict))
    return objects >= 0.8 * len(value)


def find_record_array(data: Any, path: str = "") -> tuple[str, list[dict[str, Any]]] | None:
    """``(path, objects)`` of the largest array of objects in ``data`` (``None`` if none).

    Size is the number of objects; on a tie the shallower array wins.
    """
    best: tuple[str, list[dict[str, Any]]] | None = None

    def visit(value: Any, where: str, depth: int) -> None:
        nonlocal best
        if depth > 8:
            return
        if _is_record_array(value):
            objects = [v for v in value if isinstance(v, dict)]
            if best is None or len(objects) > len(best[1]):
                best = (f"{where}[]", objects)
            return  # records inside records are columns of the outer rows
        if isinstance(value, dict):
            for key, child in value.items():
                visit(child, f"{where}.{key}" if where else str(key), depth + 1)
        elif isinstance(value, list):
            for child in value[:50]:
                visit(child, f"{where}[]", depth + 1)

    visit(data, path, 0)
    return best


def flatten_json(
    value: Any, prefix: str = "", max_depth: int = MAX_FLATTEN_DEPTH
) -> dict[str, Any]:
    """Nested objects -> dotted keys; lists of scalars are joined with ", "; deeper or
    mixed structures are kept as compact JSON text."""
    out: dict[str, Any] = {}
    # One explicit stack instead of a call per node; children are pushed in reverse so
    # keys come out in document order, exactly as the recursive walk produced them.
    stack: list[tuple[Any, str, int]] = [(value, prefix, 0)]
    pop, push = stack.pop, stack.append
    while stack:
        node, key, depth = pop()
        if isinstance(node, dict):
            if node and depth < max_depth:
                base = key + "." if key else ""
                for k, v in reversed(node.items()):
                    push((v, f"{base}{k}", depth + 1))
            else:
                out[key] = compact_json(node) if node else None
        elif isinstance(node, list):
            if all(v is None or isinstance(v, _SCALARS) for v in node):
                out[key] = ", ".join(str(v) for v in node if v is not None)
            else:
                out[key] = compact_json(node)
        else:
            out[key] = node
    return out


def _record_lines(items: list[Any], key: str) -> list[str]:
    out = [f"{key}: {len(items)} records"]
    for number, item in enumerate(items, start=1):
        if isinstance(item, dict):
            fields = flatten_json(item)
            body = " | ".join(f"{k}: {v}" for k, v in fields.items() if v is not None and v != "")
        else:
            body = compact_json(item)
        out.append(f"{key}[{number}] {body}")
    return out


def _context_lines(data: Any, skip_path: str) -> list[str]:
    lines: list[str] = []
    records: list[str] = []  # other record arrays, after the scalar fields

    def walk(node: Any, key: str) -> None:
        if len(lines) >= MAX_CONTEXT_LINES:
            return
        if f"{key}[]" == skip_path:
            return
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{key}.{k}" if key else str(k))
        elif isinstance(node, list):
            if all(v is None or isinstance(v, _SCALARS) for v in node):
                if node:
                    lines.append(f"{key}: {', '.join(str(v) for v in node if v is not None)}")
            elif _is_record_array(node):
                # Another record array: one readable line per record (never one multi-MB
                # JSON line), every record kept.
                records.extend(_record_lines(node, key))
            else:
                lines.append(f"{key}: {compact_json(node)}")
        elif node is not None and node != "":
            lines.append(f"{key}: {node}")

    walk(data, "")
    return lines + records


def json_table(source: str | Any, min_rows: int = MIN_ROWS) -> JsonTable | None:
    """The largest record array of a JSON document as rows (``None`` when there is none or
    the text is not JSON)."""
    if isinstance(source, str):
        try:
            data = parse_json(source)
        except ValueError:
            return None
    else:
        data = source
    found = find_record_array(data)
    if found is None or len(found[1]) < min_rows:
        return None
    path, objects = found
    rows = [flatten_json(obj) for obj in objects]
    columns: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                columns.append(key)
    return JsonTable(path=path, columns=columns, rows=rows, context=_context_lines(data, path))
