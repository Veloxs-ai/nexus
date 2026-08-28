# Enterprise Data Pipeline Layer

> Part of **[Nexus — Enterprise Intelligence Framework](../README.md)**, the open-source framework for secure, governed AI applications.
> This layer provides the **Data Connectivity** capability.


Ingests enterprise data across multi-format batch files (CSV, JSON, JSONL, TXT, Markdown), paginated REST APIs, streaming Kafka events, and database Change Data Capture (CDC).

---

## 🛠️ Capabilities

- **Multi-Format Batch Ingestion**: Ingests `.csv`, `.json`, `.jsonl`, `.txt`, `.md`, and `.markdown` files.
- **REST API Connectors**: Handles token-based authentication and pagination.
- **Event Streaming & CDC**: Ingestion support for Kafka topic streams and Debezium change data capture.
- **Integrity & Checkpointing**: Dead-letter queues, checkpoint tracking, and schema validation.

---

## 📂 Project Layout

```text
enterprise-data-pipeline/
  configs/
    sources.json
  data/
    raw/
  docs/
    architecture.md
  src/nexus_pipeline/
    batch.py
    cdc.py
    cli.py
    config.py
    integrity.py
    models.py
    streaming.py
  pyproject.toml
```
