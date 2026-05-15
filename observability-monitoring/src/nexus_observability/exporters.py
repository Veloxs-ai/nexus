from __future__ import annotations

import os

from nexus_observability.config import ExporterConfig, ObservabilityConfig

SUPPORTED_EXPORTERS = {"opentelemetry", "prometheus", "grafana", "datadog", "splunk", "cloudwatch"}


def validate_exporter(name: str, exporter: ExporterConfig) -> list[str]:
    issues: list[str] = []
    if exporter.type not in SUPPORTED_EXPORTERS:
        issues.append(f"{name}: unsupported exporter type {exporter.type}")
    if exporter.enabled and not exporter.endpoint:
        issues.append(f"{name}: enabled exporter requires endpoint")
    if exporter.enabled and exporter.api_key_env and not os.getenv(exporter.api_key_env):
        issues.append(f"{name}: missing API key environment variable {exporter.api_key_env}")
    return issues


def validate_exporters(config: ObservabilityConfig) -> list[str]:
    issues: list[str] = []
    for name, exporter in config.exporters.items():
        issues.extend(validate_exporter(name, exporter))
    return issues


def enabled_exporters(config: ObservabilityConfig) -> list[str]:
    return sorted(name for name, exporter in config.exporters.items() if exporter.enabled)

