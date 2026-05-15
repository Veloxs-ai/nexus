from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class IntegrationConfig(BaseModel):
    experience_project: str | None = None
    guardrails_project: str | None = None
    retrieval_project: str | None = None
    processing_project: str | None = None
    ingestion_project: str | None = None


class TenantConfig(BaseModel):
    name: str
    data_scopes: list[str] = Field(default_factory=list)


class RoleConfig(BaseModel):
    permissions: list[str] = Field(default_factory=list)
    data_scopes: list[str] = Field(default_factory=list)


class EncryptionConfig(BaseModel):
    enabled: bool = True
    key_id: str = "local-dev-key"
    key_material_env: str = "NEXUS_SECURITY_KEY"
    require_tls: bool = True
    allowed_tls_versions: list[str] = Field(default_factory=lambda: ["TLSv1.2", "TLSv1.3"])


class AuditConfig(BaseModel):
    enabled: bool = True
    output_uri: str = "data/audit/audit.jsonl"
    include_denied_events: bool = True


class ObservabilityConfig(BaseModel):
    enabled: bool = True
    output_uri: str = "data/telemetry/events.jsonl"
    service_name: str = "nexus-security-governance"


class SecurityConfig(BaseModel):
    integration: IntegrationConfig = Field(default_factory=IntegrationConfig)
    tenants: dict[str, TenantConfig]
    roles: dict[str, RoleConfig]
    encryption: EncryptionConfig = Field(default_factory=EncryptionConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)


def load_config(path: Path) -> SecurityConfig:
    with path.open("r", encoding="utf-8") as config_file:
        raw = yaml.safe_load(config_file)
    return SecurityConfig.model_validate(raw)

