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
    enterprise_data_pipeline: str | None = None
    data_processing_enrichment: str | None = None
    embedding_retrieval_intelligence: str | None = None
    orchestration_guardrails: str | None = None
    experience_api_engagement: str | None = None
    security_governance: str | None = None


class StorageConfig(BaseModel):
    metrics_uri: str
    logs_uri: str
    traces_uri: str
    ai_interactions_uri: str
    alerts_uri: str


class ServiceConfig(BaseModel):
    layer: str
    owner: str
    slo_latency_ms: float
    slo_error_rate: float


class AlertConfig(BaseModel):
    latency_ms_threshold: float = 2000
    error_rate_threshold: float = 0.05
    min_ai_confidence: float = 0.3
    denied_access_threshold: int = 5


class ExporterConfig(BaseModel):
    enabled: bool = False
    type: str
    endpoint: str
    api_key_env: str | None = None


class ObservabilityConfig(BaseModel):
    integration: IntegrationConfig = Field(default_factory=IntegrationConfig)
    storage: StorageConfig
    services: dict[str, ServiceConfig]
    alerts: AlertConfig = Field(default_factory=AlertConfig)
    exporters: dict[str, ExporterConfig] = Field(default_factory=dict)


def _load_raw(path: Path):
    """Parse JSON (stdlib) natively; YAML only when PyYAML is installed (optional extra)."""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                f"{path} is YAML, but PyYAML is not installed. Use a JSON config "
                "or install the optional extra: pip install observability-monitoring[yaml]"
            ) from exc
        return yaml.safe_load(text)
    return json.loads(text)


def load_config(path: Path) -> ObservabilityConfig:
    return ObservabilityConfig.model_validate(_load_raw(path))

