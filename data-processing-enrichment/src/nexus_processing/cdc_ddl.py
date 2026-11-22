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

"""DDL statements in a change stream that remove a table's rows (standard library only).

A binlog / logical-replication query event can empty or retire a table without row events:
``TRUNCATE``, ``DROP TABLE`` and renames (``RENAME TABLE a TO b``, ``ALTER TABLE a RENAME TO
b``). ``parse_ddl(query)`` reads every such statement of a query (several statements separated
by ``;``, leading ``/* */``, ``--`` and ``#`` comments, MySQL ``/*! */`` hints, quoted names
with ``` `` ```, ``""`` or ``[]``, schema-qualified names, ``IF EXISTS``, ``TEMPORARY``, ``ONLY``,
``RESTART IDENTITY``, ``CASCADE``/``RESTRICT``). ``ddl_cleared_tables(query, wanted)`` returns
the bare names of the tables whose rows are gone (renames: the old name), limited to
``wanted`` (case-insensitive bare names; empty = every table).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

__all__ = ["DdlChange", "ddl_cleared_tables", "parse_ddl"]

_PART = r"(?:`(?:[^`]|``)*`|\"(?:[^\"]|\"\")*\"|\[[^\]]*\]|[^\s,.;()`\"\[\]]+)"
_NAME = re.compile(rf"{_PART}(?:\s*\.\s*{_PART})*")
_PART_RE = re.compile(_PART)
_LEAD = re.compile(r"\A(?:\s+|/\*(?!!).*?\*/|--[^\n]*(?:\n|\Z)|#[^\n]*(?:\n|\Z))*", re.S)
_HINT = re.compile(r"/\*!\d*\s*(.*?)\*/", re.S)  # MySQL version hints: their content counts
_TRUNCATE = re.compile(r"TRUNCATE(?:\s+TABLE)?(?:\s+ONLY)?\s+(.*)", re.I | re.S)
_DROP = re.compile(r"DROP\s+(?:TEMPORARY\s+)?TABLE(?:\s+IF\s+EXISTS)?\s+(.*)", re.I | re.S)
_RENAME = re.compile(r"RENAME\s+TABLES?\s+(.*)", re.I | re.S)
_ALTER = re.compile(
    rf"ALTER\s+TABLE(?:\s+IF\s+EXISTS)?(?:\s+ONLY)?\s+({_NAME.pattern})\s+RENAME\s+(?:TO|AS)\s+"
    rf"({_NAME.pattern})\s*$",
    re.I | re.S,
)
_TAIL = re.compile(
    r"(?:\s+(?:RESTART|CONTINUE)\s+IDENTITY|\s+CASCADE|\s+RESTRICT|\s+PURGE|\s+WAIT\s+\d+|"
    r"\s+NOWAIT)+\s*$",
    re.I,
)
_TO = re.compile(r"\s+TO\s+", re.I)


@dataclass(frozen=True, slots=True)
class DdlChange:
    verb: str  # "truncate" | "drop" | "rename"
    tables: tuple[tuple[str, ...], ...]  # name parts (schema, table) of the affected tables
    renames: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = ()  # (old, new) for renames


def _unquote(part: str) -> str:
    if part[:1] == "`" and part[-1:] == "`":
        return part[1:-1].replace("``", "`")
    if part[:1] == '"' and part[-1:] == '"':
        return part[1:-1].replace('""', '"')
    if part[:1] == "[" and part[-1:] == "]":
        return part[1:-1]
    return part


def _parts(name: str) -> tuple[str, ...]:
    return tuple(_unquote(p) for p in _PART_RE.findall(name.strip()))


def _split(text: str, sep: str) -> list[str]:
    """``text`` split on ``sep`` outside quotes and brackets."""
    out, cur, quote = [], [], ""
    for ch in text:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = ""
        elif ch in '`"[':
            quote = "]" if ch == "[" else ch
            cur.append(ch)
        elif ch == sep:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return out


def _names(text: str) -> list[tuple[str, ...]]:
    found = []
    for item in _split(_TAIL.sub("", text.strip()), ","):
        m = _NAME.match(item.strip())
        if m and m.group():
            found.append(_parts(m.group()))
    return found


def _statement(stmt: str) -> DdlChange | None:
    stmt = _LEAD.sub("", _HINT.sub(r"\1", stmt)).strip()
    if not stmt:
        return None
    m = _ALTER.match(stmt)
    if m:
        old, new = _parts(m.group(1)), _parts(m.group(2))
        return DdlChange("rename", (old,), ((old, new),))
    m = _TRUNCATE.match(stmt)
    if m:
        names = _names(m.group(1))
        return DdlChange("truncate", tuple(names)) if names else None
    m = _DROP.match(stmt)
    if m:
        names = _names(m.group(1))
        return DdlChange("drop", tuple(names)) if names else None
    m = _RENAME.match(stmt)
    if m:
        pairs = []
        for item in _split(m.group(1), ","):
            halves = _TO.split(item.strip(), maxsplit=1)
            if len(halves) == 2 and halves[0].strip() and halves[1].strip():
                pairs.append((_parts(halves[0]), _parts(halves[1])))
        if pairs:
            return DdlChange("rename", tuple(old for old, _ in pairs), tuple(pairs))
    return None


def parse_ddl(query: str) -> list[DdlChange]:
    """The table-emptying statements of ``query`` (module doc), in order."""
    if not query:
        return []
    changes = []
    for stmt in _split(query, ";"):
        change = _statement(stmt)
        if change is not None:
            changes.append(change)
    return changes


def ddl_cleared_tables(query: str, wanted: Iterable[str] = ()) -> list[str]:
    """Bare names of the tables whose rows ``query`` removes, limited to ``wanted``."""
    allowed = {_parts(w)[-1].casefold() for w in wanted if w and _parts(w)}
    out: list[str] = []
    for change in parse_ddl(query):
        for parts in change.tables:
            bare = parts[-1].strip() if parts else ""
            if bare and (not allowed or bare.casefold() in allowed) and bare not in out:
                out.append(bare)
    return out
