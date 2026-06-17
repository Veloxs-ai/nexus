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

from nexus_observability.alerts import AlertRecorder, evaluate_ai_alerts, evaluate_metric_alerts
from nexus_observability.config import ObservabilityConfig
from nexus_observability.io import append_jsonl, read_jsonl
from nexus_observability.logging import StructuredLogger
from nexus_observability.metrics import MetricRecorder
from nexus_observability.models import AiInteractionEvent, MetricEvent, MetricKind, Severity
from nexus_observability.traces import TraceRecorder


class ObservabilityService:
    def __init__(self, config: ObservabilityConfig, base_dir: Path) -> None:
        self.config = config
        self.base_dir = base_dir
        self.metrics = MetricRecorder(config.storage, base_dir)
        self.logs = StructuredLogger(config.storage, base_dir)
        self.traces = TraceRecorder(config.storage, base_dir)
        self.alerts = AlertRecorder(config.storage, base_dir)

    def record_metric(
        self,
        service: str,
        name: str,
        value: float,
        kind: MetricKind = MetricKind.GAUGE,
        tenant: str | None = None,
    ) -> MetricEvent:
        event = self.metrics.record(service, name, value, kind, tenant)
        for alert in evaluate_metric_alerts(event, self.config.alerts):
            self.alerts.write(alert)
        return event

    def write_log(
        self,
        service: str,
        severity: Severity,
        message: str,
        tenant: str | None = None,
    ):
        return self.logs.write(service, severity, message, tenant)

    def record_trace(self, service: str, operation: str, duration_ms: float, trace_id: str):
        metric = self.record_metric(service, f"{operation}_latency_ms", duration_ms, MetricKind.HISTOGRAM)
        return self.traces.record(
            service,
            operation,
            duration_ms,
            trace_id,
            attributes={"metric_event_id": metric.event_id},
        )

    def record_ai_interaction(
        self,
        tenant: str,
        decision: str,
        confidence: float,
        citation_count: int,
        latency_ms: float,
    ) -> AiInteractionEvent:
        event = AiInteractionEvent(
            tenant=tenant,
            decision=decision,
            confidence=confidence,
            citation_count=citation_count,
            latency_ms=latency_ms,
        )
        append_jsonl(self.config.storage.ai_interactions_uri, self.base_dir, event)
        for alert in evaluate_ai_alerts(event, self.config.alerts):
            self.alerts.write(alert)
        return event

    def evaluate_existing_alerts(self) -> int:
        count = 0
        for raw_metric in read_jsonl(self.config.storage.metrics_uri, self.base_dir):
            for alert in evaluate_metric_alerts(MetricEvent.model_validate(raw_metric), self.config.alerts):
                self.alerts.write(alert)
                count += 1
        for raw_event in read_jsonl(self.config.storage.ai_interactions_uri, self.base_dir):
            for alert in evaluate_ai_alerts(AiInteractionEvent.model_validate(raw_event), self.config.alerts):
                self.alerts.write(alert)
                count += 1
        return count

