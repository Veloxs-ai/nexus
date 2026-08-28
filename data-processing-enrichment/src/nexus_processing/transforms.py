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

from __future__ import annotations

import re
from typing import Any

from .config import TransformConfig

EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_PATTERN = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")


def transform_record(record: dict[str, Any], config: TransformConfig) -> dict[str, Any]:
    transformed = dict(record)

    if config.trim_strings:
        transformed = trim_strings(transformed)

    for source_field, target_field in config.rename_fields.items():
        if source_field in transformed:
            transformed[target_field] = transformed.pop(source_field)

    for field, value in config.default_values.items():
        transformed.setdefault(field, value)

    for field, mode in config.normalize_case_fields.items():
        if field in transformed and isinstance(transformed[field], str):
            transformed[field] = normalize_case(transformed[field], mode)

    if config.redact_pii:
        transformed = redact_pii_from_record(transformed)

    return transformed


def trim_strings(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value.strip() if isinstance(value, str) else value for key, value in record.items()
    }


def normalize_case(value: str, mode: str) -> str:
    if mode == "lower":
        return value.lower()
    if mode == "upper":
        return value.upper()
    if mode == "title":
        return value.title()
    raise ValueError(f"Unsupported case normalization mode: {mode}")


def redact_pii_from_record(record: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in record.items():
        if isinstance(value, str):
            cleaned = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", value)
            cleaned = PHONE_PATTERN.sub("[REDACTED_PHONE]", cleaned)
            result[key] = cleaned
        else:
            result[key] = value
    return result
