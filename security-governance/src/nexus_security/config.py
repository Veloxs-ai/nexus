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
    tenant_id: str = "default"
    secret_key: str | None = None
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


def _load_raw(path: Path):
    """Parse JSON (stdlib) natively; YAML only when PyYAML is installed (optional extra)."""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                f"{path} is YAML, but PyYAML is not installed. Use a JSON config "
                "or install the optional extra: pip install security-governance[yaml]"
            ) from exc
        return yaml.safe_load(text)
    return json.loads(text)


def load_config(path: Path) -> SecurityConfig:
    return SecurityConfig.model_validate(_load_raw(path))
