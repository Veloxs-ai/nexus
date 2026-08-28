# Experience API & Engagement Layer

> Part of **[Nexus — Enterprise Intelligence Framework](../README.md)**, the open-source framework for secure, governed AI applications.
> This layer provides the **AI Orchestration** capability.


Serves as the engagement layer for enterprise AI services, enabling systems and users to onboard, access, and interact through APIs, SDKs, assistants, dashboards, and applications.

This layer provides standardized interfaces so intelligent services can be consumed consistently across channels while remaining loosely coupled to orchestration, retrieval, enrichment, and ingestion layers.

## Capabilities

- **REST APIs / GraphQL**: Developer-friendly interfaces for integrating AI services into enterprise applications.
- **SDKs**: Pre-built client utilities for faster integration and customization.
- **AI Assistants**: Conversational session management for chatbots, copilots, and voice-agent front ends.
- **Web & Mobile Applications**: Channel configuration for personalized, context-aware experiences.

## Current Status

This project is runnable locally and includes:

- config-driven channel and tenant setup
- assistant session orchestration
- API request/response models
- SDK-style Python client
- optional FastAPI app entry point
- GraphQL-style schema document
- downstream adapter contract for the guardrails layer
- deterministic local mock service for tests and demos
- automated tests

The implementation is intentionally loosely coupled. It does not import code from upstream layers. It can call the `orchestration-guardrails` layer through a CLI contract or use a mock/local backend for development.

## Project Layout

```text
experience-api-engagement/
  configs/
    engagement.json
  docs/
    architecture.md
    graphql-schema.graphql
  src/nexus_experience/
    api.py
    assistant.py
    channels.py
    cli.py
    config.py
    gateway.py
    models.py
    sdk.py
    service.py
  tests/
    conftest.py
    test_api.py
    test_assistant.py
    test_channels.py
    test_cli.py
    test_config.py
    test_gateway.py
    test_sdk.py
    test_service.py
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
cd path/to/nexus/experience-api-engagement
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Confirm the CLI:

```bash
experience --help
```

Without package installation:

```bash
PYTHONPATH=src python -m nexus_experience.cli --help
```

## Configuration

The engagement layer is configured in [configs/engagement.json](configs/engagement.json).

The config includes:

- tenant defaults
- channel definitions for web, mobile, assistant, REST, GraphQL, and SDK
- downstream guardrails integration
- assistant defaults
- API settings

Example:

```json
{
  "integration": {
    "guardrails_project": "../orchestration-guardrails",
    "guardrails_config": "../orchestration-guardrails/configs/guardrails.json",
    "mode": "subprocess_cli"
  }
}
```

For local tests or demos, set:

```json
{
  "integration": {
    "mode": "mock"
  }
}
```

## Validate Config

```bash
experience validate-config configs/engagement.json
```

Expected output:

```text
Loaded 6 channels for tenant default.
```

Without package installation:

```bash
PYTHONPATH=src python -m nexus_experience.cli validate-config configs/engagement.json
```

## Ask Through The Engagement Layer

```bash
experience ask configs/engagement.json "What does the security policy say about MFA?" --channel assistant
```

Without package installation:

```bash
PYTHONPATH=src python -m nexus_experience.cli ask configs/engagement.json "What does the security policy say about MFA?" --channel assistant
```

The default config uses the guardrails CLI integration, so make sure the guardrails layer and retrieval indexes are available:

```bash
cd path/to/nexus/embedding-retrieval-intelligence
PYTHONPATH=src python -m nexus_retrieval.cli build-index configs/retrieval.json
```

## Start REST API

Install runtime dependencies first:

```bash
python -m pip install -e ".[api]"
```

Start the API:

```bash
uvicorn nexus_experience.api:create_app --factory --host 0.0.0.0 --port 8080
```

Health check:

```bash
curl http://localhost:8080/health
```

Ask endpoint:

```bash
curl -X POST http://localhost:8080/v1/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"What does the security policy say about MFA?","channel":"assistant","user_id":"u001"}'
```

## GraphQL Contract

A GraphQL-style contract is provided at [docs/graphql-schema.graphql](docs/graphql-schema.graphql).

This project does not run a GraphQL server by default. The schema documents the stable contract for teams that want to expose the same engagement service through GraphQL.

## SDK Usage

```python
from pathlib import Path

from nexus_experience.config import load_config
from nexus_experience.gateway import MockGuardrailsGateway
from nexus_experience.sdk import ExperienceClient
from nexus_experience.service import ExperienceService

config = load_config(Path("configs/engagement.json"))
service = ExperienceService(config, MockGuardrailsGateway())
client = ExperienceClient(service)

response = client.ask("What does the security policy say about MFA?", channel="assistant")
print(response.answer)
```

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
20 passed
```

## Integration Flow

The intended architecture flow is:

1. Users and applications call `experience-api-engagement`.
2. The engagement layer normalizes requests by channel and tenant.
3. The request is sent to `orchestration-guardrails`.
4. Guardrails performs policy, privacy, RAG, and verification.
5. The engagement layer returns a consistent response to REST, GraphQL, SDK, assistant, web, or mobile consumers.

The projects remain loosely coupled:

- no shared runtime imports across layers
- integration through config paths and API/CLI contracts
- each layer can deploy and scale independently

## Production Next Steps

1. Add authentication and authorization middleware.
2. Add tenant-aware rate limits and quotas.
3. Add a real GraphQL server adapter.
4. Add web dashboard and mobile API facades.
5. Add streaming assistant responses.
6. Add conversation persistence in Postgres, Redis, or platform storage.
7. Add OpenAPI publishing and SDK generation.
