# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

from __future__ import annotations

from typing import Any

from nexus_processing.config import TransformConfig


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

    return transformed


def trim_strings(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value.strip() if isinstance(value, str) else value for key, value in record.items()}


def normalize_case(value: str, mode: str) -> str:
    if mode == "lower":
        return value.lower()
    if mode == "upper":
        return value.upper()
    if mode == "title":
        return value.title()
    raise ValueError(f"Unsupported case normalization mode: {mode}")

