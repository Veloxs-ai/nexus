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

``parse_csv_table`` reads a CSV with one ``csv.reader`` pass (delimiter sniffed among
``, ; | tab``; leading title lines skipped, even a title that contains the delimiter,
while a header above ragged rows is kept) and types each column once: a column whose
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
    if "." not in clean:
        return int(clean)  # exact at any size (float would round past 2**53)
    return float(clean)


def _sniff(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=_DELIMITERS).delimiter
    except csv.Error:
        counts = {d: sample.count(d) for d in _DELIMITERS}
        return max(counts, key=lambda d: counts[d]) if any(counts.values()) else ","


def _first_lines(text: str, count: int) -> list[str]:
    """The first ``count`` non-blank lines, without splitting the whole text."""
    lines: list[str] = []
    pos, size = 0, len(text)
    while pos < size and len(lines) < count:
        end = text.find("\n", pos)
        end = size if end < 0 else end
        line = text[pos:end]
        if line.strip():
            lines.append(line)
        pos = end + 1
    return lines


def _looks_header(record: list[str]) -> bool:
    cells = [c.strip() for c in record]
    return (
        len(cells) > 1
        and all(cells)
        and len(set(cells)) == len(cells)
        and not any(_PLAIN_NUMBER.match(c) for c in cells)
    )


def _header_index(records: list[tuple[list[str], bool]]) -> int:
    """Position of the header among the leading records ``(fields, blank_line_after)``.

    Lines without the delimiter are titles. A line with the delimiter is still a title
    when the next line looks like a header (text names, no numbers) and either it is a
    short line (``Report, Q3``) above a wider header with data of the same width below
    it, or a blank line separates them and data follows. A header above ragged data rows
    is never skipped, because the data row below it does not look like a header."""
    start = 0
    while start < len(records) - 1 and len(records[start][0]) < 2:
        start += 1
    while start < min(len(records) - 1, 10):
        fields, blank_after = records[start]
        nxt = records[start + 1][0]
        if not _looks_header(nxt):
            break
        after = records[start + 2][0] if start + 2 < len(records) else None
        # A short title (one or two fields) above a wider header whose width the data
        # below repeats; a wider all-text *data* row under a real header is not this.
        wider = (
            len(fields) <= 2
            and len(nxt) > len(fields)
            and after is not None
            and len(after) == len(nxt)
            and not _looks_header(after)
        )
        separated = blank_after and after is not None and not _looks_header(after)
        if not (wider or separated):
            break
        start += 1
    return start


def parse_csv_table(text: str) -> CsvTable | None:
    """Parse CSV text into a typed table (``None`` when it has no header and data row)."""
    if "\r" in text:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
    clean = text.strip().lstrip("\ufeff")
    sample = _first_lines(clean, 20)
    if len(sample) < 2:
        return None
    delimiter = _sniff("\n".join(sample))
    if delimiter not in clean:
        return None
    reader = csv.reader(io.StringIO(clean), delimiter=delimiter)
    # Leading records (up to 25) decide where the header is; blank lines are skipped
    # but remembered, since a blank line after a title separates it from the table.
    head: list[tuple[list[str], bool]] = []
    for record in reader:
        if not any(v.strip() for v in record):
            if head and len(record) <= 1:  # a blank line, not a row of empty cells
                head[-1] = (head[-1][0], True)
            continue
        head.append((record, False))
        if len(head) >= 25:
            break
    start = _header_index(head)
    if start >= len(head) - 1 and len(head) < 25:
        return None
    fieldnames = head[start][0]
    width = len(fieldnames)
    keep = [(i, name.strip()) for i, name in enumerate(fieldnames) if name and name.strip()]
    columns = [name for _, name in keep]
    if not columns:
        return None
    names = [name for _, name in keep]
    direct = len(keep) == width  # no blank header names: zip straight
    rows: list[dict[str, str]] = []

    def records():
        for record, _blank in head[start + 1 :]:
            yield record
        yield from reader

    for record in records():
        if len(record) < width:
            record = record + [""] * (width - len(record))
        if direct:
            row = dict(zip(names, map(str.strip, record[:width]), strict=False))
        else:
            row = {name: record[i].strip() for i, name in keep}
        if len(record) > width:  # values past the header width are kept, never dropped
            row["_extra"] = delimiter.join(record[width:])
        if any(row.values()):
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
