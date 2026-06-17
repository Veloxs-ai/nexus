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

