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

import os

from .config import ExporterConfig, ObservabilityConfig

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
