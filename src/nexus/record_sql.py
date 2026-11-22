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

"""Records queries compiled to parameterised SQL over records kept in chunk metadata.

Tabular processors attach each source row to its chunk as ``metadata.record`` (one row) or
``metadata.records`` (a row group). ``compile_query`` turns a resolved ``RecordQuery``
(``nexus.record_spec``) into one SQL statement that reads those rows where they are stored and
computes the answer in the database, so a 1M-row table is never loaded into the application:

* dialects ``"postgresql"`` (JSONB) and ``"sqlite"`` (JSON1, 3.38+);
* every value, JSON path and constant is a bound parameter; the only identifiers are the
  caller's own chunk table and columns (``ChunkTable``) and generated aliases; field names come
  from the schema profile (allow-listed by ``parse_spec``) and are bound as JSON paths;
* the result is bounded: at most ``limit`` list rows or groups come back (plus counts).

``read_result`` turns the rows the statement returned into the same ``RecordResult`` the Python
engine (``nexus.record_eval``) produces. The caller runs the statement read-only, with a
statement timeout. Notes: SQLite's built-in ``lower()`` folds ASCII only (register
``unicode_lower`` on the connection for parity); on PostgreSQL a ``week`` bucket of an
impossible calendar date (``2025-02-30``) fails the statement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .record_render import RecordResult, from_rows
from .record_spec import Cond, RecordQuery, RecordQueryError
from .record_sql_builder import EMPTY, ChunkTable, _Builder

__all__ = ["ChunkTable", "CompiledQuery", "compile_query", "read_result", "unicode_lower"]

_MARK = re.compile("\x00(\\d+)\x00")


@dataclass
class CompiledQuery:
    sql: str
    params: list[Any]
    query: RecordQuery
    dialect: str
    columns: list[str] = field(default_factory=list)


def unicode_lower(conn: Any) -> None:
    """Make a sqlite3 connection's ``lower()`` Unicode-aware (as in PostgreSQL and Python)."""
    conn.create_function(
        "lower", 1, lambda s: s.lower() if isinstance(s, str) else s, deterministic=True
    )


def _cond(b: _Builder, c: Cond, metric_types: list[bool] | None = None) -> str:
    if c.op in ("and", "or"):
        return "(" + f" {c.op.upper()} ".join(_cond(b, i, metric_types) for i in c.items) + ")"
    if c.op == "not":
        return f"(NOT {_cond(b, c.items[0], metric_types)})"
    op = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "eq": "=", "ne": "<>"}.get(c.op, "")
    if c.metric:
        option, text = c.options[0], bool(metric_types and metric_types[c.index])
        value = option.text if text else option.number
        if value is None:
            raise RecordQueryError(f"having compares a numeric metric with '{option.text}'")
        column = b.collate(f"m{c.index}") if text else f"m{c.index}"
        return f"COALESCE({column} {op} {b.p(value)}, FALSE)"
    n, f = f"n{c.index}", f"f{c.index}"
    if c.op == "is_null":
        empty = f"({f} IS NULL OR {f} = '')"
        return empty if c.flag else f"(NOT {empty})"
    if c.op == "contains":
        found = (
            f"strpos({f}, {b.p(c.options[0].folded)}) > 0"
            if b.pg
            else f"instr({f}, {b.p(c.options[0].folded)}) > 0"
        )
        return f"COALESCE({found}, FALSE)"
    if c.op in ("eq", "in", "ne"):
        parts = []
        for o in c.options:
            if o.number is not None:
                parts.append(
                    f"(CASE WHEN {n} IS NOT NULL THEN {n} = {b.p(o.number)} "
                    f"ELSE {f} = {b.p(o.folded)} END)"
                )
            else:
                parts.append(f"{f} = {b.p(o.folded)}")
        hit = f"COALESCE({' OR '.join(parts)}, FALSE)"
        return f"(NOT {hit})" if c.op == "ne" else hit
    o = c.options[0]
    text = f"{b.collate(f)} {op} {b.p(o.folded)}"
    if o.number is None:
        return f"COALESCE({text}, FALSE)"
    return (
        f"COALESCE(CASE WHEN {n} IS NOT NULL THEN {n} {op} {b.p(o.number)} ELSE {text} END, FALSE)"
    )


def _hints(b: _Builder, q: RecordQuery, source: ChunkTable, mapped: dict[int, tuple]) -> str:
    """Index-friendly conditions implied by top-level ``eq`` / ``in`` predicates of a ``"row"``
    source (the exact predicate still runs; these only let an index narrow the rows)."""
    if source.layout != "row" or q.where is None:
        return ""
    out = []
    for c in q.where.items if q.where.op == "and" else [q.where]:
        if c.op not in ("eq", "in") or c.metric or not 0 < len(c.options) <= 50:
            continue
        f = q.fields[c.index]
        numbers = all(o.number is not None for o in c.options)
        texts = all(o.number is None for o in c.options)
        if f.side != "base" or not (numbers or texts):
            continue
        if c.index in mapped:
            column, kind = mapped[c.index]
            values = [o.number if numbers else o.folded for o in c.options]
            out.append(b.slot_hint(column, kind, values, numbers))
        elif b.pg and texts:  # matches an expression index on the folded JSON value
            listed = ", ".join(b.p(o.folded) for o in c.options)
            folded = b.fold(f"(c.{source.metadata} #>> {b.path(f.path)})")
            out.append(f" AND {folded} IN ({listed})")
    return "".join(out)


def _layers(b: _Builder, q: RecordQuery, source: ChunkTable, join_source: ChunkTable | None) -> str:
    slots = source.slots()
    mapped = {
        i: slots[f.path] for i, f in enumerate(q.fields) if f.side == "base" and f.path in slots
    }
    extra = "".join(f", c.{column} AS x{i}" for i, (column, _) in mapped.items())
    xs = "".join(f", x{i}" for i in mapped)
    ctes = [f"src AS ({b.source(source, extra, _hints(b, q, source, mapped))})"]
    rows = "src"
    carry = ("rec" if b.pg else "doc, pre") + xs
    if q.join is not None:
        if join_source is None:
            raise RecordQueryError("the query joins a table: pass its join_source")
        right, left = q.fields[q.join.right], q.fields[q.join.left]
        ctes.append(f"jsrc AS ({b.source(join_source)})")
        ctes += b.keyed("jkey", "jsrc", "rec" if b.pg else "doc, pre", right)
        jcols = "rec AS jrec" if b.pg else "doc AS jdoc, pre AS jpre"
        # materialised once (SQLite then indexes _k for the join; PostgreSQL hashes it either way)
        ctes.append(f"jk AS {'' if b.pg else 'MATERIALIZED '}(SELECT _k, {jcols} FROM jkey)")
        kind = "LEFT JOIN" if q.join.kind == "left" else "JOIN"
        jcarry = "jk.jrec" if b.pg else "jk.jdoc, jk.jpre"
        ctes += b.keyed(
            "sk", "src", f"_ci, _ri, {carry}", left
        )  # each row's key, then looked up in jk
        ctes.append(
            f"base AS (SELECT s._ci, s._ri, "
            f"{', '.join('s.' + c for c in carry.split(', '))}, {jcarry} "
            f"FROM sk s {kind} jk ON jk._k = s._k)"
        )
        rows = "base"
    cols = ", ".join(f"t{i}" for i in range(len(q.fields)))
    keep = "_ci, _ri" + (f", {cols}" if cols else "")
    if b.pg:
        texts = []
        for i, f in enumerate(q.fields):
            text = f"({'j' if f.side == 'join' else ''}rec #>> {b.path(f.path)})"
            if i in mapped:  # the typed column, else (NULL) the JSON
                slot = b.slot_text(f"x{i}", mapped[i][1])
                text = f"CASE WHEN x{i} IS NOT NULL THEN {slot} ELSE {text} END"
            texts.append(f"{text} AS t{i}")
        ctes.append(f"d AS (SELECT _ci, _ri{xs}{''.join(', ' + t for t in texts)} FROM {rows})")
        forms = []
        for i in range(len(q.fields)):
            number = b.number(f"t{i}")
            if i in mapped and mapped[i][1] != "text":
                slot = b.slot_number(f"x{i}", mapped[i][1])
                number = f"CASE WHEN x{i} IS NOT NULL THEN {slot} ELSE {number} END"
            forms.append(f"{number} AS n{i}, {b.fold(f't{i}')} AS f{i}")
        ctes.append(f"e AS (SELECT {keep}{''.join(', ' + f for f in forms)} FROM d)")
    else:
        carried = "_ci, _ri, doc, pre" + (", jdoc, jpre" if q.join is not None else "") + xs
        types, values = [], []
        for i, f in enumerate(q.fields):
            y, v = b.extract("j" if f.side == "join" else "", f)
            types.append(y)
            values.append(f"{f'CASE WHEN x{i} IS NULL THEN {v} END' if i in mapped else v} AS v{i}")
        # LIMIT -1 keeps this layer a co-routine: each value is extracted once per row, however
        # often the expressions below refer to it (a flattened query would extract it each time)
        ctes.append(
            f"d AS (SELECT {carried}{', ' + ', '.join(values) if values else ''} "
            f"FROM {rows} LIMIT -1)"
        )
        forms = []
        for i, y in enumerate(types):
            t, n = b.sqlite_text(y, f"v{i}"), b.number("", y, f"v{i}")
            if i in mapped:
                x, kind = f"x{i}", mapped[i][1]
                t = f"CASE WHEN {x} IS NOT NULL THEN {b.slot_text(x, kind)} ELSE {t} END"
                n = f"CASE WHEN {x} IS NOT NULL THEN {b.slot_number(x, kind)} ELSE {n} END"
            forms.append(f"{t} AS t{i}, {n} AS n{i}, {b.fold(t)} AS f{i}")
        ctes.append(f"e AS (SELECT _ci, _ri{', ' + ', '.join(forms) if forms else ''} FROM d)")
    buckets = ", ".join(
        f"{b.bucket(f't{g.index}', g.trunc)} AS b{j}" for j, g in enumerate(q.groups) if g.trunc
    )
    where = f" WHERE {_cond(b, q.where)}" if q.where is not None else ""
    ctes.append(f"m AS (SELECT *{', ' + buckets if buckets else ''} FROM e{where})")
    return "WITH " + ",\n".join(ctes)


def _metric_sql(b: _Builder, op: str, index: int, text: bool) -> str:
    if op == "count":
        return "COUNT(*)"
    if op == "count_distinct":
        return f"COUNT(DISTINCT NULLIF(f{index}, ''))"
    if text:
        trimmed = b.trim(f"t{index}")
        return f"{op.upper()}({b.collate(f'NULLIF({trimmed}, {EMPTY})')})"
    return f"{op.upper()}(n{index})"


def _order_sql(b: _Builder, expr: str, desc: bool, text: bool) -> str:
    return f"{b.collate(expr) if text else expr} {'DESC' if desc else 'ASC'} NULLS LAST"


def compile_query(
    q: RecordQuery,
    dialect: str,
    source: ChunkTable,
    join_source: ChunkTable | None = None,
    placeholder: str = "?",
) -> CompiledQuery:
    """One parameterised statement computing ``q`` over the records of ``source``.
    ``placeholder``: ``"?"`` (qmark) or ``"%s"`` (format) for the bound values."""
    if q.impossible:
        raise RecordQueryError("nothing to compute: a required value is not in the table")
    b = _Builder(dialect)
    head = _layers(b, q, source, join_source)
    if q.mode == "list":
        orders = [
            _order_sql(
                b,
                f"n{o.index}" if q.fields[o.index].numeric else b.trim(f"t{o.index}"),
                o.desc,
                not q.fields[o.index].numeric,
            )
            for o in q.order
        ]
        cols = ", ".join(f"t{i}" for i in q.projection)
        body = (
            f"SELECT {cols}, COUNT(*) OVER () AS _matched FROM m ORDER BY "
            f"{', '.join([*orders, '_ci', '_ri'])} LIMIT {int(q.limit)}"
        )
        columns = [q.fields[i].name for i in q.projection] + ["_matched"]
    elif q.mode == "group":
        keys = [f"b{j}" if g.trunc else f"NULLIF(f{g.index}, '')" for j, g in enumerate(q.groups)]
        labels = [
            # NULL for the empty group (its key is NULL), so it sorts last as in the Python engine
            f"MIN(b{j})" if g.trunc else f"NULLIF(MAX({b.collate(b.trim(f't{g.index}'))}), {EMPTY})"
            for j, g in enumerate(q.groups)
        ]
        metrics = [_metric_sql(b, m.op, m.index, m.text) for m in q.metrics]
        inner = (
            f"SELECT {', '.join(f'{k} AS k{j}' for j, k in enumerate(keys))}, "
            f"{', '.join(f'{lab} AS g{j}' for j, lab in enumerate(labels))}, "
            f"{', '.join(f'{m} AS m{i}' for i, m in enumerate(metrics))}, "
            f"COUNT(*) AS _n FROM m GROUP BY {', '.join(str(j + 1) for j in range(len(keys)))}"
        )
        having = (
            f" WHERE {_cond(b, q.having, [m.text for m in q.metrics])}"
            if q.having is not None
            else ""
        )
        orders = [
            _order_sql(
                b,
                f"m{o.index}" if o.kind == "metric" else f"g{o.index}",
                o.desc,
                o.kind == "group" or q.metrics[o.index].text,
            )
            for o in q.order or []
        ]
        if not q.order:
            orders = [_order_sql(b, "m0", True, q.metrics[0].text)]
        orders += [_order_sql(b, f"g{j}", False, True) for j in range(len(q.groups))]
        width = len(q.groups)
        out = (
            [f"k{j}" for j in range(width)]
            + [f"g{j}" for j in range(width)]
            + [f"m{i}" for i in range(len(metrics))]
        )
        body = (
            f"SELECT {', '.join(out)}, SUM(_n) OVER () AS _matched, COUNT(*) OVER () AS _groups "
            f"FROM ({inner}) q{having} "
            f"ORDER BY {', '.join(orders)} LIMIT {int(q.limit)}"
        )
        columns = [*out, "_matched", "_groups"]
    else:
        metrics = [_metric_sql(b, m.op, m.index, m.text) for m in q.metrics]
        selected = ", ".join(f"{m} AS m{i}" for i, m in enumerate(metrics))
        body = f"SELECT COUNT(*) AS _matched, {selected} FROM m"
        columns = ["_matched"] + [f"m{i}" for i in range(len(metrics))]
    sql = f"{head}\n{body}"
    params: list[Any] = []

    def place(match: re.Match[str]) -> str:
        params.append(b.values[int(match.group(1))])
        return placeholder

    return CompiledQuery(_MARK.sub(place, sql), params, q, dialect, columns)


def read_result(compiled: CompiledQuery, rows: list[Any], total: int) -> RecordResult:
    """The ``RecordResult`` of the rows ``compiled`` returned (``total``: rows in the table)."""
    return from_rows(compiled.query, rows, total)
