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

"""The resolved records query that ``nexus.record_spec.parse_spec`` returns.

Plain data: fields, conditions, groups, metrics, order and join, plus the spec's limits and
vocabularies. ``nexus.record_eval`` and ``nexus.record_sql`` evaluate it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# fmt: off
__all__ = [
    "DEFAULT_LIST", "MAX_GROUPS", "MAX_LIST", "METRICS", "NUMERIC_TYPES", "OPS", "TRUNCS", "Cond",
    "Field", "Group", "Join", "Metric", "Option", "Order", "RecordQuery", "RecordQueryError",
]
# fmt: on

OPS = ("eq", "ne", "gt", "gte", "lt", "lte", "contains", "in", "is_null")
METRICS = ("count", "count_distinct", "sum", "avg", "min", "max")
TRUNCS = ("day", "week", "month", "quarter", "year")
MAX_LIST = 200
MAX_GROUPS = 100
DEFAULT_LIST = 50
NUMERIC_TYPES = ("integer", "number")


class RecordQueryError(ValueError):
    """The spec cannot be evaluated (unknown field, bad operator ...); the message says why."""


# ---------------------------------------------------------------------------
# The resolved query
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Field:
    side: str  # "base" | "join"
    path: tuple[str, ...]
    name: str  # as written in results ("amount", "c.segment")
    numeric: bool = False  # the profile types the column as integer/number


@dataclass(frozen=True)
class Option:
    number: float | None
    folded: str
    text: str


@dataclass
class Cond:
    """``op`` "and" / "or" / "not" (``items``) or a predicate on ``fields[index]``
    (``metric`` True: on ``metrics[index]``, in ``having``)."""

    op: str
    items: list[Cond] = field(default_factory=list)
    index: int = -1
    metric: bool = False
    options: tuple[Option, ...] = ()
    flag: bool = True  # is_null: true / false


@dataclass(frozen=True)
class Group:
    index: int  # into fields
    trunc: str | None
    name: str


@dataclass(frozen=True)
class Metric:
    op: str
    index: int  # into fields; -1 for count
    name: str
    text: bool = False  # min/max over texts (a non-numeric column)


@dataclass(frozen=True)
class Order:
    kind: str  # "metric" | "group" | "field"
    index: int
    desc: bool


@dataclass(frozen=True)
class Join:
    document: str
    alias: str
    left: int  # into fields
    right: int
    kind: str  # "inner" | "left"


@dataclass
class RecordQuery:
    document: str
    mode: str  # "list" | "group" | "scalar"
    fields: list[Field]
    where: Cond | None = None
    groups: list[Group] = field(default_factory=list)
    metrics: list[Metric] = field(default_factory=list)
    having: Cond | None = None
    order: list[Order] = field(default_factory=list)
    limit: int = DEFAULT_LIST
    projection: list[int] = field(default_factory=list)
    join: Join | None = None
    not_found: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    description: str = ""

    @property
    def impossible(self) -> bool:
        """A required value is not in the table: no row can match (nothing to run)."""
        return any(item.get("required") for item in self.not_found)
