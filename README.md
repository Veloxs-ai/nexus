# Nexus — Enterprise Intelligence Framework

[![CI](https://github.com/Veloxs-ai/nexus/actions/workflows/ci.yml/badge.svg)](https://github.com/Veloxs-ai/nexus/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/badge/pypi-veloxs--nexus-blue.svg)](https://pypi.org/project/veloxs-nexus/)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://pypi.org/project/veloxs-nexus/)
[![License](https://img.shields.io/badge/license-Apache--2.0-green.svg)](LICENSE)

**Nexus is an open-source enterprise intelligence framework for building secure, governed AI applications, retrieval systems, agents, and intelligent workflows.**

It sits *upstream and around* large language models: turning fragmented enterprise data into normalized vectors, contextual knowledge graphs, and grounded, policy-checked answers — without locking you into a particular model provider, vector database, or runtime.

```
Data Connectivity → Processing & Enrichment → Knowledge & Retrieval → Intelligent RAG
                                     → AI Orchestration → Governance → Observability
```

---

## Contents

- [What Nexus gives you](#what-nexus-gives-you)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Build a RAG workflow](#build-a-rag-workflow)
- [Architecture](#architecture)
- [Configuration](#configuration)
- [Running tests](#running-tests)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

---

## What Nexus gives you

Nexus provides seven composable capabilities. Each is an independently installable package that talks to the others through typed configs, JSONL contracts, CLI, and HTTP — **never by importing another layer's code**. That is what makes any layer swappable for your own systems.

| Capability | Package | What it does |
|---|---|---|
| **Data Connectivity** | `nexus.pipeline` | REST connectors with pagination and SSRF defense, batch file drops, streaming events, CDC (Debezium format) |
| **Processing & Enrichment** | `nexus.processing` | Format-aware chunking for CSV, JSON, Markdown and text; metadata extraction; FF1 format-preserving tokenization for sensitive fields |
| **Knowledge & Retrieval** | `nexus.retrieval` | Vector, lexical (BM25-style), hybrid RRF, and knowledge-graph retrieval with pluggable stores |
| **Intelligent RAG** | `nexus.guardrails` | Grounded answers with citations, PII masking, prompt-injection defense, fail-closed policy checks |
| **AI Orchestration** | `nexus.experience` | REST API, SDK, CLI, assistant sessions, channel adapters, API-key auth |
| **Governance** | `nexus.security` | RBAC, multi-tenant isolation, authenticated encryption, immutable audit log |
| **Observability** | `nexus.observability` | Metrics, structured logs, distributed trace spans, AI interaction events, alerting |

**Design properties worth knowing about:**

- **Runs offline.** The default embedding provider is a local hashing projection — no model downloads, no API calls, no network egress. Good for air-gapped evaluation and deterministic tests.
- **Thread-safe and serverless-friendly.** In-memory stores are guarded by `threading.Lock`; `in_memory_only=True` (the default) skips disk I/O entirely.
- **Typed configuration end to end.** Every layer's config is a Pydantic model, so a control plane can introspect the schema and render forms automatically.
- **Multi-tenant by construction.** Encryption and tokenization derive a tenant-bound salt (`HKDF-SHA256`), so two tenants processing identical data produce cryptographically distinct ciphertext.

> **On the embedding provider:** the built-in projection is a deterministic multi-gram hashing embedder, not a trained semantic model. It is excellent for reproducible local development, lexical-adjacent matching, and offline demos. For production semantic search, plug in your own embedding provider — the interface is designed for it. See [docs/USING_NEXUS.md](docs/USING_NEXUS.md).

---

## Installation

Requires **Python 3.11 or 3.12**.

```bash
pip install veloxs-nexus
```

Optional extras:

```bash
pip install "veloxs-nexus[postgres]"   # pgvector + SQLAlchemy persistence
pip install "veloxs-nexus[yaml]"       # YAML configuration files
```

To work on Nexus itself, see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Quick start

Process a document through the full pipeline and inspect the execution trace:

```python
import nexus

client = nexus.NexusClient(tenant_id="org-finance", in_memory_only=True)

csv_data = """employee_id,department,salary_usd,contact_email
101,Engineering,145000,john.doe@example.com
102,Security,160000,jane.smith@example.com"""

doc = client.process_document(
    document_id="doc-ledger-01",
    name="salaries.csv",
    text=csv_data,
    file_type="csv",
    enable_guardrails=True,
)

print(f"{doc.name}: {len(doc.chunks)} chunks")
print(doc.chunks[0].text)
# [Row ID: 1] employee_id: 101 | department: Engineering | salary_usd: 145000 | contact_email: [EMAIL]

for step in doc.execution_trace:
    print(f"[{step.step_number}/5] {step.stage_name} ({step.duration_ms}ms)")
```

Each chunk carries a 3072-dimensional embedding normalized to exact L2 unit length:

```python
import math

vector = doc.chunks[0].embedding
print(len(vector), round(math.sqrt(sum(v * v for v in vector)), 6))
# 3072 1.0
```

### Raw fidelity mode

When you need verbatim text — audit logs, code, account identifiers — bypass redaction:

```python
raw = client.process_document(
    document_id="doc-audit-02",
    name="audit.txt",
    text="Transaction 9842 authorized by admin@example.com",
    file_type="txt",
    enable_guardrails=False,
)
print(raw.chunks[0].text)  # preserved verbatim
```

---

## Build a RAG workflow

Index documents and ask grounded questions. Answers are checked against retrieved context and refused when they cannot be grounded:

```python
import nexus

client = nexus.NexusClient(in_memory_only=True)

doc = client.process_document(
    document_id="arch-01",
    name="architecture.md",
    text=(
        "# Infrastructure\n"
        "All database connections require TLS 1.3 encryption "
        "and mutual certificate authentication."
    ),
    file_type="md",
)
client.index_document(doc)

response = client.ask("What encryption is required for database connections?")
print(response.decision)  # allowed
print(response.answer)  # grounded in the indexed chunk
```

### Using layers individually

Every capability works standalone:

```python
# Vector projection
from nexus.retrieval.engine import RetrievalEngine

vector = RetrievalEngine().embed("Enterprise cloud infrastructure")

# PII masking
from nexus.guardrails.pii import mask_pii
from nexus.guardrails.config import PiiConfig

clean = mask_pii("Contact user@example.com", PiiConfig())

# Tenant-bound encryption
from nexus.security.encryption import encrypt_text, decrypt_text
from nexus.security.config import EncryptionConfig

cfg = EncryptionConfig(secret_key="replace-me", tenant_id="org-acme")
plain = decrypt_text(encrypt_text("Confidential Record", cfg), cfg)

# Format-aware chunking
from nexus.processing.engine import ProcessingEngine

chunks = ProcessingEngine().chunk_document("id,val\n1,Alpha\n2,Beta", file_type="csv")

# Batch ingestion
from nexus.pipeline.batch import run_batch
```

### Command line

Every command takes the path to a platform config:

```bash
nexus validate-config configs/nexus.json    # load and validate the config
nexus layers configs/nexus.json             # list configured layers
nexus validate-platform configs/nexus.json  # check every layer is ready
nexus ask configs/nexus.json "What is the MFA policy?" --channel assistant
```

---

## Architecture

```
                        ┌──────────────────────────────┐
   your application ──▶ │  nexus.experience            │  REST · SDK · CLI · channels
                        └──────────────┬───────────────┘
                                       │
                        ┌──────────────▼───────────────┐
                        │  nexus.guardrails            │  grounded RAG · PII · policy
                        └──────────────┬───────────────┘
                                       │
                        ┌──────────────▼───────────────┐
                        │  nexus.retrieval             │  vector · lexical · hybrid · graph
                        └──────────────┬───────────────┘
                                       │
                        ┌──────────────▼───────────────┐
                        │  nexus.processing            │  chunking · enrichment · tokenization
                        └──────────────┬───────────────┘
                                       │
                        ┌──────────────▼───────────────┐
                        │  nexus.pipeline              │  REST · batch · streaming · CDC
                        └──────────────────────────────┘

   cross-cutting:  nexus.security (RBAC · tenancy · encryption · audit)
                   nexus.observability (metrics · logs · traces · alerts)
```

Layers integrate only through configs, JSONL contracts, CLI, and HTTP. Replacing `nexus.retrieval` with your own vector database, or `nexus.guardrails` with your own policy engine, requires no changes to the layers around it.

Full detail: [docs/ARCHITECTURE_OVERVIEW.md](docs/ARCHITECTURE_OVERVIEW.md) · [docs/USING_NEXUS.md](docs/USING_NEXUS.md)

### PostgreSQL + pgvector

For durable persistence, `nexus.database` ships a reference schema:

```python
from nexus.database import PGVECTOR_DDL_SCHEMA

print(PGVECTOR_DDL_SCHEMA)
```

> **Index dimension limit.** pgvector's HNSW and IVFFlat indexes support up to 2000 dimensions for the `vector` type, below the 3072 Nexus emits by default. For an indexed column, either reduce `embedding.dimensions` to 2000 or below, or use `halfvec` with pgvector 0.7+. Without an index, 3072-dimension columns still store and scan correctly.

---

## Configuration

Every layer reads a JSON (or, with the `[yaml]` extra, YAML) config validated by a Pydantic model. The root config at [`configs/nexus.json`](configs/nexus.json) wires the layers together.

```bash
nexus validate-config configs/nexus.json
```

Because configs are typed models, you can introspect any layer's schema programmatically:

```python
from nexus.retrieval.config import RetrievalConfig

print(RetrievalConfig.model_json_schema())
```

Secrets are never read implicitly from the environment by library code. Pass them explicitly, or use the documented `env:VAR_NAME` indirection. See [SECURITY.md](SECURITY.md).

---

## Running tests

The suite is deterministic and fully offline — no network, no cloud services, no model downloads.

```bash
git clone https://github.com/Veloxs-ai/nexus.git
cd nexus
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest -q
```

Each layer has its own suite:

```bash
for layer in enterprise-data-pipeline data-processing-enrichment \
             embedding-retrieval-intelligence orchestration-guardrails \
             experience-api-engagement security-governance \
             observability-monitoring; do
  (cd "$layer" && python -m pip install -e ".[dev]" -q && python -m pytest -q)
done
```

Lint and format with [Ruff](https://docs.astral.sh/ruff/):

```bash
ruff check .
ruff format --check .
```

---

## Documentation

| Guide | What it covers |
|---|---|
| [Integrator Guide](docs/USING_NEXUS.md) | The comprehensive reference — every layer in detail, the security model, extension points, and what is production-grade today. **Start here after the quick start.** |
| [Architecture Overview](docs/ARCHITECTURE_OVERVIEW.md) | Design principles, the loose-coupling rule, and per-layer capabilities |
| [Integration Guide](docs/INTEGRATION_GUIDE.md) | Installation, library vs. CLI integration patterns, environment variables |
| [Processing Reference](docs/PROCESSING_REFERENCE.md) | Ingestion formats, the five processing phases, output structure, database setup |
| [Processing & Embedding Spec](docs/PROCESSING_AND_EMBEDDING_SPEC.md) | Chunking rules and the 3072-dimension vector projection, specified precisely |

---

## Contributing

Contributions are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md) for the development setup, project conventions, and pull-request process.

- 🐛 [Report a bug](https://github.com/Veloxs-ai/nexus/issues/new?template=bug_report.yml)
- ✨ [Request a feature](https://github.com/Veloxs-ai/nexus/issues/new?template=feature_request.yml)
- 🔐 [Report a vulnerability privately](SECURITY.md) — please do not open a public issue
- 💬 [Getting help](SUPPORT.md)

Everyone participating is expected to follow our [Code of Conduct](CODE_OF_CONDUCT.md).

---

## License

Copyright © 2026 Veloxs AI Inc.

Licensed under the [Apache License, Version 2.0](LICENSE). See [NOTICE](NOTICE) for attribution and third-party dependency information.

**Trademarks.** "Nexus", "Veloxs", and "Veloxs AI", together with associated logos and branding, are trademarks of Veloxs AI Inc. As set out in Section 6 of the Apache License, this license grants **no** rights to use these marks. You may state truthfully that your software is built on Nexus; you may not imply endorsement by or affiliation with Veloxs AI Inc. See [NOTICE](NOTICE) for details.
