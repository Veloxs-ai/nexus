from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class Decision(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"


class AccessRequest(BaseModel):
    role: str
    permission: str
    user_tenant: str
    resource_tenant: str
    data_scope: str | None = None
    subject_id: str | None = None


class AccessDecision(BaseModel):
    decision: Decision
    reason: str
    request: AccessRequest


class AuditEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str
    actor_id: str
    tenant_id: str
    decision: Decision
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TelemetryEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    service_name: str
    metric_name: str
    value: float
    attributes: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

