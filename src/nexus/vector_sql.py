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

"""pgvector helpers: HNSW index DDL, k-nearest-neighbour SQL, exact vs HNSW by scope size.

A filtered vector search over one HNSW graph shared by many scopes (tenants, projects,
documents) walks the graph until enough rows pass the filter: a small scope needs a long walk
(``hnsw.max_scan_tuples``) and can come back short. An exact scan of a small scope (through the
caller's B-tree on the scope column) is both complete and fast. ``choose_strategy`` picks one
from the scope's vector count; ``knn_sql`` writes the statement and the ``SET LOCAL`` settings
for it; ``vector_index_ddl`` writes the index (``halfvec`` halves its memory; a ``where_sql``
makes it partial). Tables, columns and filters are the caller's.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = ["KnnQuery", "Strategy", "choose_strategy", "knn_sql", "vector_index_ddl"]

_IDENT_PART = r'(?:[A-Za-z_][A-Za-z0-9_]*|"[^"\x00]+")'
_IDENT = re.compile(rf"^{_IDENT_PART}(?:\.{_IDENT_PART})*$")
_OPS = {"cosine": ("<=>", "cosine"), "l2": ("<->", "l2"), "ip": ("<#>", "ip")}
_TYPES = (None, "halfvec")
EXACT_LIMIT = 50_000
MIN_SCAN = 20_000  # pgvector's default hnsw.max_scan_tuples


@dataclass(frozen=True)
class Strategy:
    kind: str  # "exact" | "hnsw"
    ef_search: int = 0
    max_scan_tuples: int = 0
    reason: str = ""


@dataclass(frozen=True)
class KnnQuery:
    """``sql`` takes the query vector (pgvector text form ``"[0.1,0.2,...]"``) first, then the
    ``where_sql`` parameters; run ``settings`` in the same transaction first."""

    sql: str
    settings: list[str] = field(default_factory=list)
    strategy: Strategy | None = None


def _check(identifier: str) -> str:
    if not _IDENT.match(identifier):
        raise ValueError(f"'{identifier}' is not a plain or quoted identifier")
    return identifier


def _vector_type(quantize: str | None, dim: int) -> str:
    if quantize not in _TYPES:
        raise ValueError(f"quantize must be None or 'halfvec', not {quantize!r}")
    if int(dim) <= 0:
        raise ValueError("dim must be positive")
    return f"{quantize or 'vector'}({int(dim)})"


def choose_strategy(
    scope_vectors: int,
    total_vectors: int | None = None,
    *,
    k: int = 40,
    exact_limit: int = EXACT_LIMIT,
    ef_search: int = 100,
    max_scan_cap: int = 1_000_000,
) -> Strategy:
    """``"exact"`` when the scope holds at most ``exact_limit`` vectors (every row is compared:
    full recall, and fast through a B-tree on the scope); else ``"hnsw"`` with an
    ``ef_search`` of at least ``k`` and a ``max_scan_tuples`` large enough for ``k`` rows of the
    scope to pass the filter (about ``4 k / share`` tuples, capped)."""
    scope = max(0, int(scope_vectors))
    if scope <= exact_limit:
        return Strategy("exact", reason=f"{scope} vectors in scope <= {exact_limit}")
    total = max(scope, int(total_vectors or scope))
    share = scope / total if total else 1.0
    scan = int(min(max_scan_cap, max(MIN_SCAN, 4 * k / max(share, 1e-9))))
    return Strategy(
        "hnsw",
        ef_search=max(int(ef_search), int(k)),
        max_scan_tuples=scan,
        reason=f"{scope} vectors in scope ({share:.2%} of {total})",
    )


def vector_index_ddl(
    table: str,
    column: str,
    dim: int,
    *,
    quantize: str | None = None,
    metric: str = "cosine",
    where_sql: str | None = None,
    m: int = 16,
    ef_construction: int = 64,
    name: str | None = None,
    concurrently: bool = False,
    if_not_exists: bool = True,
) -> str:
    """``CREATE INDEX`` of an HNSW graph over ``table.column`` (``quantize="halfvec"``: over the
    column cast to ``halfvec(dim)``, half the memory). ``where_sql`` (the caller's SQL, no
    parameters) makes it partial; the query must repeat that condition to use it."""
    if metric not in _OPS:
        raise ValueError(f"metric must be one of {', '.join(_OPS)}")
    _check(table)
    _check(column)
    kind = _vector_type(quantize, dim)
    expr = f"(CAST({column} AS {kind}))" if quantize else column
    opclass = f"{quantize or 'vector'}_{_OPS[metric][1]}_ops"
    base = re.sub(r"[^A-Za-z0-9_]+", "_", table.split(".")[-1]).strip("_")[:30]
    index = _check(name) if name else f"ix_{base}_{column.strip(chr(34))[:20]}_hnsw"
    parts = ["CREATE INDEX"]
    if concurrently:
        parts.append("CONCURRENTLY")
    if if_not_exists:
        parts.append("IF NOT EXISTS")
    parts += [
        index,
        "ON",
        table,
        f"USING hnsw ({expr} {opclass})",
        f"WITH (m = {int(m)}, ef_construction = {int(ef_construction)})",
    ]
    if where_sql:
        parts.append(f"WHERE {where_sql}")
    return " ".join(parts)


def knn_sql(
    table: str,
    column: str,
    dim: int,
    *,
    exact: bool | None = None,
    quantize: str | None = None,
    metric: str = "cosine",
    where_sql: str = "TRUE",
    select: str = "*",
    limit: int = 40,
    placeholder: str = "%s",
    strategy: Strategy | None = None,
    distance_alias: str = "distance",
) -> KnnQuery:
    """The ``limit`` rows of ``table`` nearest the query vector, with a ``distance`` column
    (``distance_alias``: its name, which must not clash with a selected column).

    ``exact`` (or ``strategy.kind == "exact"``) compares every row matching ``where_sql`` in
    full precision and never walks an HNSW index (the distance is not an index ordering);
    otherwise the ORDER BY matches the index ``vector_index_ddl`` writes with the same
    ``quantize`` / ``metric``, and ``settings`` carries ``hnsw.ef_search``, iterative scan
    and ``hnsw.max_scan_tuples`` from ``strategy``. ``select`` and ``where_sql`` are the
    caller's SQL (``where_sql`` parameters follow the vector's)."""
    if metric not in _OPS:
        raise ValueError(f"metric must be one of {', '.join(_OPS)}")
    _check(table)
    _check(column)
    _check(distance_alias)
    if placeholder not in ("%s", "?"):
        raise ValueError("placeholder must be '%s' or '?'")
    if exact is None:
        exact = strategy is not None and strategy.kind == "exact"
    op = _OPS[metric][0]
    query = f"CAST({placeholder} AS {_vector_type(None, dim)})"
    if exact:
        distance = f"(({column} {op} {query}) + 0)"
        settings: list[str] = []
    else:
        kind = _vector_type(quantize, dim)
        left = f"CAST({column} AS {kind})" if quantize else column
        right = f"CAST({query} AS {kind})" if quantize else query
        distance = f"({left} {op} {right})"
        plan = strategy or Strategy("hnsw", ef_search=max(100, int(limit)), max_scan_tuples=0)
        settings = [f"SET LOCAL hnsw.ef_search = {max(int(plan.ef_search), int(limit))}"]
        settings.append("SET LOCAL hnsw.iterative_scan = relaxed_order")
        if plan.max_scan_tuples:
            settings.append(f"SET LOCAL hnsw.max_scan_tuples = {int(plan.max_scan_tuples)}")
    sql = (
        f"SELECT {select}, {distance} AS {distance_alias} FROM {table} WHERE ({where_sql}) "
        f"ORDER BY {distance_alias} LIMIT {int(limit)}"
    )
    return KnnQuery(sql, settings, strategy)
