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


class JobMode(StrEnum):
    RECORDS = "records"
    DOCUMENTS = "documents"


class ProcessedRecord(BaseModel):
    record_id: str
    source_job: str
    payload: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)
    processed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DocumentChunk(BaseModel):
    chunk_id: str
    document_id: str
    source_job: str
    chunk_index: int
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    processed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

