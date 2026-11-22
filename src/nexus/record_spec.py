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

"""Records queries: the declarative spec, its validation and value resolution.

A records question ("how many open orders by month", "top 5 customers by amount") is a
computation over the rows of a table. A model writes a small JSON spec, never SQL;
``parse_spec`` checks it against the table's schema profile (``nexus.table_profile``) and
returns a resolved ``RecordQuery``: identifiers allow-listed, values normalised, the result
shape decided. Two engines evaluate a ``RecordQuery`` with the same semantics:

* ``nexus.record_eval``: Python over records in memory (the reference, used as the oracle);
* ``nexus.record_sql``: parameterised SQL over records stored in chunk metadata
  (PostgreSQL JSONB, SQLite JSON1).

Spec (v1 keys ``filters``, ``metric``, ``field``, ``group_by`` (string) and ``limit`` still work)::

    {"document": "<table>",
     "where": {"and"|"or": [cond, ...]} | {"not": cond}
              | {"field": f, "op": "eq|ne|gt|gte|lt|lte|contains|in|is_null", "value": v},
     "filters": [cond, ...],                       # v1: AND of conditions
     "group_by": f | [f | {"field": f, "date_trunc": "day|week|month|quarter|year"}],
     "metrics": [{"op": "count|count_distinct|sum|avg|min|max", "field": f, "as": name}],
     "metric": "count|count_distinct|sum|avg|min|max|list", "field": f,   # v1: one metric
     "having": [cond over metric names],
     "order_by": [{"by": metric | group field | field, "dir": "asc|desc"}],
     "limit": n, "fields": [f, ...],               # list: projection
     "join": {"document": "<table>", "as": "c", "on": {"<left field>": "<right field>"},
              "type": "inner|left"}}

Fields of a joined table are written ``"<as>.<field>"``; nested fields ``"address.city"``.

Semantics (both engines; values as in ``nexus.record_values``):

* ``eq``/``in``/``ne`` compare numbers numerically when both sides are numbers, else the
  trimmed, lower-cased texts; ``gt``..``lte`` likewise (texts in code-point order, so ISO
  dates order correctly); ``contains`` is a case-insensitive substring; ``is_null`` is true
  for a missing, null or blank value; a condition on a missing value is false (``ne``: true);
* with a complete value list in the profile, a text value is matched to every stored
  spelling that normalises the same (``"mid market"`` = ``"Mid-Market"`` = ``"MID_MARKET "``);
  a value with no such spelling is reported as not found, with the closest stored values,
  instead of computing 0;
* ``min``/``max`` are numeric on numeric columns, else the text minimum/maximum;
  ``count_distinct`` counts distinct normalised texts; groups are keyed by normalised text
  (``"(empty)"`` for blanks) and shown with their last spelling in code-point order;
* default order: lists in source order; groups by the first metric (descending), then label.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Any

from .record_values import (
    fold,
    key_text,
    normalize_value,
    number_of,
    text_of,
)

# fmt: off
__all__ = [
    "MAX_GROUPS", "MAX_LIST", "METRICS", "OPS", "TRUNCS", "Cond", "Field", "Group", "Join",
    "Metric", "Option", "Order", "RecordQuery", "RecordQueryError", "fold", "key_text",
    "normalize_value", "number_of", "parse_spec", "text_of",
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


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
class _Columns:
    """Allow-listed columns of the base (and joined) table, from their profiles."""

    def __init__(
        self,
        profile: dict[str, Any],
        join_profile: dict[str, Any] | None,
        alias: str | None,
        current: bool,
    ):
        self.base = {str(c["name"]).casefold(): c for c in profile.get("columns") or []}
        self.join = {
            str(c["name"]).casefold(): c for c in (join_profile or {}).get("columns") or []
        }
        self.alias = (alias or "").casefold()
        self.current = current
        self.fields: list[Field] = []
        self.meta: list[dict[str, Any]] = []

    def resolve(self, name: Any, role: str) -> int:
        raw = str(name or "").strip()
        if not raw:
            raise RecordQueryError(f"a {role} field is missing")
        side, column = "base", self.base.get(raw.casefold())
        if column is None and self.alias and raw.casefold().startswith(self.alias + "."):
            side, column = "join", self.join.get(raw.casefold()[len(self.alias) + 1 :])
        if column is None:
            known = sorted(str(c["name"]) for c in self.base.values())
            if self.alias:
                known += sorted(f"{self.alias}.{c['name']}" for c in self.join.values())
            raise RecordQueryError(f"unknown {role} field '{raw}' (fields: {', '.join(known)})")
        path = tuple(str(p) for p in column.get("path") or [column["name"]])
        shown = str(column["name"]) if side == "base" else f"{self.alias}.{column['name']}"
        item = Field(side, path, shown, str(column.get("type")) in NUMERIC_TYPES)
        if item not in self.fields:
            self.fields.append(item)
            self.meta.append(column)
        return self.fields.index(item)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return list(value) if isinstance(value, list | tuple) else [value]


def _option(value: Any) -> Option:
    text = text_of(value)
    if text is None:
        raise RecordQueryError("a condition value is null (use op is_null)")
    return Option(number_of(value), fold(text) or "", text)


def _closest(value: str, column: dict[str, Any]) -> list[list[Any]]:
    values = column.get("values") or column.get("top") or []
    norms = {}
    for text, count in values:
        norms.setdefault(normalize_value(text), [text, count])
    hits = difflib.get_close_matches(normalize_value(value), list(norms), n=3, cutoff=0.5)
    return [norms[h] for h in hits] or [list(v) for v in values[:3]]


def _match_values(
    cols: _Columns,
    index: int,
    raw_options: list[Any],
    required: bool,
    query_notes: list[str],
    not_found: list[dict[str, Any]],
) -> tuple[Option, ...]:
    """Options for an equality: each value plus every stored spelling that normalises the same.
    With the column's complete value list, a value with no such spelling is reported (not found);
    it is ``required`` (no row can match) when the condition must hold and no option exists."""
    column, fld = cols.meta[index], cols.fields[index]
    known = column.get("values") or column.get("top") or []
    complete = bool(column.get("values_complete")) and cols.current and fld.side == "base"
    out: list[Option] = []
    missing: list[dict[str, Any]] = []
    for option in (_option(v) for v in raw_options):
        out.append(option)
        if option.number is not None and fld.numeric:
            continue
        wanted = normalize_value(option.text)
        variants = [str(t) for t, _ in known if normalize_value(t) == wanted]
        out += [_option(t) for t in variants if fold(t) != option.folded]
        if variants and not any(fold(t) == option.folded for t in variants):
            query_notes.append(
                f"'{option.text}' in {fld.name} matched the stored value(s) "
                + ", ".join(f"'{t}'" for t in variants)
            )
        if complete and not variants:
            missing.append(
                {"field": fld.name, "value": option.text, "closest": _closest(option.text, column)}
            )
    every_missing = required and len(missing) == len(raw_options)
    not_found += [{**item, "required": every_missing} for item in missing]
    seen, unique = set(), []
    for option in out:
        if (option.number, option.folded) not in seen:
            seen.add((option.number, option.folded))
            unique.append(option)
    return tuple(unique)


def _condition(
    raw: Any,
    cols: _Columns,
    q: RecordQuery,
    required: bool,
    metric_names: dict[str, int] | None = None,
) -> Cond:
    if not isinstance(raw, dict):
        raise RecordQueryError(f"a condition must be an object, got {raw!r}")
    for key in ("and", "or"):
        if key in raw:
            items = [
                _condition(c, cols, q, required and key == "and", metric_names)
                for c in _as_list(raw[key])
            ]
            if not items:
                raise RecordQueryError(f"'{key}' needs at least one condition")
            return items[0] if len(items) == 1 else Cond(key, items)
    if "not" in raw:
        return Cond("not", [_condition(raw["not"], cols, q, False, metric_names)])
    op = str(raw.get("op") or "eq").lower().replace("not_null", "is_null")
    if op not in OPS:
        raise RecordQueryError(f"unknown operator '{op}' (operators: {', '.join(OPS)})")
    if metric_names is not None:
        name = str(raw.get("field") or raw.get("metric") or "").strip().casefold()
        if name not in metric_names:
            raise RecordQueryError(
                f"having refers to '{name}', not a metric ({', '.join(metric_names)})"
            )
        if op in ("contains", "in", "is_null"):
            raise RecordQueryError(f"having does not support '{op}'")
        option = _option(raw.get("value"))
        index = metric_names[name]
        if option.number is None and not q.metrics[index].text:
            raise RecordQueryError(
                f"having compares the number {q.metrics[index].name} with '{option.text}'"
            )
        return Cond(op, index=index, metric=True, options=(option,))
    index = cols.resolve(raw.get("field"), "filter")
    if op == "is_null":
        flag = raw.get("value", True)
        flag = (
            flag
            if isinstance(flag, bool)
            else str(flag).strip().lower() not in ("false", "0", "no")
        )
        if str(raw.get("op")).lower() == "not_null":
            flag = not flag
        return Cond(op, index=index, flag=flag)
    value = raw.get("value")
    if op in ("eq", "in", "ne"):
        values = _as_list(value) if op == "in" else [value]
        if not values:
            raise RecordQueryError("'in' needs at least one value")
        options = _match_values(cols, index, values, required and op != "ne", q.notes, q.not_found)
        return Cond("in" if op == "in" else op, index=index, options=options)
    if isinstance(value, list | dict):
        raise RecordQueryError(f"'{op}' takes one value")
    return Cond(op, index=index, options=(_option(value),))


def _join(raw: dict[str, Any], cols: _Columns) -> tuple[int, int, str]:
    on = raw.get("on")
    if isinstance(on, dict) and "left" in on:
        pairs = [(on.get("left"), on.get("right"))]
    elif isinstance(on, dict):
        pairs = list(on.items())
    elif isinstance(on, list | tuple) and on and isinstance(on[0], dict):
        pairs = [(p.get("left"), p.get("right")) for p in on]
    elif isinstance(on, list | tuple) and len(on) == 2 and all(isinstance(p, str) for p in on):
        pairs = [tuple(on)]
    else:
        pairs = []
    if len(pairs) != 1:
        raise RecordQueryError(
            'a join needs exactly one key pair: {"on": {"<field>": "<joined field>"}}'
        )
    left, right = pairs[0]
    right_name = str(right or "")
    if not right_name.casefold().startswith(cols.alias + "."):
        right_name = f"{cols.alias}.{right_name}"
    kind = str(raw.get("type") or "inner").lower()
    if kind not in ("inner", "left"):
        raise RecordQueryError("join type must be inner or left")
    return cols.resolve(left, "join"), cols.resolve(right_name, "join"), kind


def _metrics(spec: dict[str, Any], cols: _Columns) -> list[Metric]:
    raw = spec.get("metrics")
    if raw is None:
        name = str(spec.get("metric") or "count").lower()
        raw = [] if name == "list" else [{"op": name, "field": spec.get("field")}]
    out: list[Metric] = []
    for item in _as_list(raw):
        item = item if isinstance(item, dict) else {"op": item}
        op = str(item.get("op") or item.get("metric") or "count").lower()
        if op not in METRICS:
            raise RecordQueryError(f"unknown metric '{op}' (metrics: {', '.join(METRICS)}, list)")
        index = -1 if op == "count" else cols.resolve(item.get("field"), "metric")
        text = op in ("min", "max") and not cols.fields[index].numeric
        kind = cols.meta[index].get("type") if index >= 0 else None
        if op in ("sum", "avg") and kind in ("date", "boolean", "object", "array"):
            raise RecordQueryError(
                f"'{op}' needs a numeric field; '{cols.fields[index].name}' is {kind}"
            )
        default = op if index < 0 else f"{op}({cols.fields[index].name})"
        name = str(item.get("as") or default).strip() or default
        out.append(Metric(op, index, name, text))
    return out


def _groups(spec: dict[str, Any], cols: _Columns) -> list[Group]:
    out = []
    for item in _as_list(spec.get("group_by")):
        if isinstance(item, dict):
            name, trunc = item.get("field"), item.get("date_trunc") or item.get("trunc")
        else:
            name, trunc = (
                item,
                spec.get("date_trunc") if len(_as_list(spec.get("group_by"))) == 1 else None,
            )
        trunc = str(trunc).lower() if trunc else None
        if trunc and trunc not in TRUNCS:
            raise RecordQueryError(f"unknown date_trunc '{trunc}' ({', '.join(TRUNCS)})")
        index = cols.resolve(name, "group")
        shown = cols.fields[index].name
        out.append(Group(index, trunc, f"{trunc}({shown})" if trunc else shown))
    if len(out) > 3:
        raise RecordQueryError("group by at most 3 fields")
    return out


def _order(spec: dict[str, Any], cols: _Columns, q: RecordQuery) -> list[Order]:
    out: list[Order] = []
    if q.mode == "scalar":
        return out
    metric_names = {m.name.casefold(): i for i, m in enumerate(q.metrics)}
    metric_names.update({m.op: i for i, m in enumerate(q.metrics) if m.op not in metric_names})
    group_names = {g.name.casefold(): i for i, g in enumerate(q.groups)}
    group_names.update({cols.fields[g.index].name.casefold(): i for i, g in enumerate(q.groups)})
    for item in _as_list(spec.get("order_by")):
        item = item if isinstance(item, dict) else {"by": item}
        by = str(item.get("by") or item.get("field") or item.get("metric") or "").strip()
        desc = str(item.get("dir") or item.get("direction") or "desc").lower().startswith("desc")
        if q.mode == "list":
            out.append(Order("field", cols.resolve(by, "order"), desc))
        elif by.casefold() in metric_names:
            out.append(Order("metric", metric_names[by.casefold()], desc))
        elif by.casefold() in group_names and q.mode == "group":
            out.append(Order("group", group_names[by.casefold()], desc))
        else:
            raise RecordQueryError(f"cannot order by '{by}': use a metric or a group field")
    return out


def _where(spec: dict[str, Any]) -> Any:
    parts = list(_as_list(spec.get("filters")))
    if spec.get("where"):
        parts.append(spec["where"])
    if not parts:
        return None
    return parts[0] if len(parts) == 1 else {"and": parts}


def _limit(raw: Any, default: int, cap: int) -> int:
    """A row/group limit in [1, cap]; ``default`` when absent; a non-integer says why."""
    if not raw:  # absent, empty or 0: the default (as before)
        return default
    try:
        value = int(raw) if not isinstance(raw, bool) else None
    except (TypeError, ValueError):
        value = None
    if value is None:
        raise RecordQueryError(f"limit must be a whole number (got {str(raw)[:40]!r})")
    return max(1, min(cap, value))


def parse_spec(
    spec: dict[str, Any],
    profile: dict[str, Any],
    join_profile: dict[str, Any] | None = None,
    current: bool = True,
) -> RecordQuery:
    """Validate ``spec`` against the table's schema ``profile`` (and the joined table's) and
    resolve it. ``current``: the profile describes the stored rows as they are now (a stale
    profile still allow-lists fields but never reports a value as not found)."""
    if not isinstance(spec, dict):
        raise RecordQueryError("the records spec must be an object")
    if not (profile or {}).get("columns"):
        raise RecordQueryError("the table has no profiled fields")
    raw_join = spec.get("join") if isinstance(spec.get("join"), dict) else None
    alias = None
    if raw_join:
        if not join_profile:
            raise RecordQueryError(
                f"the joined table '{raw_join.get('document')}' has no profiled fields"
            )
        doc = str(raw_join.get("document") or "")
        alias = str(raw_join.get("as") or doc.rsplit("/", 1)[-1].rsplit(".", 1)[-1]).strip()
    cols = _Columns(profile, join_profile, alias, current)
    metric_name = str(spec.get("metric") or "").lower()
    q = RecordQuery(document=str(spec.get("document") or ""), mode="scalar", fields=cols.fields)
    if raw_join:
        left, right, kind = _join(raw_join, cols)
        q.join = Join(str(raw_join.get("document") or ""), alias or "", left, right, kind)
    where = _where(spec)
    q.where = _condition(where, cols, q, True) if where else None
    projection_only = (
        metric_name in ("", "list")
        and spec.get("fields")
        and not spec.get("metrics")
        and not spec.get("group_by")
    )
    if metric_name == "list" or projection_only:
        q.mode = "list"
        names = _as_list(spec.get("fields")) or [
            c["name"] for c in profile["columns"] if len(c.get("path") or [1]) == 1
        ]
        q.projection = [cols.resolve(n, "list") for n in names]
        q.limit = _limit(spec.get("limit"), DEFAULT_LIST, MAX_LIST)
    else:
        q.groups = _groups(spec, cols)
        q.metrics = _metrics(spec, cols) or [Metric("count", -1, "count")]
        q.mode = "group" if q.groups else "scalar"
        q.limit = _limit(spec.get("limit"), MAX_GROUPS, MAX_GROUPS) if q.groups else 1
        if spec.get("having"):
            if not q.groups:
                raise RecordQueryError("having needs group_by")
            names = {m.name.casefold(): i for i, m in enumerate(q.metrics)}
            names.update({m.op: i for i, m in enumerate(q.metrics) if m.op not in names})
            q.having = _condition({"and": _as_list(spec["having"])}, cols, q, False, names)
    q.order = _order(spec, cols, q)
    from .record_render import describe

    q.description = describe(q)
    return q
