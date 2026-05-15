from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ChannelType(StrEnum):
    API = "api"
    SDK = "sdk"
    ASSISTANT = "assistant"
    WEB = "web"
    MOBILE = "mobile"


class AskRequest(BaseModel):
    query: str
    channel: str = "assistant"
    user_id: str | None = None
    session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Citation(BaseModel):
    source_id: str
    collection: str
    score: float


class AskResponse(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    decision: str
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    channel: str
    tenant_id: str
    session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AssistantSession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str | None = None
    channel: str = "assistant"
    greeting: str
    history: list[dict[str, str]] = Field(default_factory=list)

