# Nexus Enterprise AI Platform — Project Overview

Nexus is a layered, config-driven enterprise AI platform designed to turn fragmented data into secure, grounded, and context-aware intelligence. It is built as a set of seven loosely-coupled layers, each independently installable and replaceable.

---

## 🏛️ System Architecture & Design Principles

Nexus adheres to strict architectural guidelines to ensure enterprise-grade security and maintainability:
* **Zero Inter-Layer Imports**: Layers never import code from one another. Integration occurs exclusively through shared JSONL data boundaries, file configurations, and CLI subprocess execution.
* **Zero Side Effects at Import Time**: Importing any module has no side effects, ensuring reproducible, lightweight startup times.
* **Fail-Closed Security**: Any configuration error, authorization mismatch, or policy violation defaults to a hard block.
* **Introspection-First Configuration**: Every layer's configuration is defined as a strongly typed Pydantic model. This allows external control planes (such as the `veloxs-platform` UI) to dynamically introspect schemas and render configuration forms automatically.

---

## 📂 Detailed Layer Capabilities

Here is the breakdown of what each of the seven layers is designed to do, and what is currently simulated/mocked for local development:

### 1. Enterprise Data Pipeline (`enterprise-data-pipeline`)
* **What it does**: Ingests enterprise data from multiple source patterns:
  - **REST API Connector**: Fetches API endpoints with built-in token authentication, configurable page sizing, pagination, and a strict same-origin checker to prevent cross-origin redirect security issues.
  - **Batch Ingestion**: Reads directory drops containing `JSON`, `JSONL`, or `CSV` files and parses them into standardized records.
  - **Change Data Capture (CDC)**: Normalizes incoming Debezium database operation streams (`INSERT`, `UPDATE`, `DELETE`) into standard events.
  - **Streaming Connector**: Simulates event streams by reading local files containing JSON records.
* **What it does NOT do**: 
  - Real database CDC captures or Kafka queue ingestion are not implemented in the base package; they raise a `NotImplementedError` and require custom production adapters.
  - Ingesting file drops from cloud object storage (like AWS S3) is simulated and requires a production object-store adapter.

### 2. Data Processing & Enrichment (`data-processing-enrichment`)
* **What it does**: Prepares and structures raw ingested records for retrieval:
  - **Transforms**: Handles string trimming, case normalization (`upper`, `lower`, `title`), column renaming, and setting default values.
  - **Chunking**: Splits long text segments using a sliding window algorithm with configurable overlaps.
  - **Metadata Extraction**: Extracts entities, email addresses, dates, currency values, and keyword tags using regular expressions.
  - **Classification**: Assigns data categories (`security`, `finance`, `customer`, `general`) dynamically based on extracted tags.
* **What it does NOT do**:
  - The chunking algorithm is a naive word-based whitespace splitter. It does not use tokenizers (like Byte-Pair Encoding, tiktoken, or SentencePiece) to count real LLM tokens.
  - Entity extraction relies on simple capitalization heuristics (`[A-Z][a-z]+`) instead of full Named Entity Recognition (NER) models.

### 3. Knowledge Retrieval & Intelligence (`embedding-retrieval-intelligence`)
* **What it does**: Provides search capabilities across ingested enterprise context:
  - **Vector Store**: A local JSON-backed store that calculates cosine similarity scores.
  - **Lexical Index**: A basic inverted index that performs query term frequency scoring.
  - **Knowledge Graph**: Builds relationship graphs (linking documents to entities, tags, and parent scopes) and scores query overlap with node neighbors.
  - **Hybrid Search**: Combines vector, lexical, and graph search results using Reciprocal Rank Fusion (RRF) and custom reranking formulas.
* **What it does NOT do**:
  - Does not generate real semantic vector embeddings. The embedder is a deterministic hashing generator (`HashingEmbedder`) that creates a fingerprint based on word hashes.
  - The vector store runs linear scans (`O(N)`) over in-memory entries, making it unsuitable for large-scale production without replacing it with an HNSW/ANN store (like pgvector or Qdrant).
  - The lexical search is a basic token overlap counter, not a statistical scoring algorithm like BM25 or TF-IDF.

### 4. AI Orchestration & Governance (`orchestration-guardrails`)
* **What it does**: Acts as the guardrail engine for LLM inputs and outputs:
  - **PII Detection & Masking**: Flags and redacts sensitive PII (emails, phones, SSNs, credit cards via the Luhn algorithm) using configurable mask characters.
  - **Prompt Hardening**: Normalizes Unicode inputs and checks for substring blocklists (prompt injection/data leakage).
  - **Grounded Answer Synthesis**: Compiles a mock answer by prefixing retrieved context with `"Based on retrieved enterprise context: "`.
  - **Grounding Verification**: Calculates a grounding confidence score based on word-level overlaps between the answer and retrieved citations.
* **What it does NOT do**:
  - Does not invoke an actual LLM. Synthesizing answers and verifying grounding are done offline via local string manipulation.
  - Does not use machine learning classifiers for safety/toxicity detection, relying instead on static regex and keyword rules.

### 5. Experience API & Engagement (`experience-api-engagement`)
* **What it does**: Exposes the platform functionality to clients:
  - **REST API**: A FastAPI service providing access control endpoints.
  - **CLI & SDK**: Allows programmatic platform access from other Python applications.
  - **Auth**: Validates API tokens using constant-time comparisons (`hmac.compare_digest`) and assigns user roles and capabilities.
  - **Gateway Dispatcher**: Shells out requests to the guardrails CLI via subprocesses to maintain sandboxed execution.
* **What it does NOT do**:
  - The chat assistant channels (like Slack or web widgets) are mocks.
  - The subprocess gateway path resolver does not enforce strict workspace boundary checks, introducing path traversal risks.

### 6. Security & Governance (`security-governance`)
* **What it does**: Enforces platform trust boundaries:
  - **RBAC**: Implements a policy engine validating roles (`owner`, `analyst`, `auditor`, etc.), tenant bounds, capabilities, and data scopes.
  - **Fernet Encryption**: Performs symmetric authenticated encryption of sensitive config parameters.
  - **Key Derivation**: Derives keys securely using HKDF-SHA256 from master key material.
  - **Audit Logging**: Persists access control decisions into tamper-resistant local JSONL audit logs.
* **What it does NOT do**:
  - Does not support automatic key rotation.
  - Integration with hardware security modules (HSM) or key management systems (like AWS KMS) is a stub.

### 7. Observability & Monitoring (`observability-monitoring`)
* **What it does**: Tracks system health and interaction telemetry:
  - **Telemetry**: Records service metrics, distributed trace spans, and structured logs to JSONL files.
  - **Alerting**: Triggers alerts if API latencies or error rates exceed configured thresholds.
* **What it does NOT do**:
  - The telemetry exporters do not push data outbound to Prometheus, OpenTelemetry, or Datadog; they are configuration validation stubs only.
