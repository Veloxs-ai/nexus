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

