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

"""Schema profiles of table records, and linking a question to the columns it needs.

``profile_records(records)`` reads every row once and describes each column (nested object
fields included, one level down)::

    {"v": 1, "rows": 200000, "columns": [
      {"name": "region", "path": ["region"], "type": "text", "nulls": 0, "null_pct": 0.0,
       "distinct": 4, "distinct_capped": false, "values_complete": true,
       "values": [["North", 50211], ...]},                 # every value, when there are few
      {"name": "amount", "path": ["amount"], "type": "number", ..., "top": [...],
       "min": 20.01, "max": 4999.98}, ...]}

Types: integer, number, date (ISO date or datetime text), boolean, text, object, array,
mixed (no kind reaches 95% of the non-blank values) and empty. Memory is bounded: distinct
values are tracked up to ``DISTINCT_CAP`` per column.

``profile_text`` renders a profile for a planner prompt; ``link_columns`` keeps the columns a
question is most likely about when many tables or columns are in scope.
"""

from __future__ import annotations

import re
from typing import Any

from .record_render import format_value
from .record_values import ISO_DATE_RE, NUMBER_RE, WS, normalize_value, text_of

__all__ = ["DISTINCT_CAP", "MAX_VALUES", "link_columns", "profile_records", "profile_text"]

PROFILE_VERSION = 1
DISTINCT_CAP = 1000  # distinct values tracked per column (memory bound)
MAX_VALUES = 50  # a column with at most this many distinct values lists them all
TOP_VALUES = 10
MAX_VALUE_CHARS = 120
MAX_COLUMNS = 200
MAJORITY = 0.95


class _Column:
    __slots__ = (
        "count",
        "date_max",
        "date_min",
        "kinds",
        "name",
        "num_max",
        "num_min",
        "overflow",
        "path",
        "present",
        "values",
    )

    def __init__(self, name: str, path: tuple[str, ...]):
        self.name, self.path = name, path
        self.present = 0  # non-blank values
        self.kinds: dict[str, int] = {}
        self.values: dict[str, int] = {}
        self.overflow = False
        self.num_min: float | None = None
        self.num_max: float | None = None
        self.date_min: str | None = None
        self.date_max: str | None = None
        self.count = 0

    def add(self, value: Any) -> None:
        kind = type(value)
        if value is None or (kind is str and not value.strip(WS)):
            return
        self.present += 1
        if kind is bool:
            k = "boolean"
        elif kind is int or kind is float:
            k = "integer" if kind is int else "number"
            self._number(float(value))
        elif kind is str:
            if NUMBER_RE.match(value):
                k = "number" if "." in value else "integer"
                self._number(float(value))
            elif ISO_DATE_RE.match(value.strip(WS)):
                k = "date"
                day = value.strip(WS)
                if self.date_min is None or day < self.date_min:
                    self.date_min = day
                if self.date_max is None or day > self.date_max:
                    self.date_max = day
            else:
                k = "text"
        elif kind is dict:
            k = "object"
        elif kind is list:
            k = "array"
        else:
            k = "text"
        self.kinds[k] = self.kinds.get(k, 0) + 1
        if k in ("object", "array"):
            return
        text = text_of(value)
        if text is None:
            return
        counts = self.values
        if text in counts:
            counts[text] += 1
        elif len(counts) < DISTINCT_CAP and len(text) <= MAX_VALUE_CHARS:
            counts[text] = 1
        else:
            self.overflow = True

    def _number(self, number: float) -> None:
        if self.num_min is None or number < self.num_min:
            self.num_min = number
        if self.num_max is None or number > self.num_max:
            self.num_max = number

    def kind(self) -> str:
        if not self.present:
            return "empty"
        kinds = dict(self.kinds)
        if "integer" in kinds and "number" in kinds:
            kinds["number"] += kinds.pop("integer")
        best, count = max(kinds.items(), key=lambda item: item[1])
        return best if count >= MAJORITY * self.present else "mixed"

    def describe(self, rows: int) -> dict[str, Any]:
        kind = self.kind()
        nulls = rows - self.present
        ranked = sorted(self.values.items(), key=lambda item: (-item[1], item[0]))
        complete = (
            not self.overflow and len(ranked) <= MAX_VALUES and kind not in ("object", "array")
        )
        out: dict[str, Any] = {
            "name": self.name,
            "path": list(self.path),
            "type": kind,
            "nulls": nulls,
            "null_pct": round(100.0 * nulls / rows, 2) if rows else 0.0,
            "distinct": len(ranked),
            "distinct_capped": self.overflow,
            "values_complete": complete,
        }
        if complete:
            out["values"] = [[t, n] for t, n in ranked]
        else:
            out["top"] = [
                [t, n] for t, n in ranked[:TOP_VALUES] if n > 1 or len(ranked) <= TOP_VALUES
            ]
        if kind in ("integer", "number") and self.num_min is not None:
            out["min"], out["max"] = self.num_min, self.num_max
        elif kind == "date" and self.date_min is not None:
            out["min"], out["max"] = self.date_min, self.date_max
        return out


def profile_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """The schema profile of ``records`` (see the module docstring)."""
    columns: dict[tuple[str, ...], _Column] = {}
    rows = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        rows += 1
        for key, value in record.items():
            path = (str(key),)
            column = columns.get(path)
            if column is None:
                if len(columns) >= MAX_COLUMNS:
                    continue
                column = columns[path] = _Column(str(key), path)
            column.add(value)
            if type(value) is dict:
                for sub, inner in value.items():
                    sub_path = (str(key), str(sub))
                    nested = columns.get(sub_path)
                    if nested is None:
                        if len(columns) >= MAX_COLUMNS:
                            continue
                        nested = columns[sub_path] = _Column(f"{key}.{sub}", sub_path)
                    nested.add(inner)
    return {
        "v": PROFILE_VERSION,
        "rows": rows,
        "columns": [c.describe(rows) for c in columns.values()],
    }


# ---------------------------------------------------------------------------
# Planner text and column linking
# ---------------------------------------------------------------------------
def _range(column: dict[str, Any]) -> str:
    low, high = column.get("min"), column.get("max")
    if low is None:
        return ""
    if column["type"] == "date":
        return f"{str(low)[:10]} to {str(high)[:10]}"
    return f"{format_value(low)} to {format_value(high)}"


def column_text(column: dict[str, Any], rows: int, values: int = 8) -> str:
    """``region (text; 4 values: East, North, South, West)``,
    ``amount (number; 20 to 4,999.98)``."""
    kind = column.get("type") or "text"
    parts = [kind]
    span = _range(column)
    if kind in ("integer", "number", "date") and span:
        parts.append(span)
    if kind == "integer" and column.get("distinct") == rows and not column.get("distinct_capped"):
        parts.append("unique")
    listed = column.get("values")
    if listed and kind not in ("integer", "number", "date"):
        shown = ", ".join(str(t) for t, _ in listed[:values])
        more = f" +{len(listed) - values} more" if len(listed) > values else ""
        parts.append(f"{len(listed)} value{'s' if len(listed) != 1 else ''}: {shown}{more}")
    elif column.get("top") and kind not in ("integer", "number", "date"):
        many = (
            f"{column['distinct']:,}+"
            if column.get("distinct_capped")
            else f"{column['distinct']:,}"
        )
        parts.append(
            f"{many} distinct; e.g. " + ", ".join(str(t)[:40] for t, _ in column["top"][:3])
        )
    if column.get("null_pct", 0) >= 1:
        parts.append(f"{column['null_pct']:.0f}% empty")
    return f"{column['name']} ({'; '.join(parts)})"


def profile_text(profile: dict[str, Any], columns: list[str] | None = None, values: int = 8) -> str:
    """The profile's columns (or only ``columns``) as one planner line (columns separated by
    `` | ``)."""
    keep = None if columns is None else {c.casefold() for c in columns}
    rows = int(profile.get("rows") or 0)
    shown = [
        column_text(c, rows, values)
        for c in profile.get("columns") or []
        if keep is None or str(c["name"]).casefold() in keep
    ]
    return " | ".join(shown)


_SPLIT = re.compile(r"[a-z]+|[0-9]+")
_CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])")


def _words(text: str) -> set[str]:
    words = set()
    for w in _SPLIT.findall(_CAMEL.sub(" ", str(text)).lower()):
        if len(w) >= 2:
            words.add(w[:-1] if len(w) > 3 and w.endswith("s") else w)
    return words


def link_columns(
    question: str,
    profiles: dict[str, dict[str, Any]],
    max_columns: int = 40,
    max_tables: int = 10,
    per_table: int = 3,
) -> dict[str, list[str]] | None:
    """The columns to show for each table when more than ``max_tables`` tables or ``max_columns``
    columns are in scope (None: show everything). A column is kept when its name shares a word
    with the question or the question contains one of its values; each table keeps its first
    ``per_table`` columns (keys and names usually come first), up to ``max_columns`` in all."""
    total = sum(len(p.get("columns") or []) for p in profiles.values())
    if len(profiles) <= max_tables and total <= max_columns:
        return None
    q_words = _words(question)
    q_norm = f" {normalize_value(question)} "
    scored: list[tuple[float, int, str, str]] = []
    out: dict[str, list[str]] = {}
    for table, profile in profiles.items():
        out[table] = []
        for position, column in enumerate(profile.get("columns") or []):
            name = str(column["name"])
            score = 3.0 * len(q_words & _words(name))
            for text, _ in column.get("values") or column.get("top") or []:
                norm = normalize_value(text)
                if len(norm) >= 3 and f" {norm} " in q_norm:
                    score += 2.0
                    break
            if position < per_table:
                score += 1.0 - position * 0.1
            if score > 0:
                scored.append((-score, position, table, name))
    scored.sort()
    for _, _, table, name in scored[:max_columns]:
        out[table].append(name)
    return out
