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

"""Typed spreadsheet cell values: Excel dates from number formats.

Excel stores a date as a day count (``45352`` is 2024-03-01) and marks it as a date
only through the cell's number format. ``WorkbookStyles`` reads ``xl/styles.xml``
(built-in and custom ``numFmt`` codes per ``cellXfs`` entry) and the workbook's
1900/1904 date system, so XLSX date cells become ISO strings (``2024-03-01``,
``2024-03-01T09:30:00``, ``09:30:00``). ``xls_cell_value`` does the same for legacy
``.xls`` through xlrd's cell types.
"""

from __future__ import annotations

import datetime as _dt
import re
import xml.etree.ElementTree as ET
import zipfile
from typing import Any

__all__ = ["WorkbookStyles", "excel_serial_to_iso", "number_value", "xls_cell_value"]

# Built-in number formats (ECMA-376 18.8.30) that display dates and/or times.
_BUILTIN_DATE = {14, 15, 16, 17, 22, 27, 28, 29, 30, 31, 34, 35, 36, 50, 51, 52, 53, 54, 57, 58}
_BUILTIN_TIME = {18, 19, 20, 21, 32, 33, 45, 46, 47, 55, 56}
_BUILTIN_DATETIME = {22}

_QUOTED = re.compile(r'"[^"]*"|\\.|_.|\*.')
_BRACKET = re.compile(r"\[(?!h\]|hh\]|m\]|mm\]|s\]|ss\])[^\]]*\]", re.IGNORECASE)


def _local(tag: str) -> str:
    return tag.split("}")[-1]


def classify_format(code: str) -> str | None:
    """``"date"``, ``"time"``, ``"datetime"`` or ``None`` for an Excel format code."""
    if not code or code.lower() == "general":
        return None
    section = code.split(";", 1)[0]
    cleaned = _BRACKET.sub("", _QUOTED.sub("", section)).lower()
    # "m" alone is ambiguous (month or minute); "mmm"/"mmmm" (month names) is a date.
    has_date = bool(re.search(r"[dy]|m{3,}", cleaned))
    has_time = bool(re.search(r"[hs]", cleaned)) or "am/pm" in cleaned
    if has_date and has_time:
        return "datetime"
    if has_date:
        return "date"
    if has_time:
        return "time"
    return None


def excel_serial_to_iso(serial: float, kind: str = "date", date1904: bool = False) -> str:
    """Convert an Excel day count to ISO text according to the format ``kind``."""
    base = _dt.datetime(1904, 1, 1) if date1904 else _dt.datetime(1899, 12, 30)
    moment = base + _dt.timedelta(days=float(serial))
    moment = moment.replace(microsecond=0) + _dt.timedelta(seconds=round(moment.microsecond / 1e6))
    if kind == "time" and float(serial) < 1:
        return moment.time().isoformat()
    if kind == "date" or (kind == "datetime" and moment.time() == _dt.time(0)):
        return moment.date().isoformat()
    return moment.isoformat()


def number_value(raw: str) -> int | float | str:
    """Numeric cell text -> int when integral, else float (the text itself if unparseable)."""
    try:
        number = float(raw)
    except ValueError:
        return raw
    if number.is_integer() and "e" not in raw.lower() and abs(number) < 2**53:
        return int(number)
    return number


class WorkbookStyles:
    """Per-style date kinds of one XLSX workbook (``cellXfs`` index -> kind)."""

    def __init__(self, kinds: list[str | None] | None = None, date1904: bool = False) -> None:
        self.kinds = kinds or []
        self.date1904 = date1904

    @classmethod
    def from_zip(cls, zf: zipfile.ZipFile) -> WorkbookStyles:
        names = set(zf.namelist())
        date1904 = False
        if "xl/workbook.xml" in names:
            try:
                root = ET.fromstring(zf.read("xl/workbook.xml"))
                for elem in root.iter():
                    if _local(elem.tag) == "workbookPr":
                        date1904 = elem.attrib.get("date1904", "0").lower() in ("1", "true")
            except ET.ParseError:
                pass
        if "xl/styles.xml" not in names:
            return cls([], date1904)
        try:
            root = ET.fromstring(zf.read("xl/styles.xml"))
        except ET.ParseError:
            return cls([], date1904)
        custom: dict[int, str] = {}
        kinds: list[str | None] = []
        for elem in root.iter():
            if _local(elem.tag) == "numFmt":
                try:
                    custom[int(elem.attrib.get("numFmtId", "-1"))] = elem.attrib.get(
                        "formatCode", ""
                    )
                except ValueError:
                    continue
        for elem in root.iter():
            if _local(elem.tag) != "cellXfs":
                continue
            for xf in elem:
                if _local(xf.tag) != "xf":
                    continue
                try:
                    fmt_id = int(xf.attrib.get("numFmtId", "0"))
                except ValueError:
                    fmt_id = 0
                kinds.append(_kind_of(fmt_id, custom))
            break
        return cls(kinds, date1904)

    def kind(self, style_index: str | None) -> str | None:
        if style_index is None:
            return None
        try:
            idx = int(style_index)
        except ValueError:
            return None
        return self.kinds[idx] if 0 <= idx < len(self.kinds) else None

    def value(self, raw: str, style_index: str | None) -> Any:
        """Typed value of a numeric cell (ISO text for date-formatted cells)."""
        value = number_value(raw)
        kind = self.kind(style_index)
        if kind and isinstance(value, int | float) and 0 <= value < 2958466:  # up to 9999-12-31
            return excel_serial_to_iso(value, kind, self.date1904)
        return value


def _kind_of(fmt_id: int, custom: dict[int, str]) -> str | None:
    if fmt_id in custom:
        return classify_format(custom[fmt_id])
    if fmt_id in _BUILTIN_DATETIME:
        return "datetime"
    if fmt_id in _BUILTIN_DATE:
        return "date"
    if fmt_id in _BUILTIN_TIME:
        return "time"
    return None


def xls_cell_value(xlrd_module: Any, sheet: Any, row: int, col: int, datemode: int) -> Any:
    """Typed value of a legacy ``.xls`` cell (dates as ISO text, booleans as bool)."""
    ctype = sheet.cell_type(row, col)
    value = sheet.cell_value(row, col)
    if ctype == xlrd_module.XL_CELL_DATE:
        try:
            moment = xlrd_module.xldate.xldate_as_datetime(value, datemode)
        except Exception:
            return value
        if value < 1:
            return moment.time().isoformat()
        return moment.date().isoformat() if moment.time() == _dt.time(0) else moment.isoformat()
    if ctype == xlrd_module.XL_CELL_BOOLEAN:
        return bool(value)
    if ctype == xlrd_module.XL_CELL_ERROR:
        return ""
    if isinstance(value, float) and value.is_integer() and abs(value) < 2**53:
        return int(value)
    return value
