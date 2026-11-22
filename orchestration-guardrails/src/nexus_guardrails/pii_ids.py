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

"""Opt-in national-id detectors, each confirmed by its checksum or format rules.

- ``aadhaar``: Indian Aadhaar number, 12 digits (first 2-9), Verhoeff check digit.
- ``pan``: Indian Permanent Account Number ``AAAPA1234A`` (4th letter is the holder type).
- ``iban``: International Bank Account Number, country code + ISO 7064 mod-97 check.

None is a default detector; enable them with ``PiiConfig(detectors=[..., "aadhaar"])``.
"""

from __future__ import annotations

import re

ID_PATTERNS: dict[str, re.Pattern[str]] = {
    "aadhaar": re.compile(r"(?<![\w-])[2-9]\d{3}([ -]?)\d{4}\1\d{4}(?![\w-])"),
    "pan": re.compile(r"\b[A-Z]{3}[ABCFGHJLPT][A-Z]\d{4}[A-Z]\b"),
    "iban": re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b"),
}

_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)

# IBAN length per country (ISO 13616 registry, common countries); others: 15-34.
_IBAN_LENGTHS = {
    "AD": 24, "AE": 23, "AT": 20, "BE": 16, "BG": 22, "BH": 22, "CH": 21, "CY": 28,
    "CZ": 24, "DE": 22, "DK": 18, "EE": 20, "ES": 24, "FI": 18, "FR": 27, "GB": 22,
    "GR": 27, "HR": 21, "HU": 28, "IE": 22, "IL": 23, "IS": 26, "IT": 27, "KW": 30,
    "LT": 20, "LU": 20, "LV": 21, "MT": 31, "NL": 18, "NO": 15, "PK": 24, "PL": 28,
    "PT": 25, "QA": 29, "RO": 24, "SA": 24, "SE": 24, "SI": 19, "SK": 24, "TR": 26,
}  # fmt: skip


def verhoeff_valid(digits: str) -> bool:
    """True when the digit string's last digit is its Verhoeff check digit."""
    check = 0
    for i, ch in enumerate(reversed(digits)):
        check = _D[check][_P[i % 8][int(ch)]]
    return check == 0


def iban_valid(value: str) -> bool:
    """ISO 7064 mod-97 check of an IBAN (spaces ignored) with its country's length."""
    compact = value.replace(" ", "").upper()
    expected = _IBAN_LENGTHS.get(compact[:2])
    if expected is not None and len(compact) != expected:
        return False
    if not 15 <= len(compact) <= 34:
        return False
    rearranged = compact[4:] + compact[:4]
    number = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(number) % 97 == 1


def _aadhaar_ok(text: str, match: re.Match[str]) -> bool:
    return verhoeff_valid(re.sub(r"\D", "", match.group(0)))


def _iban_ok(text: str, match: re.Match[str]) -> bool:
    return iban_valid(match.group(0))


ID_VALIDATORS = {"aadhaar": _aadhaar_ok, "iban": _iban_ok}
