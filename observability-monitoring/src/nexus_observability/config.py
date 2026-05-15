from __future__ import annotations

from pathlib import Path

import yaml
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


def load_config(path: Path) -> ObservabilityConfig:
    with path.open("r", encoding="utf-8") as config_file:
        raw = yaml.safe_load(config_file)
    return ObservabilityConfig.model_validate(raw)

