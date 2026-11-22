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

"""The bulk part of ``table_rollups.build_rollups``: rows are read in blocks; per block each
numeric value is parsed once, each column's group key is computed once per distinct raw value,
rows are grouped, and every group's count / exact sum / minimum / maximum is folded in with
one pass over its members. The result is the same as adding the rows one at a time with
``apply_row_change`` (same groups and order, same labels, same sums under the same decimal
context, same first-seen minimum and maximum), only without a function call per row, group and
measure."""

from __future__ import annotations

import decimal
from collections import Counter
from collections.abc import Callable, Iterable
from itertools import islice
from typing import Any

from .record_values import WS, number_of

BLOCK_ROWS = 8192
KEY_CACHE = 4096  # distinct raw values whose group key is remembered per column
_SCALARS = (str, int, float, bool, type(None))


def _getter(path: tuple[str, ...]) -> Callable[[dict[str, Any]], Any]:
    if len(path) == 1:
        key = path[0]
        return lambda row: row.get(key)

    def get(row: Any) -> Any:
        for key in path:
            if not isinstance(row, dict):
                return None
            row = row.get(key)
        return row

    return get


def _parse(values: list[Any]) -> tuple[list[Any], list[Any]]:
    """(number, exact decimal) of each value; None for values without a number."""
    nums: list[Any] = [None] * len(values)
    exact: list[Any] = [None] * len(values)
    for i, value in enumerate(values):
        number = number_of(value)
        if number is None:
            continue
        nums[i] = number
        if isinstance(value, str):
            exact[i] = decimal.Decimal(value.strip(WS))
        else:
            exact[i] = decimal.Decimal(repr(value) if isinstance(value, float) else value)
    return nums, exact


def _fold(
    entry: dict[str, Any],
    members: list[int] | range,
    measures: list[tuple[str, list[Any], list[Any]]],
    labels: list[Any] | None,
    context: decimal.Context,
) -> None:
    """Add the rows ``members`` (positions in the block) to one group."""
    entry["rows"] += len(members)
    if labels is not None:
        held = entry["labels"]
        for label, n in Counter(x for x in (labels[i] for i in members) if x).items():
            held[label] = held.get(label, 0) + n
    present = []
    for position, (name, nums, exact) in enumerate(measures):
        rows = [i for i in members if nums[i] is not None]
        if rows:
            present.append((rows[0], position, name, rows, nums, exact))
    present.sort(key=lambda p: (p[0], p[1]))  # a measure first seen earlier is listed first
    for _, _, name, rows, nums, exact in present:
        stats = entry["m"].get(name)
        if stats is None:
            stats = entry["m"][name] = [0, decimal.Decimal(0), None, None, True]
        values = [nums[i] for i in rows]
        stats[0] += len(rows)
        total = stats[1] if type(stats[1]) is decimal.Decimal else decimal.Decimal(stats[1])
        with decimal.localcontext(context):
            stats[1] = sum((exact[i] for i in rows), total)
        low, high = min(values), max(values)
        if stats[4]:
            stats[2] = low if stats[2] is None else min(stats[2], low)
            stats[3] = high if stats[3] is None else max(stats[3], high)


def accumulate(
    out: dict[str, Any],
    rows: Iterable[Any],
    *,
    caps: list[int],
    key_of: Callable[[dict[str, Any], Any], tuple[Any, Any, Any]],
    new_entry: Callable[[Any, Any], dict[str, Any]],
    context: decimal.Context,
) -> None:
    """Add every dict of ``rows`` to the rollups ``out`` (``build_rollups``' empty structure);
    ``caps``: the group cap of each column; ``key_of(column, row)``: (key, number, label)."""
    names = [".".join(p) for p in out["numbers"]]
    number_get = [_getter(tuple(p)) for p in out["numbers"]]
    columns = out["columns"]
    state = [
        ({g["key"]: g for g in c["groups"]}, {}, cap, _getter(tuple(c["path"])))
        for c, cap in zip(columns, caps, strict=True)
    ]
    it = iter(rows)
    while True:
        chunk = list(islice(it, BLOCK_ROWS))
        if not chunk:
            return
        block = [r for r in chunk if isinstance(r, dict)]
        n = len(block)
        if not n:
            continue
        out["rows"] += n
        measures = []
        for name, get in zip(names, number_get, strict=True):
            nums, exact = _parse([get(row) for row in block])
            measures.append((name, nums, exact))
        _fold(out["all"], range(n), measures, None, context)
        for column, (index, cache, cap, get) in zip(columns, state, strict=True):
            if column.get("exact", True):
                _group(column, block, index, cache, cap, get, key_of, new_entry, measures, context)


def _group(
    column: dict[str, Any],
    block: list[dict[str, Any]],
    index: dict[Any, dict[str, Any]],
    cache: dict[Any, tuple[Any, Any, Any]],
    cap: int,
    get: Callable[[dict[str, Any]], Any],
    key_of: Callable[[dict[str, Any], Any], tuple[Any, Any, Any]],
    new_entry: Callable[[Any, Any], dict[str, Any]],
    measures: list[tuple[str, list[Any], list[Any]]],
    context: decimal.Context,
) -> None:
    """One column over one block. Rows are taken in order until one the column cannot hold
    (a new value past its cap, or one folded text with two numbers): from there on the column
    is not exact, exactly as when the rows are added one by one."""
    members: dict[Any, list[int]] = {}
    labels: list[Any] = [None] * len(block)
    for i, row in enumerate(block):
        raw = get(row)
        memo = (type(raw), raw) if type(raw) in _SCALARS else None
        found = cache.get(memo) if memo is not None else None
        if found is None:
            found = key_of(column, row)
            if memo is not None and len(cache) < KEY_CACHE:
                cache[memo] = found
        key, num, label = found
        entry = index.get(key)
        if entry is None:
            if len(index) >= cap:
                column["exact"] = False
                break
            entry = index[key] = new_entry(key, num)
            column["groups"].append(entry)
        elif entry["num"] != num:
            column["exact"] = False
            break
        labels[i] = label
        part = members.get(key)
        if part is None:
            members[key] = [i]
        else:
            part.append(i)
    for key, part in members.items():
        _fold(index[key], part, measures, labels, context)
