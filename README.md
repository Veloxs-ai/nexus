# Nexus Enterprise AI Platform

Nexus is a layered enterprise AI platform that transforms fragmented enterprise data into actionable, secure, and context-aware insights.

It provides one external-facing library and CLI while keeping each architecture layer independently deployable and loosely coupled.

## Layers

- `enterprise-data-pipeline`: ingestion from APIs, batch, streaming, and CDC sources
- `data-processing-enrichment`: ETL/ELT, document chunking, and metadata enrichment
- `embedding-retrieval-intelligence`: vector search, graph context, hybrid retrieval, and ranking
- `orchestration-guardrails`: prompt safety, policy enforcement, PII masking, and grounded RAG
- `experience-api-engagement`: REST/API, SDK, assistant, web, and mobile engagement
- `security-governance`: RBAC, tenant isolation, encryption, and audit logging
- `observability-monitoring`: metrics, logs, traces, AI events, alerts, and third-party observability configuration

## Single Entry Point

Install the root library:

```bash
cd path/to/nexus
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Validate the complete platform contract:

```bash
nexus validate-platform configs/nexus.yaml
```

List layers:

```bash
nexus layers configs/nexus.yaml
```

Rebuild local demo outputs and retrieval indexes:

```bash
nexus prepare-demo configs/nexus.yaml
```

Ask through the full engagement and guardrails path:

```bash
nexus ask configs/nexus.yaml "What does the security policy say about MFA?"
```

Without package installation:

```bash
PYTHONPATH=src python -m nexus.cli validate-platform configs/nexus.yaml
```

## Configuration

The root platform contract is [configs/nexus.yaml](configs/nexus.yaml). It maps each layer to:

- project path
- CLI module
- layer config path
- layer responsibility
- enterprise insight flow order

The root `nexus` package does not import child layer code. It invokes layer CLIs through configured paths and `PYTHONPATH`, so each layer can be packaged, deployed, and scaled independently.

## Run All Tests

Run the root tests:

```bash
python -m pytest
```

Run layer tests from each project folder:

```bash
cd enterprise-data-pipeline && python -m pytest
cd ../data-processing-enrichment && python -m pytest
cd ../embedding-retrieval-intelligence && python -m pytest
cd ../orchestration-guardrails && python -m pytest
cd ../experience-api-engagement && python -m pytest
cd ../security-governance && python -m pytest
cd ../observability-monitoring && python -m pytest
```

## Enterprise Integration Pattern

External enterprise projects should integrate through one of these stable entry points:

- Python: `from nexus import NexusPlatform`
- CLI: `nexus ...`
- Layer CLIs for operational ownership boundaries
- Layer configs for environment-specific deployment

This keeps the platform open, portable, and usable across onshore, offshore, hybrid, and cloud enterprise delivery models.
