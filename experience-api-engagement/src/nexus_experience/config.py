from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from nexus_experience.models import ChannelType


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
    channels: dict[str, ChannelConfig]


def load_config(path: Path) -> EngagementConfig:
    with path.open("r", encoding="utf-8") as config_file:
        raw = yaml.safe_load(config_file)
    return EngagementConfig.model_validate(raw)
