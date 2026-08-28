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

from pathlib import Path

from .config import AlertConfig, StorageConfig
from .io import append_jsonl, read_jsonl
from .models import AiInteractionEvent, AlertEvent, MetricEvent, Severity


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
