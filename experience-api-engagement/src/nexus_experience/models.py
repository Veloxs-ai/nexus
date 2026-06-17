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


class ChannelType(StrEnum):
    API = "api"
    SDK = "sdk"
    ASSISTANT = "assistant"
    WEB = "web"
    MOBILE = "mobile"


class AskRequest(BaseModel):
    query: str
    channel: str = "assistant"
    session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Principal(BaseModel):
    user_id: str
    tenant_id: str
    role: str = "anonymous"
    permissions: list[str] = Field(default_factory=list)


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
    tenant_id: str | None = None
    channel: str = "assistant"
    greeting: str
    history: list[dict[str, str]] = Field(default_factory=list)

