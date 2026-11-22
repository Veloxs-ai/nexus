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

"""Records queries: the result and its text (shared by ``record_eval`` and ``record_sql``).

Both engines hand over the same raw result (matched rows, the shown rows of a list or a
grouping, the metric values) and get the same ``RecordResult`` back, so a result reads the
same whichever engine computed it.
"""

from __future__ import annotations

import decimal
from dataclasses import dataclass, field
from typing import Any

from .record_spec import Cond, RecordQuery

__all__ = [
    "EMPTY_GROUP",
    "RecordResult",
    "describe",
    "format_value",
    "from_rows",
    "markdown_table",
    "render",
]

EMPTY_GROUP = "(empty)"


@dataclass
class RecordResult:
    document: str
    description: str
    kind: str  # "list" | "group" | "scalar" | "not_found"
    matched: (
        int  # rows meeting the conditions (joined rows; group: rows of the groups kept by having)
    )
    total: int  # rows of the table computed over
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    text: str = ""
    listed: int | None = None  # list: rows shown (fewer than ``matched`` when cut at the limit)
    groups: int | None = None  # group: groups after ``having`` (more than shown when cut)
    not_found: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def format_value(value: Any) -> str:
    """Numbers with thousands separators and at most two decimals; None as empty."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        if value == int(value):
            return f"{int(value):,}"
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    return str(value)


def markdown_table(header: list[str], rows: list[list[Any]]) -> str:
    def cell(value: Any) -> str:
        return format_value(value).replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(cell(h) for h in header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)


def _cond_text(c: Cond, q: RecordQuery) -> str:
    if c.op in ("and", "or"):
        return "(" + f" {c.op} ".join(_cond_text(i, q) for i in c.items) + ")"
    if c.op == "not":
        return f"not {_cond_text(c.items[0], q)}"
    name = q.metrics[c.index].name if c.metric else q.fields[c.index].name
    if c.op == "is_null":
        return f"{name} is {'' if c.flag else 'not '}empty"
    values = ", ".join(repr(o.text) for o in c.options)
    return f"{name} {c.op} {('[' + values + ']') if c.op == 'in' else values}"


def describe(q: RecordQuery) -> str:
    """One line saying what is computed (shown with the result)."""
    where = _cond_text(q.where, q) if q.where else "no filter"
    if q.where is not None and q.where.op == "and":
        where = where[1:-1]
    head = "list" if q.mode == "list" else ", ".join(m.name for m in q.metrics)
    if q.groups:
        head += " by " + ", ".join(g.name for g in q.groups)
    text = f"{head} where {where}"
    if q.join:
        text += (
            f" (joined with {q.join.document} as {q.join.alias} on "
            f"{q.fields[q.join.left].name} = {q.fields[q.join.right].name})"
        )
    if q.having:
        text += f" having {_cond_text(q.having, q)}"
    names = []
    for o in q.order:
        source = q.metrics if o.kind == "metric" else q.groups if o.kind == "group" else q.fields
        names.append(f"{source[o.index].name} {'desc' if o.desc else 'asc'}")
    if names:
        text += " order by " + ", ".join(names)
    if q.mode != "scalar" and (q.order or q.mode == "group"):
        text += f" limit {q.limit}"
    return text


def _closest_text(item: dict[str, Any]) -> str:
    near = ", ".join(f"'{v}' ({format_value(int(n))} rows)" for v, n in item.get("closest") or [])
    return f"{item['field']} has no value '{item['value']}'" + (
        f" (closest stored values: {near})" if near else ""
    )


def render(
    q: RecordQuery,
    total: int,
    matched: int = 0,
    rows: list[list[Any]] | None = None,
    groups: int | None = None,
) -> RecordResult:
    """The result of ``q``. ``rows``: list rows (projected texts), group rows (labels then metric
    values) or the one scalar row of metric values; ``groups``: groups after ``having``."""
    rows = rows or []
    notes = list(q.notes)
    notes += [f"No record has {_closest_text(i)}." for i in q.not_found if not i.get("required")]
    base = RecordResult(
        q.document, q.description, q.mode, matched, total, notes=notes, not_found=list(q.not_found)
    )
    if q.impossible:
        missing = "; ".join(_closest_text(i) for i in q.not_found if i.get("required"))
        base.kind, base.matched = "not_found", 0
        base.text = (
            f"No matching records: {missing}. The value is not in the table, so nothing was "
            f"computed; check which stored value is meant."
        )
        return base
    if q.mode == "list":
        base.columns = [q.fields[i].name for i in q.projection]
        base.rows, base.listed = rows, len(rows)
        body = markdown_table(base.columns, rows) if rows else "(no matching records)"
        more = (
            f"\n\n…and {matched - len(rows)} more matching record(s) not listed: "
            f"this list shows {len(rows)} of "
            f"{matched} matching records."
            if matched > len(rows)
            else ""
        )
        base.text = f"{matched} matching record(s):\n\n{body}{more}"
    elif q.mode == "group":
        base.columns = [g.name for g in q.groups] + [m.name for m in q.metrics]
        shown = [
            [EMPTY_GROUP if v is None and i < len(q.groups) else v for i, v in enumerate(r)]
            for r in rows
        ]
        base.rows, base.groups = shown, groups if groups is not None else len(rows)
        base.text = markdown_table(base.columns, shown) if shown else "(no matching records)"
        if base.groups > len(shown):
            base.text += f"\n\n…and {base.groups - len(shown)} more group(s)."
    else:
        values = rows[0] if rows else [None] * len(q.metrics)
        base.columns, base.rows = [m.name for m in q.metrics], [list(values)]
        if len(q.metrics) == 1:
            value = values[0]
            base.text = (
                f"Result: {format_value(value) if value is not None else 'no numeric values'}"
            )
        else:
            base.text = "Result: " + "; ".join(
                f"{m.name} = {format_value(v) if v is not None else 'none'}"
                for m, v in zip(q.metrics, values, strict=True)
            )
        if any(m.op != "count" for m in q.metrics):
            base.text += f" (over {matched} matching record(s))"
    if notes:
        base.text += "\n\nNote: " + " ".join(notes)
    return base


def _plain(value: Any, count: bool = False) -> Any:
    if isinstance(value, decimal.Decimal):
        return int(value) if count else float(value)
    if count and value is not None:
        return int(value)
    if isinstance(value, int) and not count and not isinstance(value, bool):
        return float(value)
    return value


def from_rows(q: RecordQuery, rows: list[Any], total: int) -> RecordResult:
    """The result of the rows a ``nexus.record_sql`` statement returned for ``q`` (columns:
    list = shown texts then matched; group = keys, labels, metrics, matched, groups;
    scalar = matched then metrics). Decimals become floats, counts ints."""
    rows = [tuple(r) for r in rows]
    counts = [m.op in ("count", "count_distinct") for m in q.metrics]

    def metric(i: int, value: Any) -> Any:
        return value if q.metrics[i].text else _plain(value, counts[i])

    if q.mode == "list":
        matched = int(rows[0][-1]) if rows else 0
        return render(q, total, matched, [list(r[:-1]) for r in rows])
    if q.mode == "group":
        width = len(q.groups)
        shown = []
        for r in rows:
            labels = [r[width + j] if r[j] is not None else None for j in range(width)]
            shown.append(
                labels
                + [metric(i, v) for i, v in enumerate(r[2 * width : 2 * width + len(q.metrics)])]
            )
        matched = int(rows[0][-2]) if rows else 0
        groups = int(rows[0][-1]) if rows else 0
        return render(q, total, matched, shown, groups)
    row = rows[0] if rows else (0,) + (None,) * len(q.metrics)
    return render(q, total, int(row[0] or 0), [[metric(i, v) for i, v in enumerate(row[1:])]])
