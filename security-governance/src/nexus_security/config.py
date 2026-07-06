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

from pathlib import Path

import json
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

