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


"""SQL building blocks of ``nexus.record_sql``: where records live (``ChunkTable``) and the value
forms (text, number, folded text, date buckets, join keys) a compiled statement reads.

Records are read from chunk metadata (``record`` / ``records`` layouts) or from a table with one
row per record (``"row"`` layout), whose typed columns (``ChunkTable.columns``, planned by
``nexus.record_slots``) are read instead of the JSON when a field is mapped.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .record_spec import Field, RecordQueryError
from .record_values import NUMBER_RE, WS

__all__ = ["DIALECTS", "EMPTY", "ChunkTable"]

DIALECTS = ("postgresql", "sqlite")
_ISO_PG = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}"
_ISO_GLOB = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]"
EMPTY = "''"  # the SQL empty string
SQLITE_WS = "char(" + ", ".join(str(ord(c)) for c in WS) + ")"  # WS in SQLite
# A folded text a JSON object, array or exponent number could have (not held by text slots).
_UNSLOTTED = re.compile(r"^[\[{]|^-?[0-9]+(?:\.[0-9]+)?e[-+]?[0-9]+$")


_IDENT = re.compile(r'^(?:[A-Za-z_][A-Za-z0-9_]*|"[^"]+")$')
_SLOT_KINDS = ("text", "number", "date")


@dataclass(frozen=True)
class ChunkTable:
    """Where records live: rows (alias ``c``) of ``table`` matching ``where``; ``where`` is the
    caller's SQL with ``?`` for each of ``params`` (e.g. ``c.document_id = ? AND
    c.chunk_index >= 0``); ``metadata`` is the JSON(B) column, ``order`` the reading order.

    ``layout``: ``"record"`` (every chunk's metadata holds one ``record``), ``"records"`` (row
    groups), ``"mixed"`` (either), or ``"row"``: one table row per record, ``metadata`` being the
    record itself (an object on every row). With ``"row"``, ``columns`` maps field paths
    (tuples, or dotted strings) to ``(column, kind)`` typed columns of the same row, kind
    ``"text"`` / ``"number"`` / ``"date"`` (``nexus.record_slots``); a mapped field is read
    from its column, and from the JSON on rows where the column is NULL."""

    table: str
    where: str
    params: tuple[Any, ...] = ()
    metadata: str = "metadata"
    order: str = "chunk_index"
    layout: str = "mixed"
    columns: Mapping[Any, tuple[str, str]] | None = field(default=None, hash=False)

    def slots(self) -> dict[tuple[str, ...], tuple[str, str]]:
        """``columns`` with tuple paths, checked (identifiers and kinds)."""
        if not self.columns:
            return {}
        if self.layout != "row":
            raise RecordQueryError("ChunkTable.columns needs layout 'row'")
        out = {}
        for path, (column, kind) in self.columns.items():
            if not _IDENT.match(str(column)):
                raise RecordQueryError(f"slot column '{column}' is not a plain identifier")
            if kind not in _SLOT_KINDS:
                raise RecordQueryError(f"slot kind '{kind}' ({', '.join(_SLOT_KINDS)})")
            key = tuple(path.split(".")) if isinstance(path, str) else tuple(str(p) for p in path)
            out[key] = (str(column), kind)
        return out


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
        # SQLite: the blanks as a constant expression, so an index on the folded value matches
        return f"btrim({expr}, {self.p(WS)})" if self.pg else f"trim({expr}, {SQLITE_WS})"

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

    # -- typed slot columns (layout "row") --------------------------------------------------
    def slot_text(self, x: str, kind: str) -> str:
        """The text a slot holds, exactly as the JSON's (``nexus.record_slots``)."""
        if kind == "text":
            return f"CAST({x} AS text)" if self.pg else f"CAST({x} AS TEXT)"
        if kind == "number":
            if self.pg:
                return (
                    f"CASE WHEN {x} = trunc({x}) THEN CAST(trunc({x}) AS text) "
                    f"ELSE rtrim(rtrim(CAST({x} AS text), '0'), '.') END"
                )
            return (
                f"CASE WHEN {x} = CAST({x} AS INTEGER) THEN CAST(CAST({x} AS INTEGER) AS TEXT) "
                f"ELSE CAST({x} AS TEXT) END"
            )
        if self.pg:
            utc = f"({x} AT TIME ZONE 'UTC')"
            stamp = 'YYYY-MM-DD"T"HH24:MI:SS"Z"'
            return (
                f"CASE WHEN to_char({utc}, {self.p('HH24:MI:SS')}) = {self.p('00:00:00')} "
                f"THEN to_char({utc}, {self.p('YYYY-MM-DD')}) "
                f"ELSE to_char({utc}, {self.p(stamp)}) END"
            )
        midnight = self.p("00:00:00")
        return f"CASE WHEN substr({x}, 12, 8) = {midnight} THEN substr({x}, 1, 10) ELSE {x} END"

    def slot_number(self, x: str, kind: str) -> str:
        """The number of a (non-NULL) slot value, as the engines read the JSON's."""
        if kind == "number":
            return f"CAST({x} AS numeric)" if self.pg else f"CAST({x} AS REAL)"
        if kind == "date":
            return "NULL"
        text = self.slot_text(x, "text")
        return self.number(text) if self.pg else self.number("", "NULL", text)

    def slot_hint(self, column: str, kind: str, options: list[Any], numbers: bool) -> str:
        """A condition every row matching ``field IN options`` meets (rows reading the JSON
        included), usable by an index on the slot (folded text for a text slot)."""
        if kind == "number" and numbers:
            listed = ", ".join(self.p(o) for o in options)
            return f" AND (c.{column} IN ({listed}) OR c.{column} IS NULL)"
        if kind == "text" and not numbers:
            listed = ", ".join(self.p(o) for o in options)
            folded = self.fold(self.slot_text(f"c.{column}", "text"))
            if any(_UNSLOTTED.match(str(o)) for o in options):  # such rows read the JSON
                return f" AND ({folded} IN ({listed}) OR c.{column} IS NULL)"
            return f" AND {folded} IN ({listed})"  # a NULL slot is a null value: no match
        return ""

    # -- row sources ------------------------------------------------------------------------
    def source(self, t: ChunkTable, extra: str = "", hint: str = "") -> str:
        """One row per record, in reading order: a chunk's ``records`` array, else its
        ``record``; with layout ``"row"``, the row's JSON column. ``extra``: more selected
        columns (``, c.t1 AS x0``); ``hint``: a further condition on ``c`` (``AND ...``)."""
        meta, order, where = f"c.{t.metadata}", f"c.{t.order}", self.caller(t.where, t.params)
        if t.layout == "row":
            if self.pg:
                return (
                    f"SELECT {order} AS _ci, 0 AS _ri, {meta} AS rec{extra} FROM {t.table} c "
                    f"WHERE ({where}){hint}"
                )
            return (
                f"SELECT {order} AS _ci, -1 AS _ri, {meta} AS doc, '$' AS pre{extra} "
                f"FROM {t.table} c WHERE ({where}){hint}"
            )
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
