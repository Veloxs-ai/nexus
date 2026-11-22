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

"""Figures written in words, the way grounding compares them with figures written in digits.

``spell_figures(text)`` rewrites English number words and long-form dates in digits, so one fact
written two ways compares equal:

  "thirty days"              -> "30 days"
  "one hundred and twenty"   -> "120"        "twenty-one" -> "21"     "two million" -> "2 million"
  "March 5, 2026"            -> "2026-03-05" "5th of March 2026" -> "2026-03-05"

A number word joined to another word by a hyphen is part of a name and is kept ("priority-one",
"one-off"). Only figure comparison uses the result; the text shown to people is unchanged.
Standard library only.
"""

from __future__ import annotations

import re
from datetime import date

__all__ = ["spell_figures"]

_UNITS = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
_TENS = ["twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
_VALUE = {w: n for n, w in enumerate(_UNITS)} | {w: 20 + 10 * i for i, w in enumerate(_TENS)}
_WORD = r"(?:" + "|".join(sorted([*_VALUE, "hundred", "thousand"], key=len, reverse=True)) + r")"
# a run of number words ("one hundred and twenty", "twenty-one"), not part of a hyphenated name
_RUN = re.compile(
    rf"(?<![\w-])(?<!\w-){_WORD}(?:(?:\s+and\s+|\s+|-){_WORD})*(?![\w-])(?!-\w)",
    re.I,
)
_MONTHS = {
    m: i + 1
    for i, names in enumerate(
        [
            ("january", "jan"),
            ("february", "feb"),
            ("march", "mar"),
            ("april", "apr"),
            ("may",),
            ("june", "jun"),
            ("july", "jul"),
            ("august", "aug"),
            ("september", "sep", "sept"),
            ("october", "oct"),
            ("november", "nov"),
            ("december", "dec"),
        ]
    )
    for m in names
}
_MONTH = r"(?P<mon>" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\.?"
_DAY = r"(?P<day>\d{1,2})(?:st|nd|rd|th)?"
_YEAR = r"(?P<year>(?:19|20)\d{2})"
_DATES = [
    re.compile(rf"(?<![\w-]){_MONTH}\s+{_DAY},?\s+{_YEAR}(?![\w-])", re.I),
    re.compile(rf"(?<![\w-]){_DAY}\s+(?:of\s+)?{_MONTH},?\s+{_YEAR}(?![\w-])", re.I),
]


def _run_value(words: list[str]) -> int | None:
    total, current, seen = 0, 0, False
    for word in words:
        if word == "hundred":
            if not seen or current >= 100:
                return None
            current *= 100
        elif word == "thousand":
            if not seen:
                return None
            total, current = total + current * 1000, 0
        else:
            value = _VALUE[word]
            if seen and current % 100 and (current % 10 or value >= 10):
                return None  # "five three", "twenty eleven": a list, not one number
            current += value
            seen = True
    return total + current if seen else None


def _number(match: re.Match[str]) -> str:
    words = [w.lower() for w in re.split(r"\s+and\s+|\s+|-", match.group(0)) if w]
    value = _run_value(words)
    return match.group(0) if value is None else str(value)


def _date(match: re.Match[str]) -> str:
    month = _MONTHS[match.group("mon").lower()]
    try:
        day = date(int(match.group("year")), month, int(match.group("day")))
    except ValueError:  # "February 30": not a date, left as written
        return match.group(0)
    return day.isoformat()


def spell_figures(text: str) -> str:
    """``text`` with number words and long-form dates written in digits (see the module doc)."""
    if not text:
        return ""
    out = _RUN.sub(_number, text)
    for pattern in _DATES:
        out = pattern.sub(_date, out)
    return out
