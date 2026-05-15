from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from nexus_observability.config import load_config
from nexus_observability.exporters import validate_exporters
from nexus_observability.models import MetricKind, Severity
from nexus_observability.service import ObservabilityService

app = typer.Typer(help="Observability and monitoring control plane.")


@app.command()
def validate_config(config_path: Path) -> None:
    config = load_config(config_path)
    typer.echo(f"Loaded {len(config.services)} monitored services and {len(config.exporters)} exporters.")
    issues = validate_exporters(config)
    for issue in issues:
        typer.echo(f"exporter_issue: {issue}")


@app.command()
def record_metric(
    config_path: Path,
    service: str,
    name: str,
    value: float,
    kind: MetricKind = MetricKind.GAUGE,
    tenant: Optional[str] = None,
) -> None:
    config = load_config(config_path)
    obs = ObservabilityService(config, config_path.parent.parent)
    event = obs.record_metric(service, name, value, kind, tenant)
    typer.echo(f"metric_event_id: {event.event_id}")


@app.command()
def log(
    config_path: Path,
    service: str,
    severity: Severity,
    message: str,
    tenant: Optional[str] = None,
) -> None:
    config = load_config(config_path)
    obs = ObservabilityService(config, config_path.parent.parent)
    event = obs.write_log(service, severity, message, tenant)
    typer.echo(f"log_event_id: {event.event_id}")


@app.command()
def trace(config_path: Path, service: str, operation: str, duration_ms: float, trace_id: str) -> None:
    config = load_config(config_path)
    obs = ObservabilityService(config, config_path.parent.parent)
    span = obs.record_trace(service, operation, duration_ms, trace_id)
    typer.echo(f"span_id: {span.span_id}")


@app.command()
def record_ai(
    config_path: Path,
    tenant: str,
    decision: str,
    confidence: float,
    citation_count: int,
    latency_ms: float,
) -> None:
    config = load_config(config_path)
    obs = ObservabilityService(config, config_path.parent.parent)
    event = obs.record_ai_interaction(tenant, decision, confidence, citation_count, latency_ms)
    typer.echo(f"ai_event_id: {event.event_id}")


@app.command()
def evaluate_alerts(config_path: Path) -> None:
    config = load_config(config_path)
    obs = ObservabilityService(config, config_path.parent.parent)
    count = obs.evaluate_existing_alerts()
    typer.echo(f"alerts_written: {count}")


if __name__ == "__main__":
    app()

