# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

from nexus_observability.models import MetricKind, Severity
from nexus_observability.service import ObservabilityService


def test_service_records_metric_and_alert(sample_config, tmp_path):
    service = ObservabilityService(sample_config, tmp_path)

    event = service.record_metric(
        "experience-api-engagement",
        "request_latency_ms",
        250,
        MetricKind.HISTOGRAM,
    )

    assert event.value == 250
    assert service.alerts.read_all()[0]["name"] == "high_latency"


def test_service_writes_log(sample_config, tmp_path):
    service = ObservabilityService(sample_config, tmp_path)

    event = service.write_log("svc", Severity.INFO, "hello")

    assert event.message == "hello"
    assert service.logs.read_all()[0]["message"] == "hello"


def test_service_records_trace_and_latency_metric(sample_config, tmp_path):
    service = ObservabilityService(sample_config, tmp_path)

    span = service.record_trace("svc", "ask", 20, "trace-1")

    assert span.trace_id == "trace-1"
    assert service.metrics.read_all()[0]["name"] == "ask_latency_ms"


def test_service_records_ai_interaction_and_alert(sample_config, tmp_path):
    service = ObservabilityService(sample_config, tmp_path)

    event = service.record_ai_interaction("default", "allowed", 0.2, 1, 100)

    assert event.confidence == 0.2
    assert service.alerts.read_all()[0]["name"] == "low_ai_confidence"


def test_service_evaluates_existing_alerts(sample_config, tmp_path):
    service = ObservabilityService(sample_config, tmp_path)
    service.metrics.record("svc", "request_latency_ms", 250, MetricKind.HISTOGRAM)

    count = service.evaluate_existing_alerts()

    assert count == 1
    assert service.alerts.read_all()[0]["name"] == "high_latency"

