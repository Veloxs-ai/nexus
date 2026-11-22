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

"""Records queries evaluated in Python over records in memory (the reference engine).

``query_records(records, spec)`` answers a records spec over a list of row dicts: it profiles
the rows (``nexus.table_profile``), resolves the spec (``nexus.record_spec``) and evaluates it
here. ``evaluate`` takes an already resolved ``RecordQuery``. The SQL engine
(``nexus.record_sql``) has the same semantics; this one is its oracle in tests and the engine
for records that are not in a database.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Iterable
from functools import cmp_to_key
from typing import Any

from .record_render import RecordResult, render
from .record_spec import Cond, Field, Order, RecordQuery, parse_spec
from .record_values import ISO_DATE_RE, WS, fold, key_text, number_of, text_of
from .table_profile import profile_records

__all__ = ["bucket", "evaluate", "query_records"]

Value = tuple[str | None, float | None, str | None]  # (text, number, folded text)


def _get(record: dict[str, Any] | None, path: tuple[str, ...]) -> Any:
    value: Any = record
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _value(raw: Any) -> Value:
    text = text_of(raw)
    return text, number_of(raw), fold(text)


def bucket(text: str | None, trunc: str) -> str | None:
    """The date bucket of an ISO date/datetime text (None when it does not start with one)."""
    if text is None:
        return None
    s = text.strip(WS)
    if not ISO_DATE_RE.match(s):
        return None
    if trunc == "day":
        return s[:10]
    if trunc == "month":
        return s[:7]
    if trunc == "year":
        return s[:4]
    if trunc == "quarter":
        return f"{s[:4]}-Q{(int(s[5:7]) + 2) // 3}"
    try:
        day = _dt.date.fromisoformat(s[:10])
    except ValueError:
        return None
    return (day - _dt.timedelta(days=day.weekday())).isoformat()


def _test(c: Cond, values: list[Value]) -> bool:
    if c.op == "and":
        return all(_test(i, values) for i in c.items)
    if c.op == "or":
        return any(_test(i, values) for i in c.items)
    if c.op == "not":
        return not _test(c.items[0], values)
    _text, number, folded = values[c.index]
    if c.op == "is_null":
        empty = folded is None or folded == ""
        return empty if c.flag else not empty
    if c.op in ("eq", "in", "ne"):
        hit = any(
            number == o.number
            if number is not None and o.number is not None
            else folded is not None and folded == o.folded
            for o in c.options
        )
        return not hit if c.op == "ne" else hit
    option = c.options[0]
    if c.op == "contains":
        return folded is not None and option.folded in folded
    if number is not None and option.number is not None:
        a, b = number, option.number
    elif folded is None:
        return False
    else:
        a, b = folded, option.folded  # type: ignore[assignment]
    return {"gt": a > b, "gte": a >= b, "lt": a < b, "lte": a <= b}[c.op]


def _test_metric(c: Cond, values: list[Any]) -> bool:
    if c.op == "and":
        return all(_test_metric(i, values) for i in c.items)
    if c.op == "or":
        return any(_test_metric(i, values) for i in c.items)
    if c.op == "not":
        return not _test_metric(c.items[0], values)
    value, option = values[c.index], c.options[0]
    if value is None:
        return False
    target: Any = option.text if isinstance(value, str) else option.number
    if target is None:
        return False
    hit = {
        "eq": value == target,
        "ne": value != target,
        "gt": value > target,
        "gte": value >= target,
        "lt": value < target,
        "lte": value <= target,
    }[c.op]
    return bool(hit)


def _rows(
    q: RecordQuery, records: Iterable[dict[str, Any]], join_records: Iterable[dict[str, Any]] | None
) -> Iterable[list[Value]]:
    """Each (joined) row as the values of ``q.fields``."""
    base = [(i, f.path) for i, f in enumerate(q.fields) if f.side == "base"]
    joined = [(i, f.path) for i, f in enumerate(q.fields) if f.side == "join"]
    index: dict[str, list[dict[str, Any]]] = {}
    if q.join is not None:
        right = q.fields[q.join.right].path
        for record in join_records or []:
            key = key_text(_get(record, right))
            if key is not None:
                index.setdefault(key, []).append(record)
    for record in records:
        partners: list[dict[str, Any] | None] = [None]
        if q.join is not None:
            key = key_text(_get(record, q.fields[q.join.left].path))
            partners = list(index.get(key, [])) if key is not None else []
            if not partners:
                if q.join.kind == "inner":
                    continue
                partners = [None]
        for partner in partners:
            values: list[Value] = [(None, None, None)] * len(q.fields)
            for i, path in base:
                values[i] = _value(_get(record, path))
            for i, path in joined:
                values[i] = _value(_get(partner, path))
            yield values


def _nulls_last(a: Any, b: Any, desc: bool) -> int:
    if a is None or b is None:
        return (a is None) - (b is None)
    order = (a > b) - (a < b)
    return -order if desc else order


def _metric(op: str, index: int, text: bool, rows: list[list[Value]]) -> Any:
    if op == "count":
        return len(rows)
    if op == "count_distinct":
        return len({r[index][2] for r in rows if r[index][2]})
    if text:
        texts = [r[index][0].strip(WS) for r in rows if r[index][2]]  # type: ignore[union-attr]
        return (min(texts) if op == "min" else max(texts)) if texts else None
    numbers = [r[index][1] for r in rows if r[index][1] is not None]
    if not numbers:
        return None
    if op == "sum":
        return sum(numbers)
    if op == "avg":
        return sum(numbers) / len(numbers)
    return min(numbers) if op == "min" else max(numbers)


def _group_key(q: RecordQuery, row: list[Value]) -> tuple:
    out = []
    for g in q.groups:
        text, _, folded = row[g.index]
        out.append(bucket(text, g.trunc) if g.trunc else (folded or None))
    return tuple(out)


def _label(q: RecordQuery, rows: list[list[Value]], position: int) -> str | None:
    g = q.groups[position]
    if g.trunc:
        return bucket(rows[0][g.index][0], g.trunc)
    texts = [r[g.index][0].strip(WS) for r in rows if r[g.index][2]]  # type: ignore[union-attr]
    return (
        max(texts) if texts else None
    )  # "open" over "OPEN": the highest code point prefers lower case


def _grouped(q: RecordQuery, matched: list[list[Value]]) -> tuple[list[list[Any]], int, int]:
    """(shown group rows, groups after ``having``, rows in those groups)."""
    groups: dict[tuple, list[list[Value]]] = {}
    for row in matched:
        groups.setdefault(_group_key(q, row), []).append(row)
    out = []
    kept = 0
    for key, rows in groups.items():
        labels = [_label(q, rows, i) if key[i] is not None else None for i in range(len(q.groups))]
        metrics = [_metric(m.op, m.index, m.text, rows) for m in q.metrics]
        if q.having is None or _test_metric(q.having, metrics):
            out.append(labels + metrics)
            kept += len(rows)
    orders = q.order or [Order("metric", 0, True)]
    width = len(q.groups)

    def compare(a: list[Any], b: list[Any]) -> int:
        for o in orders:
            column = o.index if o.kind == "group" else width + o.index
            result = _nulls_last(a[column], b[column], o.desc)
            if result:
                return result
        for column in range(width):
            result = _nulls_last(a[column], b[column], False)
            if result:
                return result
        return 0

    out.sort(key=cmp_to_key(compare))
    return out[: q.limit], len(out), kept


def _listed(q: RecordQuery, matched: list[list[Value]]) -> list[list[Any]]:
    if q.order:
        fields: list[Field] = q.fields

        def sort_value(row: list[Value], index: int) -> Any:
            text, number, _ = row[index]
            return (
                number if fields[index].numeric else (text.strip(WS) if text is not None else None)
            )

        def compare(a: list[Value], b: list[Value]) -> int:
            for o in q.order:
                result = _nulls_last(sort_value(a, o.index), sort_value(b, o.index), o.desc)
                if result:
                    return result
            return 0

        matched = sorted(matched, key=cmp_to_key(compare))  # stable: ties keep source order
    return [[row[i][0] for i in q.projection] for row in matched[: q.limit]]


def evaluate(
    q: RecordQuery, records: list[dict[str, Any]], join_records: list[dict[str, Any]] | None = None
) -> RecordResult:
    """Evaluate a resolved query over ``records`` (and the joined table's ``join_records``)."""
    total = len(records)
    if q.impossible:
        return render(q, total)
    matched = [
        row for row in _rows(q, records, join_records) if q.where is None or _test(q.where, row)
    ]
    if q.mode == "list":
        return render(q, total, len(matched), _listed(q, matched))
    if q.mode == "group":
        rows, groups, kept = _grouped(q, matched)
        return render(q, total, kept, rows, groups)
    values = [_metric(m.op, m.index, m.text, matched) for m in q.metrics]
    return render(q, total, len(matched), [values])


def query_records(
    records: list[dict[str, Any]],
    spec: dict[str, Any],
    profile: dict[str, Any] | None = None,
    join_records: list[dict[str, Any]] | None = None,
    join_profile: dict[str, Any] | None = None,
) -> RecordResult:
    """Answer ``spec`` over ``records`` (profiles are computed when not given)."""
    profile = profile or profile_records(records)
    if isinstance(spec, dict) and isinstance(spec.get("join"), dict) and join_profile is None:
        join_profile = profile_records(join_records or [])
    return evaluate(parse_spec(spec, profile, join_profile), records, join_records)
