# 🧪 Nexus Enterprise AI Platform — Testing Guide

This guide provides an overview of the test suites, configurations, and verification patterns across the **Nexus** repository (the main AI engine) and its integration with the **Veloxs Platform** control plane.

---

## 🏗️ Repository Architecture & Ecosystem

The codebase is split across three major directories:

1. **`nexus`** *(Main Engine)*: 
   - A layered, config-driven enterprise AI framework with seven loosely-coupled layers.
   - Designed with zero side effects at import time, fail-closed security defaults, and no inter-layer Python imports.
   - Contains a core orchestrator and seven independent sub-packages under `nexus/`.

2. **`veloxs-platform`** *(Control Plane & UI)*:
   - A multi-tenant control plane providing a web application (FastAPI + static front-end) to build and run Nexus pipelines.
   - Introspects Nexus config schemas from the layers to dynamically render configurations.

---

## 🧪 The Nexus Testing Suite

The `nexus` repository contains **182 deterministic, offline, and side-effect-free tests** split across the core platform package and its seven independent layers. They require no cloud credentials, model downloads, or network access.

### Environment & Executable Setup

To run the tests, activate the `nexus` Conda environment (Python 3.11) and run `pytest` in the respective package root:

```bash
# 1. Activate the conda environment
conda activate nexus

# 2. Run the core platform tests (from nexus root)
cd nexus
python -m pytest

# 3. Run individual layer tests (from each layer's subdirectory)
cd enterprise-data-pipeline && python -m pytest
cd ../data-processing-enrichment && python -m pytest
cd ../embedding-retrieval-intelligence && python -m pytest
cd ../orchestration-guardrails && python -m pytest
cd ../experience-api-engagement && python -m pytest
cd ../security-governance && python -m pytest
cd ../observability-monitoring && python -m pytest
```

---

## 🚀 Verified Use Cases & Integration Examples

Below are the primary user integration paths that have been tested and verified to work correctly.

### Use Case 1: Direct Python Library Import
You can import `NexusPlatform` directly into your pipelines. This has been verified in `tests/test_nexus_config.py` and `tests/test_nexus_platform.py`.

```python
from pathlib import Path
from nexus import NexusPlatform

# Initialize the platform using configuration YAML
config_file = Path("configs/nexus.yaml")
platform = NexusPlatform.from_config(config_file)

# Execute an interactive query
query = "What is the security policy regarding Multi-Factor Authentication (MFA)?"
response = platform.ask(query, channel="assistant")
print(response)
```

### Use Case 2: Programmatic Ingestion & Indexing
To run the full end-to-end ingestion and indexing pipeline programmatically:

```python
from pathlib import Path
from nexus import NexusPlatform

platform = NexusPlatform.from_config(Path("configs/nexus.yaml"))

# Triggers data transformations (Layer 2) and indexes (Layer 3)
logs = platform.prepare_demo()
for log_line in logs:
    print(log_line)
```

### Use Case 3: CLI Subprocess Execution
Sandboxed environments can call the platform using the Python command-line utility. This is verified in `tests/test_nexus_cli.py`:

```bash
# Validate configs
nexus validate-platform configs/nexus.yaml

# Ask query
nexus ask configs/nexus.yaml "What is the policy for password changes?"
```

---

## 📂 Detailed Test Index by Layer

### 1. Core Platform & CLI (`nexus/`)
*Located in `nexus/tests/`* — **11 Tests**
* **CLI Command Validation (`test_nexus_cli.py`)**: Tests Typer CLI commands (`validate-config`, `validate-platform`, `prepare-demo`) using `CliRunner`.
* **Config Parsing (`test_nexus_config.py`)**: Validates YAML parsing and layers configuration loading.
* **Platform & Security Policies (`test_nexus_platform.py`)**:
  - Checks layer contract status (e.g. verifying `pyproject.toml`, `README.md`, config schema existence).
  - Enforces path-traversal blocking (raises `PlatformSecurityError` for path traversal outside the workspace).
  - Asserts executable safety (rejecting relative/unsafe/non-existent Python interpreters).

### 2. Layer 1: Enterprise Data Pipeline (`enterprise-data-pipeline/`)
*Located in `enterprise-data-pipeline/tests/`* — **19 Tests**
* **API Connector (`test_api_connector.py`)**: Validates REST API extraction, rate limiters, pagination, header injection, and security rules.
* **Batch Ingestion (`test_batch.py`)**: Tests parsing directory drops, chunk loading, and state checkpoints.
* **CDC Ingestion (`test_cdc.py`)**: Tests mock transaction log capturing, schema mapping, and source deduplication.
* **CLI/Config Interface (`test_cli.py`, `test_config.py`)**: Validates CLI command execution and pipelines configuration.
* **Data Integrity & Streaming (`test_integrity.py`, `test_streaming.py`)**: Asserts stream-consumer checkpoint stability, error boundaries, and hash checking.

### 3. Layer 2: Data Processing & Enrichment (`data-processing-enrichment/`)
*Located in `data-processing-enrichment/tests/`* — **13 Tests**
* **Document Chunking (`test_chunking.py`)**: Verifies token-based and character-based text segmenting, overlap logic, and boundary separators.
* **Metadata Extraction (`test_enrichment.py`)**: Asserts keyword tagging, email patterns, date patterns, currency matching, and content classifications.
* **ETL Transformations (`test_transforms.py`)**: Validates text cleaning, stripping, normalization, and tokenizers.
* **Pipeline Orchestrator (`test_pipeline.py`)**: Verifies end-to-end execution flow of enrichment steps.

### 4. Layer 3: Knowledge Retrieval & Intelligence (`embedding-retrieval-intelligence/`)
*Located in `embedding-retrieval-intelligence/tests/`* — **16 Tests**
* **Embedding Providers (`test_embeddings.py`)**: Asserts deterministic offline vector generation mock contracts.
* **Vector Store (`test_vector_store.py`)**: Checks document serialization, cosine/Euclidean similarity queries, and partition storage.
* **Lexical & BM25 (`test_lexical.py`)**: Validates token frequency indexing and keyword match grading.
* **Knowledge Graph (`test_graph.py`)**: Tests graph relationships traversal, node-edge properties, and paths.
* **Hybrid Retrieval & Reranking (`test_hybrid.py`, `test_ranking.py`)**: Verifies reciprocal rank fusion (RRF) and post-retrieval reranking pipelines.
* **Indexing Core (`test_indexing.py`)**: Tests pipeline indexing execution.

### 5. Layer 4: AI Orchestration & Governance (`orchestration-guardrails/`)
*Located in `orchestration-guardrails/tests/`* — **34 Tests**
* **PII Redaction & Masking (`test_pii.py`)**: Asserts regex patterns for emails, phone numbers, SSNs, and credit cards (Luhn algorithm verification).
* **Prompt Hardening & Normalization (`test_normalization.py`, `test_prompt_security.py`)**: Checks Unicode normalization, escape seq clean-up, and prompt-injection defense heuristics.
* **Policy Constraints (`test_policy.py`, `test_offtopic.py`)**: Validates off-topic classification, keyword blocklists, and safety policy checks.
* **Grounded RAG & Verification (`test_rag.py`, `test_verification.py`, `test_orchestrator.py`)**: Validates context citation integrity, hallucination checks, confidence grading, and response guardrails routing.

### 6. Layer 5: Experience API & Engagement (`experience-api-engagement/`)
*Located in `experience-api-engagement/tests/`* — **34 Tests**
* **FastAPI Service (`test_api.py`, `test_service.py`)**: Tests endpoint payloads, server startup, query routing, and HTTP status codes.
* **Auth & Session Management (`test_auth.py`)**: Asserts API-key checks, session duration bounds, and cross-session security.
* **SDK Interface (`test_sdk.py`, `test_gateway.py`)**: Verifies client-wrapper functionality and SDK connector hooks.
* **Assistant Channels (`test_channels.py`, `test_assistant.py`)**: Evaluates payload adapters for web widgets, chat history models, and agent loops.

### 7. Layer 6: Security, Privacy & Compliance (`security-governance/`)
*Located in `security-governance/tests/`* — **32 Tests**
* **Role-Based Access Control (`test_rbac.py`)**: Tests fine-grained security policies (e.g. comparing owner, analyst, and auditor capability matrices).
* **Tenant Isolation (`test_tenant.py`)**: Validates logical partition enforcement (preventing cross-tenant document reads).
* **AEAD Encryption (`test_encryption.py`)**: Asserts Fernet cryptographic round-trips and HKDF key derivation from master seeds.
* **Audit Logging (`test_audit.py`)**: Checks JSONL audit trail persistence, sanitization of inputs, and log structure validation.

### 8. Layer 7: Observability & Monitoring (`observability-monitoring/`)
*Located in `observability-monitoring/tests/`* — **23 Tests**
* **Structured Logs & Metrics (`test_logging.py`, `test_metrics.py`)**: Verifies structured log formats and custom counters/latencies.
* **Distributed Tracing (`test_traces.py`)**: Tests request trace spans creation and trace propagation.
* **Telemetry Exporters (`test_exporters.py`)**: Asserts OTLP mock export schemas and config-driven telemetry sinks.
* **Alerts Engine (`test_alerts.py`)**: Asserts threshold limits, sliding error rates, and alerts trigger routing.

---

## ⚡ Integration Tests: Veloxs Platform Control Plane

The `veloxs-platform` repo tests the orchestration capabilities and schema-driven generation of Nexus.

### Running Platform Tests
Run `pytest` from the `veloxs-platform` package:
```bash
cd veloxs-platform
conda activate nexus  # or your preferred environment containing FastAPI/Uvicorn
python -m pytest
```

### Scope of Platform Integration Tests (`veloxs-platform/backend/tests/test_platform.py`)
1. **Multi-Tenant SSO & API Key RBAC**:
   - Asserts that API requests require valid headers (`X-API-Key`).
   - Verifies Owner role permissions vs. Viewer role permissions.
2. **Schema Introspection**:
   - Verifies `/api/layers/{layer_id}/schema` produces standard JSON Schemas parsed from Nexus layers' actual Pydantic models.
3. **Pipeline DAG Compiling**:
   - Composes a pipeline graph (nodes + edges), compiles the node configs, schedules execution order, and triggers a run.
4. **Secrets Injection & KMS Integration**:
   - Tests storing KMS-backed encrypted secrets (e.g. API tokens) and dynamically resolving `${secret:KEY}` syntax inside layer configs at execution time *without* exposing raw strings in log files.
