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

"""CSV files as typed tables.

``parse_csv_table`` reads a CSV with ``csv.DictReader`` (delimiter sniffed among
``, ; | tab``; leading title lines skipped) and types each column once: a column whose
every value is a plain number becomes ``int``/``float`` (``1,234.50`` -> ``1234.5``),
except identifier-like columns (leading zeros, or names such as ``id``, ``zip``,
``phone``) which keep their text. ``group_rows`` packs row narratives into row-group
chunks and reports which rows each chunk holds, so callers can attach the rows as
``metadata.records``.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Any

__all__ = ["CsvTable", "group_rows", "parse_csv_table", "row_text"]

_DELIMITERS = ",;|\t"
_PLAIN_NUMBER = re.compile(r"^[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$")
_KEEP_TEXT_NAME = re.compile(
    r"(?:^|_)(?:id|ids|uuid|code|zip|zipcode|postcode|postal|pin|phone|mobile|tel|ssn|account|acct|no|nr"
    r"|number|ref|sku|isbn|iban|card)(?:$|_)",
    re.IGNORECASE,
)


@dataclass
class CsvTable:
    """A parsed CSV: column names, display rows (source text) and typed rows."""

    columns: list[str]
    rows: list[dict[str, str]] = field(default_factory=list)
    typed_rows: list[dict[str, Any]] = field(default_factory=list)
    delimiter: str = ","


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()).strip(
        "_"
    )


def _numeric_column(name: str, values: list[str]) -> bool:
    present = [v for v in values if v != ""]
    if not present or _KEEP_TEXT_NAME.search(_norm(name)):
        return False
    for value in present:
        if not _PLAIN_NUMBER.match(value):
            return False
        digits = value.lstrip("+-")
        if len(digits) > 1 and digits.startswith("0") and not digits.startswith("0."):
            return False  # leading zeros: an identifier, not a quantity
    return True


def _to_number(value: str) -> int | float:
    clean = value.replace(",", "")
    number = float(clean)
    return int(number) if "." not in clean and abs(number) < 2**53 else number


def _sniff(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=_DELIMITERS).delimiter
    except csv.Error:
        counts = {d: sample.count(d) for d in _DELIMITERS}
        return max(counts, key=lambda d: counts[d]) if any(counts.values()) else ","


def parse_csv_table(text: str) -> CsvTable | None:
    """Parse CSV text into a typed table (``None`` when it has no header and data row)."""
    clean = text.replace("\r\n", "\n").replace("\r", "\n").strip().lstrip("﻿")
    lines = [line for line in clean.split("\n") if line.strip()]
    if len(lines) < 2:
        return None
    delimiter = _sniff("\n".join(lines[:20]))
    # Skip title lines above the header: the header is the first line with the delimiter.
    start = next((i for i, line in enumerate(lines) if delimiter in line), None)
    if start is None or start >= len(lines) - 1:
        return None
    reader = csv.DictReader(io.StringIO("\n".join(lines[start:])), delimiter=delimiter)
    columns = [c.strip() for c in (reader.fieldnames or []) if c and c.strip()]
    if len(columns) < 1:
        return None
    rows: list[dict[str, str]] = []
    for raw in reader:
        row = {
            k.strip(): (v.strip() if isinstance(v, str) else "")
            for k, v in raw.items()
            if k and k.strip()
        }
        extra = raw.get(None)  # values past the header width are kept, never dropped
        if extra:
            row["_extra"] = delimiter.join(str(x) for x in extra)
        if any(v for v in row.values()):
            rows.append(row)
    if not rows:
        return None
    numeric = {c for c in columns if _numeric_column(c, [r.get(c, "") for r in rows])}
    typed = [
        {
            k: (_to_number(v) if k in numeric and v != "" else (v if v != "" else None))
            for k, v in r.items()
        }
        for r in rows
    ]
    return CsvTable(columns=columns, rows=rows, typed_rows=typed, delimiter=delimiter)


def row_text(row_number: int, row: dict[str, Any]) -> str:
    """``[Row ID: n] col: value | ...`` (empty values left out)."""
    items = [f"{k}: {v}" for k, v in row.items() if v is not None and v != ""]
    return f"[Row ID: {row_number}] " + " | ".join(items)


def group_rows(
    texts: list[str],
    header: str = "",
    max_chars: int = 1500,
    max_tokens: int | None = None,
    token_costs: list[int] | None = None,
    header_tokens: int = 0,
) -> list[tuple[str, int, int]]:
    """Pack row texts into chunks of about ``max_chars`` (and at most ``max_tokens`` when
    the rows' ``token_costs`` are given); returns ``(text, first, last)`` with
    ``first``/``last`` as 0-based row positions (inclusive). The header is repeated in
    every chunk."""
    groups: list[tuple[str, int, int]] = []
    prefix = f"{header}\n" if header else ""
    by_tokens = bool(max_tokens) and token_costs is not None
    current: list[str] = []
    first = 0
    size, tokens = len(prefix), header_tokens
    for pos, text in enumerate(texts):
        text = text.strip()
        cost = token_costs[pos] + 1 if by_tokens else 0  # type: ignore[index]
        over_tokens = by_tokens and tokens + cost > max_tokens  # type: ignore[operator]
        if current and (size + len(text) + 1 > max_chars or over_tokens):
            groups.append((prefix + "\n".join(current), first, pos - 1))
            current, size, tokens = [], len(prefix), header_tokens
        if not current:
            first = pos
        current.append(text)
        size += len(text) + 1
        tokens += cost
    if current:
        groups.append((prefix + "\n".join(current), first, len(texts) - 1))
    return groups
