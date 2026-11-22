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

"""Typed slot columns for a table that stores one row per record.

A records table can keep, next to each row's JSON record, a few typed columns ("slots") holding
the values of its most queried fields, so ``nexus.record_sql`` reads them instead of parsing the
JSON (``ChunkTable(layout="row", columns=slot_columns(slot_map))``). The caller names the slot
columns; nothing here knows the table.

* ``plan_slots(profile, text=8, number=8, date=4)`` picks the fields for the slots of one table
  from its ``nexus.table_profile`` profile (keys and categories first, then the fullest columns).
* ``slot_values(record, slot_map)`` gives the slot values to store with a record.

Exactness: a slot holds a value only when the SQL can give back exactly the text the JSON
holds; otherwise the slot is NULL and the statement reads that row's JSON (per row, so results
never change, only speed). Text slots hold any scalar's text; number slots hold integers below
2**53 and decimals written in their shortest form with at most 13 significant digits and
at least 0.001 in size (``"300"``, ``300``, ``"12.5"``; not ``"12.50"``, ``1e20``,
``0.0001``); date slots hold ``YYYY-MM-DD`` and ``YYYY-MM-DDTHH:MM:SSZ`` values as a UTC
timestamp text (``YYYY-MM-DDTHH:MM:SSZ``).

Column types: PostgreSQL ``TEXT`` / ``NUMERIC`` (or ``double precision``) / ``TIMESTAMPTZ``;
SQLite ``TEXT`` / ``NUMERIC`` (or ``REAL``) / ``TEXT``.
"""

from __future__ import annotations

import datetime as _dt
import re
from collections.abc import Iterable, Mapping
from typing import Any

from .record_values import NUMBER_RE
from .table_profile import key_like

__all__ = [
    "SLOT_KINDS",
    "date_slot",
    "number_slot",
    "plan_slots",
    "slot_columns",
    "slot_values",
    "text_slot",
]

SLOT_KINDS = ("text", "number", "date")
SLOT_VERSION = 1
_CANON_NUMBER = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$")
_DATE_ONLY = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_DATE_TIME = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_NUMERIC_TYPES = ("integer", "number")
_SKIP_TYPES = ("object", "array", "empty")
FILL = 0.9  # share of sampled values a number/date slot must hold (else a text slot)


def text_slot(value: Any) -> str | None:
    """The text slot value of a JSON value: its text as the records engines read it, for
    strings, booleans, integers and finite decimals without an exponent (None otherwise)."""
    kind = type(value)
    if kind is str:
        return value
    if kind is bool:
        return "true" if value else "false"
    if kind is int:
        return str(value)
    if kind is float:
        text = repr(value)
        return text if NUMBER_RE.match(text) else None
    return None


def number_slot(value: Any) -> int | float | None:
    """The number slot value of a JSON value whose text is a number in its shortest form
    (see the module docstring), else None."""
    kind = type(value)
    if kind is int:
        return value if abs(value) < 2**53 else None
    if kind is float:
        if value - value != 0.0:  # inf / nan
            return None
        text = repr(value)
    elif kind is str:
        text = value
    else:
        return None
    if not _CANON_NUMBER.match(text) or text == "-0":
        return None
    digits = text.lstrip("-").replace(".", "").lstrip("0")
    if "." not in text:
        number = int(text)
        return number if abs(number) < 2**53 else None
    whole = text.lstrip("-").split(".", 1)[0]
    # what every engine renders back unchanged: at most 13 significant digits, |x| >= 0.001
    # (SQLite prints some longer or smaller decimals with more digits than they were written)
    if len(digits) > 13 or (whole == "0" and len(text.lstrip("-")) - len(digits) - 2 > 2):
        return None
    return float(text)


def date_slot(value: Any) -> str | None:
    """The date slot value (``YYYY-MM-DDTHH:MM:SSZ``, UTC) of a ``YYYY-MM-DD`` or
    ``YYYY-MM-DDTHH:MM:SSZ`` text that is a real date (a midnight datetime text is not
    slotted: it would read back as a date)."""
    if type(value) is not str:
        return None
    if _DATE_ONLY.match(value):
        try:
            _dt.date.fromisoformat(value)
        except ValueError:
            return None
        return f"{value}T00:00:00Z"
    if _DATE_TIME.match(value) and value[11:19] != "00:00:00":
        try:
            _dt.datetime.fromisoformat(value[:19])
        except ValueError:
            return None
        return value
    return None


_SLOT_OF = {"text": text_slot, "number": number_slot, "date": date_slot}


def _get(record: Any, path: tuple[str, ...]) -> Any:
    for key in path:
        if not isinstance(record, dict):
            return None
        record = record.get(key)
    return record


def _fill(sample: list[dict[str, Any]], path: tuple[str, ...], kind: str) -> float:
    values = [v for v in (_get(r, path) for r in sample) if v is not None and v != ""]
    if not values:
        return 1.0
    slot = _SLOT_OF[kind]
    return sum(1 for v in values if slot(v) is not None) / len(values)


def plan_slots(
    profile: Mapping[str, Any],
    text: int = 8,
    number: int = 8,
    date: int = 4,
    *,
    sample: Iterable[dict[str, Any]] | None = None,
    names: Mapping[str, str] | None = None,
    exclude: Iterable[str] = (),
) -> dict[str, Any]:
    """The slot map of one table: ``{"v": 1, "slots": [{"path", "name", "kind", "column"}]}``.

    Columns are taken from the profile in priority order: key-like columns (a value per row),
    then categories (every value listed), then the others, fewer empty values first; nested
    objects, arrays, empty columns and ``exclude`` names are skipped. Number and date columns
    get number/date slots (``number`` / ``date`` of them), the rest text slots (``text``); a
    number or date column that does not fit (``sample`` records show that fewer than 90% of its
    values can be held exactly, or its kind is full) takes a free text slot, which holds any
    scalar exactly. ``names`` maps a kind to its column prefix (default ``t``, ``n``, ``d``:
    columns ``t1`` .. ``t8``, ``n1`` .. ``n8``, ``d1`` .. ``d4``)."""
    prefix = {"text": "t", "number": "n", "date": "d", **(names or {})}
    room = {"text": max(0, int(text)), "number": max(0, int(number)), "date": max(0, int(date))}
    used = dict.fromkeys(SLOT_KINDS, 0)
    rows = int(profile.get("rows") or 0)
    skip = {str(x).casefold() for x in exclude}
    rows_sample = list(sample or [])
    ranked = []
    for position, column in enumerate(profile.get("columns") or []):
        kind = column.get("type")
        if kind in _SKIP_TYPES or str(column.get("name", "")).casefold() in skip:
            continue
        tier = 0 if key_like(column, rows) else 1 if column.get("values_complete") else 2
        ranked.append((tier, float(column.get("null_pct") or 0.0), position, column))
    ranked.sort(key=lambda item: item[:3])
    slots = []
    for _, _, _, column in ranked:
        path = tuple(str(p) for p in column.get("path") or [column["name"]])
        want = (
            "number"
            if column["type"] in _NUMERIC_TYPES
            else "date"
            if column["type"] == "date"
            else "text"
        )
        if want != "text" and rows_sample and _fill(rows_sample, path, want) < FILL:
            want = "text"
        if want != "text" and used[want] >= room[want]:
            want = "text"
        if used[want] >= room[want]:
            continue
        used[want] += 1
        slots.append(
            {
                "path": list(path),
                "name": str(column["name"]),
                "kind": want,
                "column": f"{prefix[want]}{used[want]}",
            }
        )
    return {"v": SLOT_VERSION, "rows": rows, "slots": slots}


def slot_values(record: Mapping[str, Any], slot_map: Mapping[str, Any]) -> dict[str, Any]:
    """``{column: value}`` for every slot of ``slot_map`` (None where the record's value cannot
    be held exactly, or is missing: the statement then reads the JSON for that row)."""
    out: dict[str, Any] = {}
    for slot in slot_map.get("slots") or []:
        value = _get(record, tuple(slot["path"]))
        out[slot["column"]] = None if value is None else _SLOT_OF[slot["kind"]](value)
    return out


def slot_columns(slot_map: Mapping[str, Any] | None) -> dict[tuple[str, ...], tuple[str, str]]:
    """The ``ChunkTable.columns`` map of a slot map: ``{field path: (column, kind)}``."""
    return {
        tuple(slot["path"]): (str(slot["column"]), str(slot["kind"]))
        for slot in (slot_map or {}).get("slots") or []
    }
