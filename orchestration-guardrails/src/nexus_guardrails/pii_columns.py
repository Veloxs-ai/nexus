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

"""Column-aware PII masking for table rows (records).

Regex masking over every string value rewrites data that questions depend on: order
ids, account numbers, timestamps and amounts that happen to look like phone numbers or
cards. Records are therefore masked **by column**: each column is classified once,
from its name and a sample of its values, and then

- a PII column (email, phone, SSN / national id, card, secret) has every value masked;
- an identifier, timestamp, numeric or boolean column is never masked;
- a free-text column gets the context-aware text detectors (``mask_pii``).

With a ``token_secret`` a PII value becomes a deterministic per-secret token
(``[EMAIL:3f9a1c2b7d]``) instead of a constant mask, so equality, grouping and
distinct counts still work on masked data.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from .config import PiiConfig
from .normalization import luhn_valid
from .pii import _DIALABLE, PATTERNS, mask_detector, mask_pii

__all__ = [
    "COLUMN_KINDS",
    "PII_COLUMN_KINDS",
    "classify_column",
    "classify_columns",
    "mask_record",
    "mask_records",
    "mask_value",
    "merge_column_kinds",
]

PII_COLUMN_KINDS = ("secret", "email", "phone", "ssn", "national_id", "credit_card")
COLUMN_KINDS = (*PII_COLUMN_KINDS, "identifier", "timestamp", "numeric", "boolean", "text", "empty")

_KIND_MASKS = {
    "secret": "[SECRET]",
    "email": "[EMAIL]",
    "phone": "[PHONE]",
    "ssn": "[SSN]",
    "national_id": "[NATIONAL_ID]",
    "credit_card": "[CREDIT_CARD]",
}
# Kind -> the PiiConfig detector that must be enabled for the column to be masked.
_KIND_DETECTOR = {
    "secret": "api_key",
    "email": "email",
    "phone": "phone",
    "ssn": "ssn",
    "national_id": "ssn",
    "credit_card": "credit_card",
}

_NAME_KINDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "secret",
        re.compile(
            r"(?:^|_)(?:password|passwd|pwd|secret|api_?key|access_?key|token|private_?key"
            r"|otp|pin|cvv|cvc)(?:$|_)"
        ),
    ),
    ("email", re.compile(r"(?:^|_)e_?mails?(?:$|_)")),
    (
        "phone",
        re.compile(
            r"(?:^|_)(?:phone|phones|mobile|cell|cellphone|tel|telephone|fax|msisdn|whatsapp"
            r"|contact_(?:number|no|num))(?:$|_)"
        ),
    ),
    ("ssn", re.compile(r"(?:^|_)(?:ssn|social_security(?:_number|_no)?)(?:$|_)")),
    (
        "national_id",
        re.compile(
            r"(?:^|_)(?:national_id|tax_id|tin|aadhaar|aadhar|passport(?:_number|_no)?"
            r"|pan_number|pan_no|driving_licen[cs]e|driver_licen[cs]e)(?:$|_)"
        ),
    ),
)
# Card columns are confirmed by their values (a "card_type" of "visa" is not a card number).
_CARD_NAME = re.compile(
    r"(?:^|_)(?:cc|ccn|pan|credit_card|debit_card|card_number|card_no|card_num|card)"
    r"(?:$|_)"
)
_IDENTIFIER_NAME = re.compile(
    r"(?:^|_)(?:id|ids|uuid|guid|key|code|ref|reference|no|nr|num|number|sku|order|invoice|account|acct"
    r"|serial|tracking|isbn|barcode|pk|slug|hash|version)(?:$|_)"
)
_TIMESTAMP_NAME = re.compile(
    r"(?:^|_)(?:date|time|ts|timestamp|datetime|created|updated|modified|deleted|at|dob|birth"
    r"|birthdate)(?:$|_)"
)
_NUMBER_VALUE = re.compile(r"^[-+]?(?:[$€£₹¥]\s?)?\d[\d,]*(?:\.\d+)?%?$")
_DATE_VALUE = re.compile(
    r"^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?$"
)
_SAMPLE = 200
_VALUE_SHARE = 0.6


def _norm_name(name: str) -> str:
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(name))
    return re.sub(r"[^a-z0-9]+", "_", spaced.lower()).strip("_")


def _share(values: list[str], test: Any) -> float:
    return sum(1 for v in values if test(v)) / len(values) if values else 0.0


def _is_card(value: str) -> bool:
    match = PATTERNS["credit_card"].fullmatch(value.strip())
    return bool(match) and luhn_valid(value)


def _is_formatted_phone(value: str) -> bool:
    value = value.strip()
    return bool(PATTERNS["phone"].fullmatch(value)) and (
        value.startswith("+") or not value.isdigit()
    )


_CONTACT_NAME = re.compile(r"(?:^|_)(?:contact|contacts|emergency|alt_?(?:no|number))(?:$|_)")


def _is_dialable(value: str) -> bool:
    return bool(_DIALABLE.fullmatch(value))


def classify_column(name: str, values: Iterable[Any]) -> str:
    """Kind of one column from its name and (a sample of) its values; see ``COLUMN_KINDS``."""
    present = [v for v in values if v is not None and v != ""]
    if not present:
        return "empty"
    norm = _norm_name(name)
    for kind, pattern in _NAME_KINDS:
        if pattern.search(norm):
            return kind
    strings = [v.strip() for v in present if isinstance(v, str)]
    scalars = all(isinstance(v, bool | int | float | Decimal | str) for v in present)
    if _CARD_NAME.search(norm) and _share([str(v) for v in present], _is_card) >= _VALUE_SHARE:
        return "credit_card"
    if strings:
        if _share(strings, lambda v: bool(PATTERNS["email"].fullmatch(v))) >= _VALUE_SHARE:
            return "email"
        if _share(strings, lambda v: bool(PATTERNS["ssn"].fullmatch(v))) >= _VALUE_SHARE:
            return "ssn"
        if _share(strings, _is_card) >= _VALUE_SHARE and not _IDENTIFIER_NAME.search(norm):
            return "credit_card"
    # Identifier/timestamp names are trusted only for short values, never for prose.
    prose = strings and _share(strings, lambda v: len(v) > 32 and " " in v) >= 0.3
    if not prose and _IDENTIFIER_NAME.search(norm):
        return "identifier"
    if not prose and _TIMESTAMP_NAME.search(norm):
        return "timestamp"
    if strings and _share(strings, _is_formatted_phone) >= _VALUE_SHARE:
        return "phone"
    # "contact" / "emergency" columns of bare dialable numbers are phone numbers, not amounts.
    if _CONTACT_NAME.search(norm) and _share([str(v).strip() for v in present], _is_dialable) >= (
        _VALUE_SHARE
    ):
        return "phone"
    if all(isinstance(v, bool) for v in present):
        return "boolean"
    if scalars and all(not isinstance(v, str) or _NUMBER_VALUE.match(v.strip()) for v in present):
        return "numeric"
    if (
        strings
        and len(strings) == len(present)
        and _share(strings, lambda v: bool(_DATE_VALUE.match(v))) >= 0.9
    ):
        return "timestamp"
    return "text"


def classify_columns(rows: Iterable[dict[str, Any]], sample: int = _SAMPLE) -> dict[str, str]:
    """Classify every column of ``rows`` once, from the first ``sample`` non-empty values."""
    samples: dict[str, list[Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key, value in row.items():
            bucket = samples.setdefault(str(key), [])
            if len(bucket) < sample and value is not None and value != "":
                bucket.append(value)
    return {key: classify_column(key, values) for key, values in samples.items()}


def merge_column_kinds(
    known: dict[str, str] | None, rows: Iterable[dict[str, Any]], sample: int = _SAMPLE
) -> dict[str, str]:
    """Column kinds for ``rows`` that stay stable over time.

    A column already classified (``known``, e.g. kept from the full-table pass) keeps its
    kind; only new columns, and columns that were ``empty`` before, are classified from
    ``rows``. A CDC stream that masks one changed row at a time therefore never
    re-classifies a ``phone`` column from a single empty or atypical value.
    """
    merged = dict(known or {})
    fresh = classify_columns(rows, sample)
    for column, kind in fresh.items():
        if merged.get(column) in (None, "empty"):
            merged[column] = kind
    return merged


def _token(kind: str, value: Any, secret: str) -> str:
    raw = str(value).strip()
    norm = raw.lower() if kind == "email" else (re.sub(r"\D", "", raw) or raw)
    digest = hmac.new(secret.encode("utf-8"), f"{kind}:{norm}".encode(), hashlib.sha256).hexdigest()
    return f"{_KIND_MASKS[kind][:-1]}:{digest[:10]}]"


def mask_value(value: Any, kind: str, config: PiiConfig, token_secret: str | None = None) -> Any:
    """Mask one value of a column of ``kind``."""
    if value is None or value == "":
        return value
    if kind in _KIND_MASKS:
        if _KIND_DETECTOR[kind] not in config.detectors and kind != "secret":
            return _mask_text_value(value, config, token_secret)
        if isinstance(value, dict | list):
            return _mask_text_value(value, config, token_secret)
        return _token(kind, value, token_secret) if token_secret else _KIND_MASKS[kind]
    if kind == "text":
        return _mask_text_value(value, config, token_secret)
    if isinstance(value, str):
        # Id, time and number columns keep their values, but formats that are never an id
        # or an amount (secrets, e-mail addresses) are masked wherever they appear.
        for detector in _ALWAYS_MASKED:
            if detector in config.detectors:
                value = mask_detector(value, detector)
    return value


_ALWAYS_MASKED = ("jwt", "api_key", "email")


def _mask_text_value(value: Any, config: PiiConfig, token_secret: str | None) -> Any:
    if isinstance(value, str):
        return mask_pii(value, config)
    if isinstance(value, dict):  # nested document: classify its keys by name and value
        return {
            k: mask_value(
                v, classify_column(k, v if isinstance(v, list) else [v]), config, token_secret
            )
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_mask_text_value(v, config, token_secret) for v in value]
    return value


def mask_record(
    record: dict[str, Any],
    column_kinds: dict[str, str],
    config: PiiConfig,
    token_secret: str | None = None,
) -> dict[str, Any]:
    """Mask one row with precomputed column kinds (unknown columns are treated as text)."""
    if not config.enabled or not config.mask:
        return dict(record)
    return {
        key: mask_value(value, column_kinds.get(str(key), "text"), config, token_secret)
        for key, value in record.items()
    }


def mask_records(
    rows: list[dict[str, Any]],
    config: PiiConfig,
    column_kinds: dict[str, str] | None = None,
    token_secret: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Mask a table: classify columns once (unless given), then mask every row by column."""
    kinds = column_kinds if column_kinds is not None else classify_columns(rows)
    return [mask_record(r, kinds, config, token_secret) for r in rows], kinds
