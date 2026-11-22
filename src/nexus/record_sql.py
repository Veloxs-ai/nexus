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
from .record_spec import Cond, Field, RecordQuery, RecordQueryError
from .record_values import NUMBER_RE, WS

__all__ = ["ChunkTable", "CompiledQuery", "compile_query", "read_result", "unicode_lower"]

DIALECTS = ("postgresql", "sqlite")
_ISO_PG = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}"
_ISO_GLOB = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]"
_MARK = re.compile("\x00(\\d+)\x00")
EMPTY = "''"  # the SQL empty string


@dataclass(frozen=True)
class ChunkTable:
    """Where records live: chunk rows (alias ``c``) of ``table`` matching ``where``; ``where`` is
    the caller's SQL with ``?`` for each of ``params`` (e.g. ``c.document_id = ? AND
    c.chunk_index >= 0``); ``metadata`` is the JSON(B) column, ``order`` the reading order."""

    table: str
    where: str
    params: tuple[Any, ...] = ()
    metadata: str = "metadata"
    order: str = "chunk_index"
    layout: str = (
        "mixed"  # "record": every chunk holds one ``record``; "records": row groups; "mixed"
    )


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


class _Builder:
    def __init__(self, dialect: str):
        if dialect not in DIALECTS:
            raise RecordQueryError(f"unsupported SQL dialect '{dialect}' ({', '.join(DIALECTS)})")
        self.pg = dialect == "postgresql"
        self.values: list[Any] = []

    def p(self, value: Any) -> str:
        self.values.append(value)
        return f"\x00{len(self.values) - 1}\x00"

    def caller(self, where: str, params: tuple[Any, ...]) -> str:
        parts = where.split("?")
        if len(parts) - 1 != len(params):
            raise RecordQueryError("ChunkTable.where needs one '?' per parameter")
        out = parts[0]
        for value, part in zip(params, parts[1:], strict=True):
            out += self.p(value) + part
        return out

    # -- value forms ------------------------------------------------------------------------
    def collate(self, expr: str) -> str:
        return f'{expr} COLLATE "C"' if self.pg else expr

    def trim(self, expr: str) -> str:
        return f"btrim({expr}, {self.p(WS)})" if self.pg else f"trim({expr}, {self.p(WS)})"

    def fold(self, text: str) -> str:
        return f"lower({self.trim(text)})"

    def path(self, path: tuple[str, ...]) -> str:
        if self.pg:
            return self.p(list(path))
        if any('"' in k for k in path):
            raise RecordQueryError(
                f"field '{'.'.join(path)}' has a double quote in its name (unsupported)"
            )
        return self.p("".join(f'."{k}"' for k in path))

    def extract(self, rec: str, f: Field) -> tuple[str, str]:
        """SQLite: (json_type, json_extract) of ``f`` in the record ``rec`` (``<rec>doc`` is the
        chunk
        metadata, ``<rec>pre`` the record's JSON path in it: one parse per chunk, cached by SQLite).
        The type is read only for integers (``true`` / ``false`` also extract as 1 / 0)."""
        path = self.path(f.path)
        return (
            f"json_type({rec}doc, {rec}pre || {path})",
            f"json_extract({rec}doc, {rec}pre || {path})",
        )

    def sqlite_text(self, y: str, v: str) -> str:
        return (
            f"CASE typeof({v}) WHEN 'text' THEN {v} WHEN 'real' THEN CAST({v} AS TEXT) "
            f"WHEN 'integer' THEN CASE {y} WHEN 'true' THEN 'true' WHEN 'false' THEN 'false' "
            f"ELSE CAST({v} AS TEXT) END END"
        )

    def number(self, text: str, y: str = "", v: str = "") -> str:
        if self.pg:
            return (
                f"CASE WHEN {text} ~ {self.p(NUMBER_RE.pattern)} THEN CAST({text} AS numeric) END"
            )
        s = self.trim(v)
        u = f"(CASE WHEN substr({s}, 1, 1) = '-' THEN substr({s}, 2) ELSE {s} END)"
        # cheap necessary conditions first (a name fails the first GLOB), then the exact shape
        test = (
            f"{v} NOT GLOB {self.p('*[^-0-9. ' + WS[1:] + ']*')} AND {v} GLOB {self.p('*[0-9]*')} "
            f"AND {u} NOT GLOB {self.p('*[^0-9.]*')} AND {u} GLOB {self.p('[0-9]*')} "
            f"AND {u} GLOB {self.p('*[0-9]')} AND length({u}) - length(replace({u}, '.', '')) <= 1"
        )
        return (
            f"CASE typeof({v}) WHEN 'real' THEN {v} WHEN 'integer' THEN CASE {y} WHEN 'integer' "
            f"THEN CAST({v} AS REAL) END "
            f"WHEN 'text' THEN CASE WHEN {test} THEN CAST({s} AS REAL) END END"
        )

    def inline(self, rec: str, f: Field) -> tuple[str, str, str]:
        """(text, number, folded) expressions of ``f`` read straight from the record ``rec``."""
        if self.pg:
            t = f"({rec}rec #>> {self.path(f.path)})"
            return t, self.number(t), self.fold(t)
        y, v = self.extract(rec, f)
        t = self.sqlite_text(y, v)
        return t, self.number(t, y, v), self.fold(t)

    def key(self, rec: str, f: Field) -> str:
        """PostgreSQL: the join key of ``f`` (``key_text``) read straight from ``rec``."""
        _, n, folded = self.inline(rec, f)
        return (
            f"CASE WHEN ({n}) IS NULL THEN {folded} "
            f"WHEN ({n}) = trunc({n}) THEN CAST(trunc({n}) AS text) "
            f"ELSE rtrim(rtrim(CAST(({n}) AS text), '0'), '.') END"
        )

    def keyed(self, name: str, rows: str, carry: str, f: Field) -> list[str]:
        """CTEs adding the join key ``_k`` of ``f`` to every row of ``rows``. SQLite: in three
        co-routines (value, then number and folded text, then key): each step runs once a row."""
        if self.pg:
            return [f"{name} AS (SELECT {carry}, {self.key('', f)} AS _k FROM {rows})"]
        y, v = self.extract("", f)
        t = self.sqlite_text(y, "_v")
        return [
            f"{name}0 AS (SELECT {carry}, {v} AS _v FROM {rows} LIMIT -1)",
            f"{name}1 AS (SELECT {carry}, {self.number('', y, '_v')} AS _n, {self.fold(t)} AS _f "
            f"FROM {name}0 LIMIT -1)",
            f"{name} AS (SELECT {carry}, CASE WHEN _n IS NULL THEN _f "
            f"WHEN _n = CAST(_n AS INTEGER) "
            f"THEN CAST(CAST(_n AS INTEGER) AS TEXT) ELSE CAST(_n AS TEXT) END AS _k FROM {name}1)",
        ]

    def bucket(self, text: str, trunc: str) -> str:
        if self.pg:
            return self._bucket(self.trim(text), trunc)
        # SQLite: the untrimmed text first (the usual case), the trimmed text only when it differs
        return (
            f"CASE WHEN substr({text}, 1, 10) GLOB {self.p(_ISO_GLOB)} "
            f"THEN {self._bucket(text, trunc, True)} "
            f"ELSE {self._bucket(self.trim(text), trunc)} END"
        )

    def _bucket(self, s: str, trunc: str, checked: bool = False) -> str:
        if self.pg:
            valid = f"{s} ~ {self.p(_ISO_PG)}"
            quarter = (
                f"substr({s}, 1, 4) || '-Q' || "
                f"CAST((CAST(substr({s}, 6, 2) AS integer) + 2) / 3 AS text)"
            )
            week = f"to_char(date_trunc('week', CAST(substr({s}, 1, 10) AS date)), 'YYYY-MM-DD')"
        else:
            valid = f"substr({s}, 1, 10) GLOB {self.p(_ISO_GLOB)}"
            quarter = f"substr({s}, 1, 4) || '-Q' || ((CAST(substr({s}, 6, 2) AS INTEGER) + 2) / 3)"
            day = f"substr({s}, 1, 10)"
            week = (
                f"CASE WHEN date({day}) = {day} THEN date({day}, '-' || "
                f"((CAST(strftime({self.p('%w')}, {day}) "
                f"AS INTEGER) + 6) % 7) || ' days') END"
            )
        body = {
            "day": f"substr({s}, 1, 10)",
            "month": f"substr({s}, 1, 7)",
            "year": f"substr({s}, 1, 4)",
            "quarter": quarter,
            "week": week,
        }[trunc]
        return body if checked else f"CASE WHEN {valid} THEN {body} END"

    # -- row sources ------------------------------------------------------------------------
    def source(self, t: ChunkTable) -> str:
        """One row per record, in reading order: a chunk's ``records`` array, else its
        ``record``."""
        meta, order, where = f"c.{t.metadata}", f"c.{t.order}", self.caller(t.where, t.params)
        if self.pg:
            rows = (
                f"CASE WHEN jsonb_typeof({meta} -> 'records') = 'array' THEN {meta} -> 'records' "
                f"WHEN jsonb_typeof({meta} -> 'record') = 'object' "
                f"THEN jsonb_build_array({meta} -> 'record') "
                f"ELSE CAST('[]' AS jsonb) END"
            )
            return (
                f"SELECT {order} AS _ci, r.ord AS _ri, r.rec AS rec FROM {t.table} c "
                f"CROSS JOIN LATERAL jsonb_array_elements({rows}) WITH ORDINALITY AS r(rec, ord) "
                f"WHERE ({where}) AND jsonb_typeof(r.rec) = 'object'"
            )
        if t.layout == "record":  # one parse per chunk (the two-branch read below parses twice)
            return (
                f"SELECT {order} AS _ci, -1 AS _ri, {meta} AS doc, '$.record' AS pre "
                f"FROM {t.table} c "
                f"WHERE ({where}) AND json_type({meta}, '$.record') = 'object'"
            )
        if t.layout == "records":
            return (
                f"SELECT {order} AS _ci, CAST(r.key AS INTEGER) AS _ri, {meta} AS doc, "
                f"'$.records[' || r.key || ']' AS pre "
                f"FROM {t.table} c, json_each({meta}, '$.records') r "
                f"WHERE ({where}) AND r.type = 'object'"
            )
        return (
            f"SELECT {order} AS _ci, COALESCE(CAST(r.key AS INTEGER), -1) AS _ri, {meta} AS doc, "
            f"CASE WHEN r.key IS NULL THEN '$.record' ELSE '$.records[' || r.key || ']' END AS pre "
            f"FROM {t.table} c LEFT JOIN json_each({meta}, '$.records') r ON r.type = 'object' "
            f"WHERE ({where}) AND (r.key IS NOT NULL OR (json_type({meta}, '$.records') IS NULL "
            f"AND json_type({meta}, '$.record') = 'object'))"
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


def _layers(b: _Builder, q: RecordQuery, source: ChunkTable, join_source: ChunkTable | None) -> str:
    ctes = [f"src AS ({b.source(source)})"]
    rows = "src"
    carry = "rec" if b.pg else "doc, pre"
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
        texts = ", ".join(
            f"({'j' if f.side == 'join' else ''}rec #>> {b.path(f.path)}) AS t{i}"
            for i, f in enumerate(q.fields)
        )
        ctes.append(f"d AS (SELECT _ci, _ri{', ' + texts if texts else ''} FROM {rows})")
        forms = ", ".join(
            f"{b.number(f't{i}')} AS n{i}, {b.fold(f't{i}')} AS f{i}" for i in range(len(q.fields))
        )
        ctes.append(f"e AS (SELECT {keep}{', ' + forms if forms else ''} FROM d)")
    else:
        carried = "_ci, _ri, doc, pre" + (", jdoc, jpre" if q.join is not None else "")
        types, values = [], []
        for i, f in enumerate(q.fields):
            y, v = b.extract("j" if f.side == "join" else "", f)
            types.append(y)
            values.append(f"{v} AS v{i}")
        # LIMIT -1 keeps this layer a co-routine: each value is extracted once per row, however
        # often the expressions below refer to it (a flattened query would extract it each time)
        ctes.append(
            f"d AS (SELECT {carried}{', ' + ', '.join(values) if values else ''} "
            f"FROM {rows} LIMIT -1)"
        )
        forms = []
        for i, y in enumerate(types):
            t = b.sqlite_text(y, f"v{i}")
            forms.append(f"{t} AS t{i}, {b.number('', y, f'v{i}')} AS n{i}, {b.fold(t)} AS f{i}")
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
