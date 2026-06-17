# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

from nexus_observability.alerts import AlertRecorder, evaluate_ai_alerts, evaluate_metric_alerts
from nexus_observability.models import AiInteractionEvent, MetricEvent, Severity


def test_evaluate_metric_alerts_detects_high_latency(sample_config):
    metric = MetricEvent(service="svc", name="request_latency_ms", value=500)

    alerts = evaluate_metric_alerts(metric, sample_config.alerts)

    assert alerts[0].name == "high_latency"
    assert alerts[0].severity == Severity.WARN


def test_evaluate_metric_alerts_detects_error_rate(sample_config):
    metric = MetricEvent(service="svc", name="request_error_rate", value=0.9)

    alerts = evaluate_metric_alerts(metric, sample_config.alerts)

    assert alerts[0].name == "high_error_rate"
    assert alerts[0].severity == Severity.ERROR


def test_evaluate_ai_alerts_detects_low_confidence(sample_config):
    event = AiInteractionEvent(
        tenant="default",
        decision="allowed",
        confidence=0.1,
        citation_count=1,
        latency_ms=50,
    )

    alerts = evaluate_ai_alerts(event, sample_config.alerts)

    assert alerts[0].name == "low_ai_confidence"


def test_alert_recorder_writes_jsonl(sample_config, tmp_path):
    recorder = AlertRecorder(sample_config.storage, tmp_path)
    alert = evaluate_metric_alerts(
        MetricEvent(service="svc", name="request_latency_ms", value=500),
        sample_config.alerts,
    )[0]

    recorder.write(alert)

    assert recorder.read_all()[0]["name"] == "high_latency"

