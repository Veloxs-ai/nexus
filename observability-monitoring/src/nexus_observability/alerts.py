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

from nexus_observability.config import AlertConfig, StorageConfig
from nexus_observability.io import append_jsonl, read_jsonl
from nexus_observability.models import AiInteractionEvent, AlertEvent, MetricEvent, Severity


def evaluate_metric_alerts(metric: MetricEvent, config: AlertConfig) -> list[AlertEvent]:
    alerts: list[AlertEvent] = []
    if metric.name.endswith("latency_ms") and metric.value > config.latency_ms_threshold:
        alerts.append(
            AlertEvent(
                name="high_latency",
                severity=Severity.WARN,
                message=f"{metric.service} latency exceeded threshold",
                source_event_id=metric.event_id,
                attributes={"value": metric.value, "threshold": config.latency_ms_threshold},
            )
        )
    if metric.name.endswith("error_rate") and metric.value > config.error_rate_threshold:
        alerts.append(
            AlertEvent(
                name="high_error_rate",
                severity=Severity.ERROR,
                message=f"{metric.service} error rate exceeded threshold",
                source_event_id=metric.event_id,
                attributes={"value": metric.value, "threshold": config.error_rate_threshold},
            )
        )
    return alerts


def evaluate_ai_alerts(event: AiInteractionEvent, config: AlertConfig) -> list[AlertEvent]:
    if event.confidence >= config.min_ai_confidence:
        return []
    return [
        AlertEvent(
            name="low_ai_confidence",
            severity=Severity.WARN,
            message="AI response confidence below threshold",
            source_event_id=event.event_id,
            attributes={"confidence": event.confidence, "threshold": config.min_ai_confidence},
        )
    ]


class AlertRecorder:
    def __init__(self, storage: StorageConfig, base_dir: Path) -> None:
        self.storage = storage
        self.base_dir = base_dir

    def write(self, alert: AlertEvent) -> None:
        append_jsonl(self.storage.alerts_uri, self.base_dir, alert)

    def read_all(self) -> list[dict]:
        return read_jsonl(self.storage.alerts_uri, self.base_dir)

