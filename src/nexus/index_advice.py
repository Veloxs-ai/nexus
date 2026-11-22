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

"""Index advice for records kept as JSON: which fields deserve an index, and its DDL.

``recommend_indexes(profile, recent_specs)`` ranks the fields that records questions look up
(``eq`` / ``in`` conditions, then ranges) by how often they are asked and how selective they
are; categories with few values are left out (rollups answer them, ``nexus.table_rollups``).
``expression_index_sql(table, column, path, ...)`` writes the ``CREATE INDEX`` for the exact
expression ``nexus.record_sql`` compares (the trimmed, lower-cased text of a JSON field or of a
text slot column), so the index-friendly conditions it adds for a ``"row"`` source can use it.
Names, tables and filters are the caller's; nothing here knows a schema.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .table_profile import key_like

__all__ = ["IndexAdvice", "expression_index_sql", "recommend_indexes", "sql_literal"]

_IDENT_PART = r'(?:[A-Za-z_][A-Za-z0-9_]*|"[^"\x00]+")'
_IDENT = re.compile(rf"^{_IDENT_PART}(?:\.{_IDENT_PART})*$")
_LOOKUP_OPS = ("eq", "in")
_RANGE_OPS = ("gt", "gte", "lt", "lte")
_CATEGORY_VALUES = 50


@dataclass(frozen=True)
class IndexAdvice:
    path: tuple[str, ...]
    name: str
    reason: str  # "lookup" | "range" | "key"
    uses: int
    score: float


def sql_literal(value: Any) -> str:
    """``value`` as a quoted SQL string literal (for DDL filters, which cannot take bound
    parameters)."""
    text = str(value)
    if "\x00" in text:
        raise ValueError("NUL character in an SQL literal")
    return "'" + text.replace("'", "''") + "'"


def _check(identifier: str) -> str:
    if not _IDENT.match(identifier):
        raise ValueError(f"'{identifier}' is not a plain or quoted identifier")
    return identifier


def _walk(where: Any, out: list[tuple[str, str]]) -> None:
    if isinstance(where, list):
        for item in where:
            _walk(item, out)
    elif isinstance(where, Mapping):
        for key in ("and", "or"):
            if key in where:
                _walk(where[key], out)
        if "not" in where:
            _walk(where["not"], out)
        if "field" in where:
            out.append((str(where["field"]), str(where.get("op") or "eq")))


def recommend_indexes(
    profile: Mapping[str, Any],
    recent_specs: Iterable[Mapping[str, Any]] = (),
    max_indexes: int = 3,
    *,
    exclude: Iterable[Any] = (),
    keys: bool = True,
) -> list[IndexAdvice]:
    """Up to ``max_indexes`` fields worth an index, best first.

    ``recent_specs``: records specs recently asked of the table (their ``where`` conditions
    are counted per field). ``exclude``: field paths already indexed (slot columns, say), as
    tuples or dotted names. With ``keys`` a key-like column (a different value on every row)
    is advised even before anyone asked, for point lookups."""
    rows = int(profile.get("rows") or 0)
    by_name = {}
    for column in profile.get("columns") or []:
        by_name[str(column["name"]).casefold()] = column
    skip = {tuple(x.split(".")) if isinstance(x, str) else tuple(x) for x in exclude}
    uses: dict[str, dict[str, int]] = {}
    for spec in recent_specs:
        found: list[tuple[str, str]] = []
        _walk(spec.get("where") if isinstance(spec, Mapping) else None, found)
        for name, op in found:
            column = by_name.get(name.casefold())
            if column is None:
                continue
            kind = "lookup" if op in _LOOKUP_OPS else "range" if op in _RANGE_OPS else ""
            if kind:
                slot = uses.setdefault(str(column["name"]).casefold(), {})
                slot[kind] = slot.get(kind, 0) + 1
    advice = []
    for key, column in by_name.items():
        path = tuple(str(p) for p in column.get("path") or [column["name"]])
        if path in skip or column.get("type") in ("object", "array", "empty"):
            continue
        distinct = int(column.get("distinct") or 0)
        category = bool(column.get("values_complete")) and distinct <= _CATEGORY_VALUES
        unique = key_like(column, rows)
        selective = 1.0 if unique or column.get("distinct_capped") else distinct / max(rows, 1)
        counted = uses.get(key, {})
        lookups, ranges = counted.get("lookup", 0), counted.get("range", 0)
        if category and not ranges:
            continue  # answered from rollups / the profile
        label = str(column["name"])
        if lookups:
            advice.append(IndexAdvice(path, label, "lookup", lookups, lookups * (0.5 + selective)))
        elif ranges and column.get("type") in ("integer", "number", "date"):
            advice.append(IndexAdvice(path, label, "range", ranges, ranges * 0.5))
        elif keys and unique:
            advice.append(IndexAdvice(path, label, "key", 0, 0.25))
    advice.sort(key=lambda a: (-a.score, a.name))
    if keys:  # one unasked key column is enough
        first_key = next((a for a in advice if a.reason == "key"), None)
        advice = [a for a in advice if a.reason != "key" or a is first_key]
    return advice[: max(0, int(max_indexes))]


def _json_path_pg(column: str, path: tuple[str, ...]) -> str:
    parts = ",".join('"' + p.replace("\\", "\\\\").replace('"', '\\"') + '"' for p in path)
    return f"({column} #>> {sql_literal('{' + parts + '}')})"


def _json_path_sqlite(column: str, path: tuple[str, ...]) -> str:
    if any('"' in p for p in path):
        raise ValueError("a double quote in a JSON field name (unsupported)")
    steps = "".join(f'."{p}"' for p in path)
    return f"json_extract({column}, {sql_literal('$' + steps)})"


def expression_index_sql(
    table: str,
    column: str,
    path: Iterable[str] | str | None = None,
    dialect: str = "postgresql",
    *,
    where_sql: str | None = None,
    name: str | None = None,
    form: str = "folded",
    lead: Iterable[str] = (),
    concurrently: bool = False,
    if_not_exists: bool = True,
) -> str:
    """``CREATE INDEX`` on a records field.

    ``column`` is the JSON column (with ``path``, a tuple or dotted name of the field) or a
    typed slot column (``path`` None). ``form``: ``"folded"`` (the trimmed, lower-cased text
    ``nexus.record_sql`` compares for equality), ``"text"`` (the raw text) or ``"plain"`` (the
    slot column itself, e.g. a number slot). ``lead``: columns put before the expression (e.g.
    a document id column). ``where_sql``: a partial-index condition written by the caller
    (literals quoted with ``sql_literal``). ``concurrently`` (PostgreSQL) builds it without
    blocking writes (outside a transaction)."""
    if dialect not in ("postgresql", "sqlite"):
        raise ValueError(f"unsupported dialect '{dialect}'")
    if form not in ("folded", "text", "plain"):
        raise ValueError(f"unsupported form '{form}'")
    pg = dialect == "postgresql"
    _check(table)
    _check(column)
    leading = [_check(c) for c in lead]
    if path is not None:
        steps = tuple(path.split(".")) if isinstance(path, str) else tuple(str(p) for p in path)
        if form == "plain" or not steps:
            raise ValueError("a JSON field needs form 'folded' or 'text' and a path")
        expr = _json_path_pg(column, steps) if pg else _json_path_sqlite(column, steps)
    else:  # PostgreSQL drops a cast of a text column to text, so the column alone matches
        expr = column if form == "plain" or pg else f"CAST({column} AS TEXT)"
    if form == "folded":
        blanks = "E' \\t\\r\\n'" if pg else "char(32, 9, 13, 10)"
        expr = f"lower({'btrim' if pg else 'trim'}({expr}, {blanks}))"
    keys = ", ".join([*leading, f"({expr})" if form != "plain" else expr])
    digest = hashlib.sha1(f"{table}|{keys}|{where_sql}".encode()).hexdigest()[:10]
    base = re.sub(r"[^A-Za-z0-9_]+", "_", table.split(".")[-1]).strip("_")[:30]
    index = _check(name) if name else f"ix_{base}_{digest}"
    parts = ["CREATE INDEX"]
    if concurrently and pg:
        parts.append("CONCURRENTLY")
    if if_not_exists:
        parts.append("IF NOT EXISTS")
    parts += [index, "ON", table, f"({keys})"]
    if where_sql:
        parts.append(f"WHERE {where_sql}")
    return " ".join(parts)
