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

from typing import Any

from .config import SourceConfig
from .integrity import validate_records
from .models import CdcOperation, DataEvent


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


def run_cdc(
    source_name: str, source: SourceConfig, messages: list[dict[str, Any]] | None = None
) -> list[DataEvent]:
    records = [normalize_debezium_event(message) for message in messages or []]
    result = validate_records(source_name, source, [record for record in records if record])
    for event in result.valid:
        operation = event.payload.get("_cdc_operation")
        event.operation = operation if isinstance(operation, CdcOperation) else None
    return result.valid
