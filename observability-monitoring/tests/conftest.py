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

import pytest

from nexus_observability.config import ObservabilityConfig


@pytest.fixture
def sample_config() -> ObservabilityConfig:
    return ObservabilityConfig.model_validate(
        {
            "storage": {
                "metrics_uri": "metrics.jsonl",
                "logs_uri": "logs.jsonl",
                "traces_uri": "spans.jsonl",
                "ai_interactions_uri": "ai.jsonl",
                "alerts_uri": "alerts.jsonl",
            },
            "services": {
                "experience-api-engagement": {
                    "layer": "engagement",
                    "owner": "app",
                    "slo_latency_ms": 1000,
                    "slo_error_rate": 0.01,
                }
            },
            "alerts": {
                "latency_ms_threshold": 100,
                "error_rate_threshold": 0.05,
                "min_ai_confidence": 0.5,
            },
            "exporters": {
                "otel": {
                    "enabled": True,
                    "type": "opentelemetry",
                    "endpoint": "http://localhost:4318",
                },
                "datadog": {
                    "enabled": False,
                    "type": "datadog",
                    "endpoint": "https://api.datadoghq.com",
                    "api_key_env": "DATADOG_API_KEY",
                },
            },
        }
    )
