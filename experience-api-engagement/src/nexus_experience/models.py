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
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AssistantSession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str | None = None
    tenant_id: str | None = None
    channel: str = "assistant"
    greeting: str
    history: list[dict[str, str]] = Field(default_factory=list)
