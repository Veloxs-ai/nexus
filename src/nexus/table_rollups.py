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

"""Rollups: exact answers to the common table questions without reading the rows.

``build_rollups(rows, profile)`` reads a table once and keeps, for every low-cardinality column
(at most ``max_groups`` values in the profile) and every date column by month, the row count of
each value and the count, exact sum, minimum and maximum of each numeric column::

    {"v": 1, "rows": 200000, "numbers": [["amount"], ...],
     "all": {...}, "columns": [{"path": ["region"], "kind": "value", "groups": [
        {"key": "north", "num": null, "rows": 50211, "labels": {"North": 50211},
         "m": {"amount": [50211, "1254880.12", 20.01, 4999.98, true]}}, ...]}, ...]}

It is plain JSON (sums are exact decimal strings), so it can be stored with the table's profile.
``apply_row_change(rollups, old, new)`` keeps it current when one row changes (a removed
minimum or maximum marks that value's min/max unknown rather than wrong); ``apply_row_changes``
does the same for a batch of ``(old, new)`` pairs.

``answer_from_rollups(query, rollups)`` answers a resolved ``RecordQuery`` (``nexus.record_spec``)
when it is a count / sum / avg / min / max (or count_distinct of the filtered column) over the
whole table, filtered by conditions on one rolled column, or grouped by one rolled column (or a
date column by month) with conditions on that column only; it returns the same ``RecordResult``
as ``nexus.record_eval`` and ``nexus.record_sql``, or None when the rollups cannot answer exactly.
The caller must only pass rollups built from the current rows.
"""

from __future__ import annotations

import decimal
from collections.abc import Iterable, Mapping
from functools import cmp_to_key
from typing import Any

from .record_eval import _nulls_last, _test, _test_metric, bucket
from .record_render import RecordResult, render
from .record_spec import Order, RecordQuery
from .record_values import WS, fold, number_of, text_of
from .table_rollups_build import accumulate

__all__ = [
    "ROLLUP_VERSION",
    "answer_from_rollups",
    "apply_row_change",
    "apply_row_changes",
    "build_rollups",
]

ROLLUP_VERSION = 1
MAX_GROUPS = 50
MAX_MONTHS = 600
MAX_NUMBERS = 20
_CTX = decimal.Context(prec=60)
_NUMERIC = ("integer", "number")


def _get(record: Any, path: tuple[str, ...]) -> Any:
    for key in path:
        if not isinstance(record, dict):
            return None
        record = record.get(key)
    return record


def _exact(value: Any) -> decimal.Decimal | None:
    """The exact decimal of a value's number (its text, as PostgreSQL's numeric reads it)."""
    if number_of(value) is None:
        return None
    if isinstance(value, str):
        return decimal.Decimal(value.strip(WS))
    return decimal.Decimal(repr(value) if isinstance(value, float) else value)


def _name(path: tuple[str, ...] | list[str]) -> str:
    return ".".join(path)


def _entry(key: Any, num: float | None) -> dict[str, Any]:
    return {"key": key, "num": num, "rows": 0, "labels": {}, "m": {}}


def _measure(row: Any, numbers: list[tuple[str, tuple[str, ...]]]) -> list[tuple]:
    """(name, number, exact decimal) of each numeric column with a number in ``row``."""
    out = []
    for name, path in numbers:
        value = _get(row, path)
        exact = _exact(value)
        if exact is not None:
            out.append((name, number_of(value), exact))
    return out


def _add(entry: dict[str, Any], label: str | None, measured: list[tuple], sign: int) -> None:
    entry["rows"] += sign
    if label:
        labels = entry["labels"]
        labels[label] = labels.get(label, 0) + sign
        if not labels[label]:
            del labels[label]
    for name, number, exact in measured:
        stats = entry["m"].get(name)
        if stats is None:
            stats = entry["m"][name] = [0, decimal.Decimal(0), None, None, True]
        stats[0] += sign
        total = stats[1] if type(stats[1]) is decimal.Decimal else decimal.Decimal(stats[1])
        stats[1] = _CTX.add(total, exact) if sign > 0 else _CTX.subtract(total, exact)
        if sign > 0:
            if stats[4]:
                stats[2] = number if stats[2] is None else min(stats[2], number)
                stats[3] = number if stats[3] is None else max(stats[3], number)
        elif not stats[0]:  # no value left: an empty range is known again
            stats[2], stats[3], stats[4] = None, None, True
        elif number in (stats[2], stats[3]):
            stats[4] = False  # a removed extreme: unknown until the rollups are rebuilt


def _key(column: Mapping[str, Any], row: Any) -> tuple[Any, float | None, str | None]:
    raw = _get(row, tuple(column["path"]))
    text = text_of(raw)
    if column["kind"] == "month":
        return bucket(text, "month"), None, None
    folded = fold(text)
    return folded, number_of(raw), (text.strip(WS) if folded else None)


def _indexes(rollups: dict[str, Any]) -> list[dict[Any, dict[str, Any]]]:
    return [{g["key"]: g for g in column["groups"]} for column in rollups["columns"]]


def _change(
    rollups: dict[str, Any], row: Any, sign: int, indexes: list[dict[Any, dict[str, Any]]]
) -> None:
    numbers = [(_name(p), tuple(p)) for p in rollups["numbers"]]
    measured = _measure(row, numbers)
    rollups["rows"] += sign
    _add(rollups["all"], None, measured, sign)
    for column, index in zip(rollups["columns"], indexes, strict=True):
        if not column.get("exact", True):
            continue
        key, num, label = _key(column, row)
        entry = index.get(key)
        if entry is None:
            cap = MAX_MONTHS if column["kind"] == "month" else column.get("max_groups", MAX_GROUPS)
            if sign < 0 or len(index) >= cap:
                column["exact"] = False  # unknown value or too many: no longer answerable
                continue
            entry = index[key] = _entry(key, num)
            column["groups"].append(entry)
        elif entry["num"] != num:
            column["exact"] = False  # one folded text, two numbers ("1e3" / 1000.0): give up
            continue
        _add(entry, label, measured, sign)
        if not entry["rows"]:
            column["groups"].remove(entry)
            del index[key]


def _as_json(rollups: dict[str, Any]) -> dict[str, Any]:
    """Exact sums as decimal strings (plain JSON)."""
    for entry in [rollups["all"], *(g for c in rollups["columns"] for g in c["groups"])]:
        for stats in entry["m"].values():
            if type(stats[1]) is decimal.Decimal:
                stats[1] = str(stats[1])
    return rollups


def build_rollups(
    rows: Iterable[dict[str, Any]],
    profile: Mapping[str, Any],
    max_groups: int = MAX_GROUPS,
    max_numbers: int = MAX_NUMBERS,
) -> dict[str, Any]:
    """Rollups of ``rows`` for the columns ``profile`` (``nexus.table_profile``) lists: value
    columns with every value known and at most ``max_groups`` of them, date columns by month,
    and up to ``max_numbers`` numeric columns measured per group."""
    columns, numbers = [], []
    for column in profile.get("columns") or []:
        path = [str(p) for p in column.get("path") or [column["name"]]]
        kind = column.get("type")
        if kind in _NUMERIC and len(numbers) < max_numbers:
            numbers.append(path)
        if kind == "date":
            columns.append({"path": path, "kind": "month", "groups": [], "exact": True})
        if (
            column.get("values_complete")
            and kind not in ("object", "array")
            and int(column.get("distinct") or 0) <= max_groups
        ):
            columns.append(
                {
                    "path": path,
                    "kind": "value",
                    "groups": [],
                    "exact": True,
                    "max_groups": max_groups,
                }
            )
    out: dict[str, Any] = {
        "v": ROLLUP_VERSION,
        "rows": 0,
        "numbers": numbers,
        "all": _entry(None, None),
        "columns": columns,
    }
    caps = [
        MAX_MONTHS if c["kind"] == "month" else c.get("max_groups", MAX_GROUPS) for c in columns
    ]
    # the same result as _change per row (apply_row_change), computed in blocks
    accumulate(out, rows, caps=caps, key_of=_key, new_entry=_entry, context=_CTX)
    return _as_json(out)


def apply_row_change(
    rollups: dict[str, Any], old: dict[str, Any] | None, new: dict[str, Any] | None
) -> dict[str, Any]:
    """Update ``rollups`` in place for one row replaced (``old`` -> ``new``), inserted (``old``
    None) or deleted (``new`` None); returns it. A column that gets a value it cannot hold
    (more than its group cap, or a new value on delete) stops answering until rebuilt."""
    return apply_row_changes(rollups, [(old, new)])


def apply_row_changes(
    rollups: dict[str, Any], changes: Iterable[tuple[dict[str, Any] | None, dict[str, Any] | None]]
) -> dict[str, Any]:
    """``apply_row_change`` for many ``(old, new)`` pairs in order (one index build and one JSON
    conversion for the whole batch); returns ``rollups``."""
    indexes = _indexes(rollups)
    for old, new in changes:
        if isinstance(old, dict):
            _change(rollups, old, -1, indexes)
        if isinstance(new, dict):
            _change(rollups, new, 1, indexes)
    return _as_json(rollups)


# ---------------------------------------------------------------------------
# Answering
# ---------------------------------------------------------------------------
def _fields_of(c: Any) -> set[int]:
    if c is None:
        return set()
    if c.op in ("and", "or", "not"):
        return set().union(*(_fields_of(i) for i in c.items)) if c.items else set()
    return {c.index}


def _column(rollups: Mapping[str, Any], path: tuple[str, ...], kind: str) -> Any:
    for column in rollups.get("columns") or []:
        if tuple(column["path"]) == path and column["kind"] == kind:
            return column if column.get("exact", True) else None
    return None


def _metric(op: str, entries: list[dict[str, Any]], name: str | None) -> tuple[bool, Any]:
    """(answerable, value) of a metric over ``entries``."""
    if op == "count":
        return True, sum(e["rows"] for e in entries)
    if op == "count_distinct":
        return True, sum(1 for e in entries if e["key"])
    stats = [e["m"][name] for e in entries if name in e["m"] and e["m"][name][0]]
    if not stats:
        return True, None
    if op in ("min", "max"):
        if not all(s[4] for s in stats):
            return False, None
        return True, (min(s[2] for s in stats) if op == "min" else max(s[3] for s in stats))
    total = sum((decimal.Decimal(s[1]) for s in stats), decimal.Decimal(0))
    if op == "sum":
        return True, float(total)
    return True, float(total) / sum(s[0] for s in stats)


def _metrics(q: RecordQuery, entries: list[dict[str, Any]]) -> list[Any] | None:
    out = []
    for m in q.metrics:
        name = _name(q.fields[m.index].path) if m.index >= 0 else None
        ok, value = _metric(m.op, entries, name)
        if not ok:
            return None
        out.append(value)
    return out


def _supported(q: RecordQuery, rollups: Mapping[str, Any]) -> bool:
    if q.join is not None or q.mode not in ("scalar", "group") or not q.metrics:
        return False
    measured = {tuple(p) for p in rollups.get("numbers") or []}
    for m in q.metrics:
        if m.op in ("sum", "avg", "min", "max") and (
            m.text or tuple(q.fields[m.index].path) not in measured
        ):
            return False
        if m.op not in ("count", "count_distinct", "sum", "avg", "min", "max"):
            return False
    return all(f.side == "base" for f in q.fields)


def _where_entries(q: RecordQuery, column: Any, index: int) -> list[dict[str, Any]]:
    out = []
    for entry in column["groups"]:
        values: list[Any] = [(None, None, None)] * len(q.fields)
        values[index] = (None, entry["num"], entry["key"])
        if q.where is None or _test(q.where, values):
            out.append(entry)
    return out


def answer_from_rollups(
    query: RecordQuery, rollups: Mapping[str, Any] | None
) -> RecordResult | None:
    """The ``RecordResult`` of ``query`` from ``rollups``, or None when they cannot answer it
    exactly (see the module docstring)."""
    if not rollups or rollups.get("v") != ROLLUP_VERSION:
        return None
    q, total = query, int(rollups["rows"])
    if q.impossible:
        return render(q, total)
    if not _supported(q, rollups):
        return None
    filtered = _fields_of(q.where)
    if len(filtered) > 1:
        return None
    distinct = {m.index for m in q.metrics if m.op == "count_distinct"}
    if q.mode == "scalar":
        if not filtered and not distinct:
            values = _metrics(q, [rollups["all"]])
            return None if values is None else render(q, total, total, [values])
        index = next(iter(filtered | distinct))
        if (filtered | distinct) != {index}:
            return None
        column = _column(rollups, tuple(q.fields[index].path), "value")
        if column is None:
            return None
        entries = _where_entries(q, column, index)
        values = _metrics(q, entries)
        if values is None:
            return None
        return render(q, total, sum(e["rows"] for e in entries), [values])
    if len(q.groups) != 1:
        return None
    g = q.groups[0]
    if g.trunc not in (None, "month") or not filtered <= {g.index} or not distinct <= {g.index}:
        return None
    if g.trunc and (filtered or distinct):
        return None
    column = _column(rollups, tuple(q.fields[g.index].path), g.trunc or "value")
    if column is None:
        return None
    merged: dict[Any, list[dict[str, Any]]] = {}
    for entry in _where_entries(q, column, g.index):
        merged.setdefault(entry["key"] or None, []).append(entry)  # "" and null: one group
    out, kept = [], 0
    for key, entries in merged.items():
        if key is None:
            label = None
        elif g.trunc:
            label = key
        else:
            label = max(t for e in entries for t, n in e["labels"].items() if n > 0)
        values = _metrics(q, entries)
        if values is None:
            return None
        if q.having is None or _test_metric(q.having, values):
            out.append([label, *values])
            kept += sum(e["rows"] for e in entries)
    orders = q.order or [Order("metric", 0, True)]

    def compare(a: list[Any], b: list[Any]) -> int:
        for o in orders:
            column_at = o.index if o.kind == "group" else 1 + o.index
            result = _nulls_last(a[column_at], b[column_at], o.desc)
            if result:
                return result
        return _nulls_last(a[0], b[0], False)

    out.sort(key=cmp_to_key(compare))
    return render(q, total, kept, out[: q.limit], len(out))
