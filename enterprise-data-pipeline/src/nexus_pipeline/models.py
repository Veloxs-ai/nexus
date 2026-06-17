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

from datetime import datetime, timezone
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
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ValidationResult(BaseModel):
    valid: list[DataEvent] = Field(default_factory=list)
    invalid: list[tuple[dict[str, Any], str]] = Field(default_factory=list)

