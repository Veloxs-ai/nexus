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

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class IngestionMode(StrEnum):
    API = "api"
    BATCH = "batch"
    STREAMING = "streaming"
    CDC = "cdc"


class CdcOperation(StrEnum):
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"


class DataEvent(BaseModel):
    source: str
    destination: str
    primary_key: str
    operation: CdcOperation | None = None
    event_time: datetime
    payload: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ValidationResult(BaseModel):
    valid: list[DataEvent] = Field(default_factory=list)
    invalid: list[tuple[dict[str, Any], str]] = Field(default_factory=list)
