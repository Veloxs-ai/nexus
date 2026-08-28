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

import json
from pathlib import Path

from pydantic import BaseModel, Field

from .models import ChannelType


class TenantConfig(BaseModel):
    id: str = "default"
    display_name: str = "Default Tenant"


class IntegrationConfig(BaseModel):
    mode: str = "mock"
    guardrails_project: str | None = None
    guardrails_config: str | None = None
    python_executable: str | None = None


class ApiConfig(BaseModel):
    title: str = "Experience API"
    version: str = "0.1.0"
    default_channel: str = "assistant"


class AssistantConfig(BaseModel):
    default_assistant_id: str = "enterprise-copilot"
    max_history_messages: int = 8
    greeting: str = "How can I help?"


class ChannelConfig(BaseModel):
    type: ChannelType
    enabled: bool = True
    description: str = ""
    allowed_capabilities: list[str] = Field(default_factory=list)


def _default_channels() -> dict[str, ChannelConfig]:
    return {
        "api": ChannelConfig(type=ChannelType.API, enabled=True, allowed_capabilities=["ask"]),
        "sdk": ChannelConfig(type=ChannelType.SDK, enabled=True, allowed_capabilities=["ask"]),
        "assistant": ChannelConfig(
            type=ChannelType.ASSISTANT, enabled=True, allowed_capabilities=["ask", "session"]
        ),
        "web": ChannelConfig(type=ChannelType.WEB, enabled=True, allowed_capabilities=["ask"]),
    }


class ApiKeyEntry(BaseModel):
    secret: str
    user_id: str
    tenant_id: str
    role: str = "anonymous"
    permissions: list[str] = Field(default_factory=list)


class AuthConfig(BaseModel):
    enabled: bool = False
    header_name: str = "X-API-Key"
    api_keys: list[ApiKeyEntry] = Field(default_factory=list)
    max_query_chars: int = 8000


class EngagementConfig(BaseModel):
    tenant: TenantConfig = Field(default_factory=TenantConfig)
    integration: IntegrationConfig = Field(default_factory=IntegrationConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    assistant: AssistantConfig = Field(default_factory=AssistantConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    channels: dict[str, ChannelConfig] = Field(default_factory=_default_channels)


def _load_raw(path: Path):
    """Parse JSON (stdlib) natively; YAML only when PyYAML is installed (optional extra)."""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                f"{path} is YAML, but PyYAML is not installed. Use a JSON config "
                "or install the optional extra: pip install experience-api-engagement[yaml]"
            ) from exc
        return yaml.safe_load(text)
    return json.loads(text)


def load_config(path: Path) -> EngagementConfig:
    return EngagementConfig.model_validate(_load_raw(path))
