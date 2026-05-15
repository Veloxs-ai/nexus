# Observability & Monitoring Layer

Enables real-time monitoring, logging, distributed tracing, and operational insight across data pipelines, system services, retrieval, guardrails, security, and engagement layers.

This layer provides a loosely coupled monitoring plane for:

- data pipeline health
- service reliability
- AI interaction behavior
- model and retrieval performance
- security and governance activity
- third-party observability integrations

## Capabilities

- **Metrics**: Captures counters, gauges, histograms, and service-level indicators.
- **Logging**: Writes structured JSONL logs with layer, service, tenant, severity, and correlation IDs.
- **Distributed Tracing**: Records spans with trace IDs, parent span IDs, durations, and attributes.
- **AI Interaction Monitoring**: Tracks prompts, decisions, confidence, citations, latency, and guardrail outcomes.
- **Alert Evaluation**: Applies configurable thresholds for latency, error rate, confidence, and denied access.
- **Third-Party Export Configuration**: Defines optional targets for OpenTelemetry, Prometheus, Grafana, Datadog, Splunk, and CloudWatch.

## Current Status

This project is runnable locally and includes:

- config-driven layer/service monitoring setup
- JSONL metric, log, trace, and AI interaction stores
- alert rule evaluation
- third-party exporter configuration validation
- CLI commands
- automated tests

The implementation uses local files for development. Production deployments can connect exporters to OpenTelemetry Collector, Prometheus, Grafana, Datadog, Splunk, CloudWatch, or another observability platform.

## Project Layout

```text
observability-monitoring/
  configs/
    observability.yaml
  data/
    logs/
      .gitkeep
    metrics/
      .gitkeep
    traces/
      .gitkeep
    ai/
      .gitkeep
    alerts/
      .gitkeep
  docs/
    architecture.md
  src/nexus_observability/
    alerts.py
    cli.py
    config.py
    exporters.py
    io.py
    logging.py
    metrics.py
    models.py
    service.py
    traces.py
  tests/
    conftest.py
    test_alerts.py
    test_cli.py
    test_config.py
    test_exporters.py
    test_logging.py
    test_metrics.py
    test_service.py
    test_traces.py
  pyproject.toml
```

## Prerequisites

Install:

- Python 3.11 or newer
- `pip`

Check Python:

```bash
python3 --version
```

## Setup

From the repository root:

```bash
cd path/to/nexus/observability-monitoring
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Confirm the CLI:

```bash
observability --help
```

Without package installation:

```bash
PYTHONPATH=src python -m nexus_observability.cli --help
```

## Configuration

Monitoring is configured in [configs/observability.yaml](configs/observability.yaml).

The config includes:

- loose references to every architecture layer
- local JSONL storage paths
- monitored services
- alert thresholds
- third-party exporter definitions

Example third-party exporter configuration:

```yaml
exporters:
  otel:
    enabled: true
    type: opentelemetry
    endpoint: http://localhost:4318
  prometheus:
    enabled: true
    type: prometheus
    endpoint: http://localhost:9090
  datadog:
    enabled: false
    type: datadog
    endpoint: https://api.datadoghq.com
    api_key_env: DATADOG_API_KEY
```

This project does not import code from other layers. Integration happens through config paths, structured event contracts, and optional exporter endpoints.

## Validate Config

```bash
observability validate-config configs/observability.yaml
```

Expected output:

```text
Loaded 7 monitored services and 6 exporters.
```

Without package installation:

```bash
PYTHONPATH=src python -m nexus_observability.cli validate-config configs/observability.yaml
```

## Record A Metric

```bash
observability record-metric configs/observability.yaml experience-api-engagement request_latency_ms 125 --kind histogram --tenant default
```

Metrics are written to:

```text
data/metrics/metrics.jsonl
```

## Write A Structured Log

```bash
observability log configs/observability.yaml orchestration-guardrails info "Guardrail decision allowed" --tenant default
```

Logs are written to:

```text
data/logs/logs.jsonl
```

## Record A Trace Span

```bash
observability trace configs/observability.yaml experience-api-engagement ask_request 42 --trace-id demo-trace
```

Traces are written to:

```text
data/traces/spans.jsonl
```

## Record AI Interaction

```bash
observability record-ai configs/observability.yaml default allowed 0.86 2 184
```

AI events are written to:

```text
data/ai/interactions.jsonl
```

## Evaluate Alerts

```bash
observability evaluate-alerts configs/observability.yaml
```

Triggered alerts are written to:

```text
data/alerts/alerts.jsonl
```

## Third-Party Tool Connections

The local project validates and documents third-party connection settings but does not push network data by default. This keeps local execution deterministic and testable.

Supported exporter types in config:

- `opentelemetry`
- `prometheus`
- `grafana`
- `datadog`
- `splunk`
- `cloudwatch`

Recommended production pattern:

1. Run this layer or equivalent instrumentation in each service.
2. Emit OpenTelemetry traces and metrics to an OpenTelemetry Collector.
3. Scrape or remote-write metrics to Prometheus.
4. Visualize in Grafana.
5. Send logs to Splunk, Datadog, CloudWatch Logs, or another SIEM/log platform.
6. Use alert rules from this config as the starting policy contract.

## Run Tests

Run all tests:

```bash
python -m pytest
```

Run one test file:

```bash
python -m pytest tests/test_service.py
```

Run with verbose output:

```bash
python -m pytest -v
```

Expected result:

```text
23 passed
```

## Integration Flow

The intended architecture flow is:

1. Each layer emits metrics, logs, traces, and AI interaction events.
2. `observability-monitoring` normalizes and stores events locally or forwards them through exporters.
3. Alert rules evaluate operational risk and service health.
4. Dashboards and third-party tools consume telemetry for performance, reliability, and incident response.

The projects remain loosely coupled through config and structured event contracts.

## Production Next Steps

1. Add OpenTelemetry SDK instrumentation helpers for each Python project.
2. Add exporter implementations that send to OTLP, Prometheus remote write, Datadog, Splunk HEC, and CloudWatch.
3. Add dashboard JSON templates for Grafana.
4. Add SLO burn-rate alerting.
5. Add tenant-specific monitoring views.
6. Add correlation across request IDs, trace IDs, audit event IDs, and AI interaction IDs.
