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

from nexus_pipeline.config import SourceConfig
from nexus_pipeline.integrity import validate_records
from nexus_pipeline.models import CdcOperation, DataEvent


def normalize_debezium_event(message: dict[str, Any]) -> dict[str, Any]:
    payload = message.get("payload", message)
    op = payload.get("op")
    after = payload.get("after")
    before = payload.get("before")
    source = payload.get("source", {})

    operation = {
        "c": CdcOperation.INSERT,
        "r": CdcOperation.INSERT,
        "u": CdcOperation.UPDATE,
        "d": CdcOperation.DELETE,
    }.get(op)

    record = after if operation != CdcOperation.DELETE else before
    if not record:
        return {}

    record["source_ts_ms"] = payload.get("ts_ms") or source.get("ts_ms")
    record["_cdc_operation"] = operation
    return record


def run_cdc(source_name: str, source: SourceConfig, messages: list[dict[str, Any]] | None = None) -> list[DataEvent]:
    records = [normalize_debezium_event(message) for message in messages or []]
    result = validate_records(source_name, source, [record for record in records if record])
    for event in result.valid:
        operation = event.payload.get("_cdc_operation")
        event.operation = operation if isinstance(operation, CdcOperation) else None
    return result.valid

