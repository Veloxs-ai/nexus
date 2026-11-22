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

"""Records queries: the value semantics both engines share (``record_eval``, ``record_sql``).

A value's *text* is the string, ``"true"``/``"false"`` for booleans, the JSON form of a
number; its *number* is a JSON number or a plain decimal string (never a boolean); texts
compare trimmed and lower-cased; a spelling-insensitive form matches dirty values.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

__all__ = [
    "ISO_DATE_RE",
    "NUMBER_RE",
    "WS",
    "fold",
    "key_text",
    "normalize_value",
    "number_of",
    "text_of",
]

WS = " \t\r\n"  # the blanks trimmed from texts (the SQL engines trim the same characters)
NUMBER_RE = re.compile(r"^[ \t\r\n]*-?[0-9]+(?:\.[0-9]+)?[ \t\r\n]*$")
ISO_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}")
_NON_ALNUM = re.compile(r"[\W_]+")


def text_of(value: Any) -> str | None:
    """The text of a JSON value as the SQL engines see it (None for null)."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value) if math.isfinite(value) else None
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def number_of(value: Any) -> float | None:
    """A JSON number or a plain decimal string as a float (None otherwise, booleans included)."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str) and NUMBER_RE.match(value):
        return float(value)
    return None


def fold(text: str | None) -> str | None:
    """Trimmed, lower-cased text (the comparison form)."""
    return None if text is None else text.strip(WS).lower()


def normalize_value(text: str) -> str:
    """Spelling-insensitive form: lower case, punctuation and underscores as single spaces."""
    return _NON_ALNUM.sub(" ", str(text).lower()).strip()


def key_text(value: Any) -> str | None:
    """Join-key form: integral numbers as integers, other numbers as their shortest decimal,
    texts folded (``1``, ``1.0`` and ``" 1 "`` join; ``"ACME"`` joins ``"acme"``)."""
    text = text_of(value)
    if text is None:
        return None
    number = number_of(value)
    if number is None:
        return fold(text)
    if number == int(number):
        return str(int(number))
    return repr(number)
