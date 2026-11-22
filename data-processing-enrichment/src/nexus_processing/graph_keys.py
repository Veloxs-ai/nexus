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

"""Guessing a table's primary key from its column names and rows (standard library only).

``guess_primary_key(columns, rows, table=, profile=)`` returns the column that identifies a
row, or ``None``: a column named like a key (``id``, ``<table>_id``, ``customer_id``,
``order_no``, ``sku_code``, ``invoice_number``, ``uuid``; camelCase ``customerId`` too) whose
values are present in every row and all distinct. ``id`` and ``<singular table>_id`` win, then
a key column whose name starts with the singular table name, then the first other key
column. With a table ``profile`` (``table_profile.profile_records``: ``rows``, and per column
``distinct``, ``nulls``, ``distinct_capped``) the whole-table counts decide uniqueness; else the
given rows (a sample can prove a column is not a key, never that it is one).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

__all__ = ["guess_primary_key", "key_like_column"]

_KEY_NAME = re.compile(r"^(?:id|uuid|guid|key|.+_(?:id|uuid|guid|no|num|number|code|key|ref))$")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _snake(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _CAMEL.sub("_", name).casefold()).strip("_")


def _singular(word: str) -> str:
    w = _snake(word.rsplit(".", 1)[-1])
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith(("ses", "xes", "ches", "shes")):
        return w[:-2]
    if w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def key_like_column(name: str) -> bool:
    """True for column names that look like an identifier (``id``, ``order_no``, ``userId``)."""
    return bool(_KEY_NAME.match(_snake(name)))


def _column_name(column: Any) -> str:
    return str(column.get("name", "")) if isinstance(column, Mapping) else str(column)


def _unique_in_rows(name: str, rows: Sequence[Mapping[str, Any]]) -> bool:
    seen: set[Any] = set()
    for row in rows:
        value = row.get(name) if isinstance(row, Mapping) else None
        if value is None or isinstance(value, bool | float):
            return False
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return False
        if value in seen:
            return False
        seen.add(value)
    return bool(seen)


def _unique_in_profile(name: str, profile: Mapping[str, Any]) -> bool | None:
    rows = int(profile.get("rows") or 0)
    for col in profile.get("columns") or ():
        if str(col.get("name", "")) != name:
            continue
        if rows <= 0 or col.get("distinct_capped") or col.get("distinct") is None:
            return None  # the profile cannot tell: fall back to the rows
        if col.get("type") in ("float", "boolean", "bool"):
            return False
        return int(col.get("nulls") or 0) == 0 and int(col.get("distinct") or 0) == rows
    return None


def guess_primary_key(
    columns: Sequence[Any],
    rows: Sequence[Mapping[str, Any]] = (),
    *,
    table: str | None = None,
    profile: Mapping[str, Any] | None = None,
) -> str | None:
    """The column that identifies a row of ``table``, or ``None`` (see the module doc).

    ``columns`` are names or profile column dicts (``{"name": ...}``), in table order."""
    singular = _singular(table) if table else ""
    best: tuple[int, int, str] | None = None
    for order, column in enumerate(columns):
        name = _column_name(column)
        snake = _snake(name)
        if not name or not _KEY_NAME.match(snake):
            continue
        unique = _unique_in_profile(name, profile) if profile else None
        if unique is None:
            unique = _unique_in_rows(name, rows) if rows else False
        if not unique:
            continue
        if snake == "id" or (singular and snake in (f"{singular}_id", f"{singular}_key")):
            rank = 0
        elif singular and snake.startswith(singular + "_"):
            rank = 1
        else:
            rank = 2
        if best is None or (rank, order) < best[:2]:
            best = (rank, order, name)
    return best[2] if best else None
