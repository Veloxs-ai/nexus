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
from uuid import uuid4

from pydantic import BaseModel, Field


class MetricKind(StrEnum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"


class Severity(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"
    CRITICAL = "critical"


class MetricEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    service: str
    name: str
    value: float
    kind: MetricKind = MetricKind.GAUGE
    tenant: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LogEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    service: str
    severity: Severity
    message: str
    tenant: str | None = None
    trace_id: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TraceSpan(BaseModel):
    span_id: str = Field(default_factory=lambda: str(uuid4()))
    trace_id: str
    service: str
    operation: str
    duration_ms: float
    parent_span_id: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AiInteractionEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    tenant: str
    decision: str
    confidence: float
    citation_count: int
    latency_ms: float
    attributes: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AlertEvent(BaseModel):
    alert_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    severity: Severity
    message: str
    source_event_id: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

