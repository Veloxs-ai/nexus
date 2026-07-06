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

import argparse
from pathlib import Path

from nexus_observability.config import load_config
from nexus_observability.exporters import validate_exporters
from nexus_observability.models import MetricKind, Severity
from nexus_observability.service import ObservabilityService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="observability", description="Observability and monitoring control plane."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate_config = commands.add_parser("validate-config", help="Load and validate an observability config.")
    validate_config.add_argument("config_path", type=Path)

    record_metric = commands.add_parser("record-metric", help="Record a service metric.")
    record_metric.add_argument("config_path", type=Path)
    record_metric.add_argument("service")
    record_metric.add_argument("name")
    record_metric.add_argument("value", type=float)
    record_metric.add_argument("--kind", type=MetricKind, choices=list(MetricKind), default=MetricKind.GAUGE)
    record_metric.add_argument("--tenant", default=None)

    log = commands.add_parser("log", help="Write a structured log event.")
    log.add_argument("config_path", type=Path)
    log.add_argument("service")
    log.add_argument("severity", type=Severity, choices=list(Severity))
    log.add_argument("message")
    log.add_argument("--tenant", default=None)

    trace = commands.add_parser("trace", help="Record a trace span.")
    trace.add_argument("config_path", type=Path)
    trace.add_argument("service")
    trace.add_argument("operation")
    trace.add_argument("duration_ms", type=float)
    trace.add_argument("trace_id")

    record_ai = commands.add_parser("record-ai", help="Record an AI interaction event.")
    record_ai.add_argument("config_path", type=Path)
    record_ai.add_argument("tenant")
    record_ai.add_argument("decision")
    record_ai.add_argument("confidence", type=float)
    record_ai.add_argument("citation_count", type=int)
    record_ai.add_argument("latency_ms", type=float)

    evaluate_alerts = commands.add_parser("evaluate-alerts", help="Evaluate alert rules over recorded events.")
    evaluate_alerts.add_argument("config_path", type=Path)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config_path)

    if args.command == "validate-config":
        print(f"Loaded {len(config.services)} monitored services and {len(config.exporters)} exporters.")
        for issue in validate_exporters(config):
            print(f"exporter_issue: {issue}")
        return 0

    obs = ObservabilityService(config, args.config_path.parent.parent)
    if args.command == "record-metric":
        event = obs.record_metric(args.service, args.name, args.value, args.kind, args.tenant)
        print(f"metric_event_id: {event.event_id}")
    elif args.command == "log":
        event = obs.write_log(args.service, args.severity, args.message, args.tenant)
        print(f"log_event_id: {event.event_id}")
    elif args.command == "trace":
        span = obs.record_trace(args.service, args.operation, args.duration_ms, args.trace_id)
        print(f"span_id: {span.span_id}")
    elif args.command == "record-ai":
        event = obs.record_ai_interaction(
            args.tenant, args.decision, args.confidence, args.citation_count, args.latency_ms
        )
        print(f"ai_event_id: {event.event_id}")
    elif args.command == "evaluate-alerts":
        count = obs.evaluate_existing_alerts()
        print(f"alerts_written: {count}")
    return 0


def app() -> None:
    """Console-script entry point (kept for the `nexus_observability.cli:app` script target)."""
    raise SystemExit(main())


if __name__ == "__main__":
    raise SystemExit(main())
