# Nexus — Enterprise Intelligence Framework

[![CI](https://github.com/Veloxs-ai/nexus/actions/workflows/ci.yml/badge.svg)](https://github.com/Veloxs-ai/nexus/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/badge/pypi-veloxs--nexus-blue.svg)](https://pypi.org/project/veloxs-nexus/)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://pypi.org/project/veloxs-nexus/)
[![License](https://img.shields.io/badge/license-Apache--2.0-green.svg)](LICENSE)

**Nexus is an open-source enterprise intelligence framework for building secure, governed AI applications, retrieval systems, and operational workflows on your own data.**

It sits *upstream and around* large language models: turning fragmented enterprise data into clean, grounded chunks, semantic embeddings, contextual knowledge graphs, and grounded, policy-checked answers — without locking you into a particular model provider, vector database, or runtime.

```
Data Connectivity → Processing & Enrichment → Knowledge & Retrieval → Intelligent RAG
                                     → AI Orchestration → Governance → Observability
```

---

## Contents

- [What Nexus gives you](#what-nexus-gives-you)
- [Supported Formats & Modalities](#supported-formats--modalities)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Multimodal Ingestion (Office, Audio, Video, Code, DBs)](#multimodal-ingestion-office-audio-video-code-dbs)
- [Semantic embeddings & re-ranking](#semantic-embeddings--re-ranking)
- [Operations: rules, contact policy and cases](#operations-rules-contact-policy-and-cases)
- [Live sources: CDC, webhooks & Slack](#live-sources-cdc-webhooks--slack)
- [Build a RAG workflow](#build-a-rag-workflow)
- [Architecture](#architecture)
- [Configuration](#configuration)
- [Running tests](#running-tests)
- [Upgrading from 3.0.0](#upgrading-from-300)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

---

## What Nexus gives you

Nexus provides seven composable capabilities. Each is an independently installable package that talks to the others through typed configs, JSONL contracts, CLI, and HTTP — **never by importing another layer's code**. That is what makes any layer swappable for your own systems.

| Capability | Package | What it does |
|---|---|---|
| **Data Connectivity** | `nexus.pipeline` | REST connectors with pagination and SSRF defense, batch file drops, streaming events; CDC normalization (Debezium, Maxwell, MongoDB change streams, PostgreSQL `pgoutput` logical replication, generic webhooks) with HMAC-signed delivery |
| **Processing & Enrichment** | `nexus.processing` | Native pure-Python parsers for Word (.docx), Excel (.xlsx), PowerPoint (.pptx), PDF, Audio (WAV/MP3/AIFF), Video (MP4/MOV), Images (PNG/JPEG/BMP), Code AST, OpenAPI, SQLite, MySQL, MongoDB, Email, Chat, Slack exports, CSV, Markdown, and Text; optional OCR / Whisper / video demuxing; format-preserving tokenization (FF1) |
| **Knowledge & Retrieval** | `nexus.retrieval` | Semantic embeddings (FastEmbed `bge-small-en-v1.5`, 384D, local ONNX — or OpenAI), cross-encoder re-ranking, lexical (BM25-style), hybrid RRF, and knowledge-graph retrieval with pluggable stores |
| **Intelligent RAG** | `nexus.guardrails` | Grounded answers with citations, PII masking, prompt-injection defense, fail-closed policy checks |
| **AI Orchestration** | `nexus.experience` | REST API, SDK, CLI, assistant sessions, channel adapters, API-key auth |
| **Governance** | `nexus.security` | RBAC, multi-tenant isolation, authenticated encryption, immutable audit log |
| **Observability** | `nexus.observability` | Metrics, structured logs, distributed trace spans, AI interaction events, alerting |

**Design properties worth knowing about:**

- **Runs locally.** Embeddings and re-ranking run on CPU through ONNX (FastEmbed); models download once and are cached (`NEXUS_MODEL_CACHE_DIR`). No API calls unless you choose the OpenAI provider.
- **Resource-aware.** OCR and Whisper models load lazily, are shared process-wide, use CUDA or Apple MPS when present, and can be unloaded when idle (`release_idle_models`).
- **Thread-safe and serverless-friendly.** In-memory stores are guarded by `threading.Lock`; `in_memory_only=True` (the default) skips disk I/O entirely.
- **Typed configuration end to end.** Every layer's config is a Pydantic model, so a control plane can introspect the schema and render forms automatically.
- **Multi-tenant by construction.** Encryption and tokenization derive a tenant-bound salt (`HKDF-SHA256`), so two tenants processing identical data produce cryptographically distinct ciphertext.

> **Processing and embedding are separate steps.** `process_*` methods return clean, grounded chunks (text + citations + metadata) and never vectors. Embed at storage time with `embed_texts()` / `embed_query()` so your index always uses one model. See [Semantic embeddings & re-ranking](#semantic-embeddings--re-ranking).

---

## Supported Formats & Modalities

Nexus includes **pure-Python binary and text decoders**. Every modality produces text chunks with format-aware grounded citations, so all of them can be embedded into one semantic index.

| Category | Supported Formats | Native Features & Grounding |
|---|---|---|
| **Office Documents** | `.docx` (Word), `.xlsx` (Excel), `.pptx` (PowerPoint) | OpenXML archive decompression; heading hierarchy (`Heading1..6`) & markdown tables for Word; multi-sheet cell matrices & row narratives for Excel; slide text, speaker notes & layouts for PowerPoint; embedded image OCR. |
| **Documents & Data** | `.pdf`, `.csv`, `.md`, `.txt`, `.json`, `.jsonl` | ISO 32000-1 PDF stream decompression & page citations; image XObject extraction; embedded image OCR; CSV row-level narratives (`[Row ID: 1] col: val`); smart boundary-aware paragraph chunking for Markdown & text. |
| **Audio & Speech** | `.wav`, `.aiff`, `.mp3` | Python 3.13-safe RIFF/AIFF/ID3 decoders; RMS loudness; Zero-Crossing Rate; Voice Activity Detection (VAD); 7-band spectral decomposition (20Hz–20kHz); temporal windows (`[00:00 - 00:10]`); Whisper transcription. |
| **Video** | `.mp4`, `.mov`, `.m4v`, `.webm` | ISO BMFF container parser (`moov`/`trak`/`mdia`/`minf`); temporal scene framing; keyframe OCR and audio-track transcription (optional `[video]`, `[ocr]`, `[audio-ml]`). |
| **Images** | `.png`, `.jpeg`, `.jpg`, `.bmp`, `.gif`, `.tiff`, `.webp` | Chunked binary parser; dimensions and metadata; OCR of visible text (optional `[ocr]`, downscaled to 2560 px). |
| **Code & APIs** | `.py`, `.ts`, `.js`, `.go`, `.rs`, `.java`, `.cpp`, `.cs`, OpenAPI 3.0/3.1, Swagger 2.0 | Standard library Python AST (signatures, parameters, decorators, cyclomatic complexity); polyglot regex scanners; OpenAPI operation and schema model extraction. |
| **Databases** | SQLite (`.db`, `.sqlite`), MySQL, MongoDB | Binary SQLite header and B-tree page extraction; CDC change-event normalizer (Debezium/Maxwell/MongoDB change streams); recursive BSON parser and dot-notation document flattener. |
| **Messaging** | `.eml` (RFC 822/MIME), Chat (`slack`, `teams`), Slack export `.zip` / channel `.json`, live Slack events | Multipart MIME extraction, DKIM/SPF auth headers, thread conversation resolution, speaker turns, timestamp grounding; Slack threads grouped with replies and mentions resolved to names. |

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
pip install "veloxs-nexus[ocr]"        # image / slide / keyframe OCR (EasyOCR)
pip install "veloxs-nexus[audio-ml]"   # speech transcription (faster-whisper)
pip install "veloxs-nexus[video]"      # video demuxing (PyAV)
pip install "veloxs-nexus[all-ml]"     # all three
```

Semantic embeddings (FastEmbed) are part of the core install. On CPU-only servers, install the CPU build of PyTorch before the ML extras to avoid multi-gigabyte CUDA wheels:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
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
# Columns: employee_id, department, salary_usd, contact_email
# [Row ID: 1] employee_id: 101 | department: Engineering | salary_usd: 145000 | contact_email: [EMAIL]
# ...

for step in doc.execution_trace:
    print(f"[{step.step_number}/5] {step.stage_name} ({step.duration_ms}ms)")
```

Embed the chunks when you store them:

```python
vectors = client.embed_texts([c.text for c in doc.chunks])
print(len(vectors[0]), client.embedding_info())
# 384 {'provider': 'fastembed', 'model': 'BAAI/bge-small-en-v1.5', 'dimensions': 384}
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

## Multimodal Ingestion (Office, Audio, Video, Code, DBs)

Nexus provides two flexible ways to ingest multimodal content:

### 1. Universal Ingestion (`client.process_document`)

Pass raw `bytes` or a local file path along with the file `name`. Nexus automatically identifies the format, decompresses binary containers, frames structures, scrubs PII, and returns grounded chunks:

```python
import nexus

client = nexus.NexusClient(in_memory_only=True)

# 1. Spreadsheets (.xlsx) — sheets, rows, and cell matrices
doc_excel = client.process_document(
    document_id="fin-model",
    name="financial_model.xlsx",
    text=excel_bytes,  # or filepath "path/to/financial_model.xlsx"
)

# 2. Word Documents (.docx) — headings, sections, and markdown tables
doc_word = client.process_document(
    document_id="msa-2026",
    name="master_agreement.docx",
    text=docx_bytes,
)

# 3. Audio Streams (.wav, .mp3, .aiff) — metadata, VAD windows, Whisper transcript when installed
doc_audio = client.process_document(
    document_id="earnings-q3",
    name="earnings_call.wav",
    text=wav_bytes,
)

# 4. Video Files (.mp4, .mov) — scene windows, transcript and keyframe OCR when installed
doc_video = client.process_document(
    document_id="walkthrough",
    name="product_walkthrough.mp4",
    text=mp4_bytes,
)

# 5. Images (.png, .jpg) — metadata and OCR text when installed
doc_image = client.process_document(
    document_id="topology",
    name="system_topology.png",
    text=png_bytes,
)
```

### 2. Dedicated Modality Methods

When you need granular control over windowing, sample rates, or format-specific parameters, call the dedicated methods directly:

```python
# Word (.docx) with heading hierarchy
doc = client.process_word(document_id="contract-7", name="contract.docx", docx_bytes=raw_bytes)

# Spreadsheets (.xlsx) with sheet & row-level narrative framing
doc = client.process_spreadsheet("budget-2026", "budget.xlsx", spreadsheet_bytes=raw_bytes)

# Presentations (.pptx) with slide text and speaker notes
doc = client.process_presentation("strategy", "strategy.pptx", presentation_bytes=raw_bytes)

# Audio (.wav, .mp3, .aiff) with configurable temporal windowing
doc = client.process_audio("speech-1", "speech.wav", audio_bytes=raw_bytes, window_seconds=10.0)

# Video (.mp4, .mov) with temporal scene framing
doc = client.process_video("demo", "demo.mp4", video_bytes=raw_bytes, scene_interval_seconds=10.0)

# Images (.png, .jpeg, .bmp) with OCR text
doc = client.process_image("chart", "chart.png", image_bytes=raw_bytes)

# SQLite binary databases (.sqlite, .db)
doc = client.process_sqlite("app-db", "app.db", db_bytes=sqlite_bytes)

# Source code AST (Python, TypeScript, Go, Rust, Java, C++)
doc = client.process_code("pipeline-py", "pipeline.py", code_input=source_code)

# OpenAPI 3.0 / 3.1 & Swagger 2.0 specs
doc = client.process_openapi("orders-api", "openapi.json", spec_data=spec_content)
```

### 3. Unified Cross-Modal Search

Every modality produces text chunks embedded by the same semantic model, so you can index and query across text, spreadsheets, audio transcripts, and diagrams at once:

```python
# Index multi-format documents into a single collection
client.index_document(doc_excel, collection="enterprise_assets")
client.index_document(doc_word, collection="enterprise_assets")
client.index_document(doc_audio, collection="enterprise_assets")

# Query with natural language across all modalities
results = client.search("quarterly revenue and SLA commitments", limit=10)  # searches every collection
for r in results:
    print(f"[{r.score:.3f}] {r.text[:120]}")
```

---

## Semantic embeddings & re-ranking

```python
client = nexus.NexusClient(in_memory_only=True)

passages = ["All database connections require TLS 1.3.", "Employees receive 20 days of PTO."]
doc_vectors = client.embed_texts(passages)                 # passage encoding (batched)
query_vector = client.embed_query("What encryption is required?")  # query encoding
scores = client.rerank("What encryption is required?", passages)   # cross-encoder, 0..1
```

| Setting | Default | Purpose |
|---|---|---|
| `NEXUS_EMBEDDING_PROVIDER` | `fastembed` | `fastembed` (local ONNX) or `openai` |
| `NEXUS_EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Any FastEmbed text model |
| `NEXUS_EMBEDDING_DIMENSIONS` | model size (OpenAI: 384) | Output dimensions |
| `NEXUS_MODEL_CACHE_DIR` | FastEmbed default | Where models are cached — mount a volume in containers |
| `NEXUS_ML_DEVICE` | auto (`cuda` > `mps` > `cpu`) | Device for OCR / Whisper |

Long-running services can free OCR / Whisper memory between jobs:

```python
from nexus.processing.ml_providers import release_idle_models

release_idle_models(max_idle_seconds=600)  # models reload transparently on next use
```

---

## Live sources: CDC, webhooks & Slack

```python
from nexus.processing import cdc, slack_export

# Change data capture — one normalizer for Debezium, Maxwell, MongoDB change streams and generic events
events = cdc.normalize_change_events(payload)       # dict, list, {"events": [...]} or NDJSON
for event in events:
    text = cdc.change_event_text(event)             # one chunk per record
    ...                                             # upsert / delete by event.key

# PostgreSQL logical replication (built-in pgoutput plugin, no server extension)
from nexus.processing.pgoutput import PostgresLogicalStream

stream = PostgresLogicalStream("postgresql://reader@db/bank?sslmode=verify-full", "my_slot", "my_publication")
assert not stream.prerequisites()          # wal_level, REPLICATION role, publication, primary keys
stream.ensure_slot()
for txn in stream.transactions():           # committed transactions, in order
    if txn:
        apply(txn.events)                   # your durable write
        stream.confirm(txn.end_lsn)         # only now may the server free that WAL

# Signed webhook delivery (HMAC-SHA256 with a 5-minute replay window)
ok = cdc.verify_webhook_signature(secret, raw_body, signature_header, timestamp_header)

# Slack Events API
ok = slack_export.verify_slack_signature(signing_secret, raw_body, x_slack_timestamp, x_slack_signature)
action, message, deleted_ts = slack_export.slack_event_message(event)   # upsert | delete | ignore
chunks = slack_export.messages_to_chunks("eng", messages, users)        # same chunking as export files
```

---

## Operations: rules, contact policy and cases

`nexus.operations` holds the pieces for turning live data into accountable actions (loan reminders before a due date, work orders for a degrading machine):

```python
from datetime import date, datetime
from zoneinfo import ZoneInfo
from nexus.operations import ContactPolicy, evaluate_strategy, idempotency_key

strategy = {
    "facts": {"days_to_due": "days_until(next_due_date)"},
    "tables": {"treatment": {"hit_policy": "first", "rules": [
        {"id": "DUE_SOON", "when": "0 <= days_to_due <= 3", "then": {"action": "reminder", "channel": "sms"}},
    ], "default": {"action": "monitor"}}},
    "steps": ["treatment"],
}
result = evaluate_strategy(strategy, {"next_due_date": "2026-09-29"}, today=date(2026, 9, 27))
result.outputs        # {'action': 'reminder', 'channel': 'sms'}
result.reason_codes   # ['treatment:DUE_SOON']

policy = ContactPolicy.preset("IN_RBI")   # 08:00–19:00 recipient time, caps, consent, DND
policy.check("sms", datetime(2026, 9, 27, 20, 0, tzinfo=ZoneInfo("Asia/Kolkata"))).allowed   # False

idempotency_key("PL0000123", "emi:2026-10", "T-3", "sms")   # send-once key for an outbox
```

Rule expressions are parsed against an allow-list (comparisons, `and`/`or`, arithmetic, `in`, a few safe functions such as `days_until`, `add_days`, `today`), so rules can be stored as data and edited by business users without any risk of code execution.

### A complete loop, without any platform

The same modules run a whole operations loop in plain Python — score, decide, respect contact rules, keep a holdout, send once, read replies, measure:

```python
from datetime import UTC, datetime
from nexus.operations import (ContactPolicy, DryRunProvider, IntentClassifier, Message,
                              OperationsEngine, compare)

strategy = {
    "facts": {"days_to_due": "days_until(next_due_date)", "cycle": "str(next_due_date)"},
    "scorecards": {"risk": {                       # points scorecard with reason codes
        "base_points": 600, "base_odds": 50, "pdo": 20,
        "bands": [{"band": "low", "min_score": 590}, {"band": "high", "min_score": 0}],
        "outputs": {"band": "risk_band"},
        "characteristics": [{"id": "BOUNCES", "field": "bounces_6m", "missing_points": 300,
                             "bins": [{"when": "value == 0", "points": 320},
                                      {"when": "value >= 1", "points": 260}]}]}},
    "tables": {"treatment": {"hit_policy": "first", "rules": [
        {"id": "DUE_SOON", "when": "0 <= days_to_due <= 3 and risk_band == 'high'",
         "then": {"action": "reminder", "channel": "whatsapp", "stage": "T-3"}}],
        "default": {"action": "monitor", "channel": "none"}}},
    "steps": ["risk", "treatment"],
    "actions": {"reminder": {"kind": "message", "fallback_channels": ["sms"]}},
    "experiment": {"name": "q4", "arms": {"treatment": 90, "holdout": 10}},
}
sms = DryRunProvider()                                    # or WebhookProvider / SmtpEmailProvider / …
engine = OperationsEngine(strategy, ContactPolicy.preset("IN_RBI"), {"sms": sms, "whatsapp": sms})
now = datetime(2026, 10, 8, 6, 30, tzinfo=UTC)
engine.upsert("LN-1", {"next_due_date": "2026-10-10", "bounces_6m": 2}, now)
plans = engine.evaluate_due(now)          # decision, reason codes, next state, planned actions
engine.dispatch(now, lambda ref, action, facts: Message(action.channel, to="+91 90000 00000",
                                                       body="Your EMI is due on 10 Oct."))

IntentClassifier().classify("Salary late hai, 12 tareekh tak pay kar dunga").intent  # 'promise_to_pay'
compare((850, 1000), (80, 100)).as_dict()    # lift, p-value, Wilson intervals, conclusive?
```

| Module | What it gives you |
|---|---|
| `scorecard` | Points scorecards on a base-points / odds / PDO scale, probability per score, bands, adverse-action style reason codes |
| `engine` | `plan_case` — facts to decision, next state and actions with permanent idempotency keys, contact rules, channel fallback, opt-outs, pauses and holdout; `OperationsEngine` in memory |
| `intents` | Reply intent in English, Hinglish, Hindi and Marathi with confidence, promise dates, payment references, stop requests; optional LLM fallback that only sees redacted text |
| `messaging` | `{field}`-only templates, recipient masking, providers: dry run, HMAC-signed webhook, SMTP, WhatsApp Cloud (approved templates), Twilio |
| `experiments` | Wilson intervals, two-proportion z-test, lift with confidence interval and a minimum-sample guard |
| `signals` | `AssetMonitor` — explainable anomaly scores from sensor readings (limits, robust z, drift, trend and time to limit, data quality, noisy-OR fusion); `diagnose` — likely failure mode with recommended checks |
| `workorders` | ServiceNow incidents, IBM Maximo work orders, Teams cards and a dry run behind one `submit()`, idempotent per key |

### Condition monitoring and work orders

```python
from datetime import UTC, datetime, timedelta
from nexus.operations import AssetMonitor, ServiceNowProvider, WorkItem, diagnose, specs_from_dict

monitor = AssetMonitor(specs_from_dict({
    "vibration_mm_s": {"warn_high": 4.5, "alarm_high": 7.1, "valid_min": 0, "valid_max": 50},
    "bearing_temp_c": {"warn_high": 80, "alarm_high": 95},
}))
start = datetime(2026, 10, 8, tzinfo=UTC)
for minute in range(26 * 60):                                  # feed readings in time order
    t = start + timedelta(minutes=minute)
    wear = max(0, minute - 24 * 60) / 60
    monitor.update(t, {"vibration_mm_s": 2.2 + 1.9 * wear, "bearing_temp_c": 61 + 7.5 * wear})
verdict = monitor.assess(now=t)       # anomaly_score, failure_risk, data_quality, time_to_limit_hours, reasons
diagnose(verdict).failure_mode        # 'bearing wear' (+ confidence, evidence, recommended checks)
state = monitor.to_dict()             # persist per asset; AssetMonitor.from_dict(specs, state) to resume

# ServiceNowProvider("https://acme.service-now.com", username="nexora", password=...).submit(
#     WorkItem("P-101: bearing wear", "...", idempotency_key="P-101|incident-1|corrective", asset_ref="P-101"))
```

Rules decide what to do with the verdict (`plan_case` action kind `work_order`, optionally after approval).

### Kafka

```python
from nexus.processing.kafka import KafkaSettings, KafkaSource, decode   # pip install 'veloxs-nexus[kafka]'

source = KafkaSource(KafkaSettings(bootstrap_servers="broker:9093", topics=["plant.telemetry"],
                                   group_id="my-app", username="app", password="..."))  # SASL_SSL + SCRAM
for batch in source.batches(max_records=500):
    documents = [doc for record in batch for doc in decode(record, "json")]
    apply(documents)          # your durable write
    source.commit(batch)      # then the offsets: a crash in between replays, never skips
```

`source.lag()` reports what the group has not processed yet without joining it. Mutual TLS: set
`security_protocol="SSL"` with `ssl_certificate_location` / `ssl_key_location`. Avro through a Schema
Registry: `decode(record, "debezium", avro_decoder("https://registry:8081", user, password))`
(`pip install 'veloxs-nexus[kafka-avro]'`).

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
# Semantic embedding
from nexus.retrieval.semantic import create_text_embedder

vector = create_text_embedder().embed_query("Enterprise cloud infrastructure")

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

For durable persistence, `nexus.database` builds a reference schema for your embedding size:

```python
from nexus import pgvector_ddl

print(pgvector_ddl(384))   # vector(384) + HNSW index + generated tsvector with a GIN index
```

Above 2000 dimensions the column becomes `halfvec` automatically (HNSW supports `halfvec` up to 4000 dimensions). `mysql_ddl(dim)` and `mongo_atlas_vector_index(dim)` cover MySQL 9 and MongoDB Atlas Vector Search.

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

The suite is deterministic and needs no cloud services; the first run downloads the small FastEmbed models (~100 MB) into the model cache.

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

## Upgrading from 3.0.0

3.0.1 separates processing from embedding and removes the legacy 3072D hashing projection:

| Removed | Use instead |
|---|---|
| `NexusClient.embed()`, `ProcessedChunk.embedding`, `chunk_embeddings=` | `client.embed_texts([...])` at storage time, `client.embed_query(q)` at search time |
| `embed_image` / `embed_audio` / `embed_video_scene` | Embed the chunk text produced by `process_image` / `process_audio` / `process_video` |
| `HashingEmbedder`, `local_hashing` provider | `fastembed` (default) or `openai` |
| `normalize_mysql_cdc_event`, `normalize_mongo_change_event` | `cdc.normalize_change_event` |
| `PGVECTOR_DDL_SCHEMA`, `MYSQL_DDL_SCHEMA`, `MONGO_ATLAS_VECTOR_SEARCH_INDEX` | `pgvector_ddl(dim)`, `mysql_ddl(dim)`, `mongo_atlas_vector_index(dim)` |
| `semantic` extra | Nothing — FastEmbed is a core dependency |

Stored 3072D vectors are not compatible with the new model: re-embed stored chunk text once with `embed_texts()`. Full list in the [CHANGELOG](CHANGELOG.md).

---

## Documentation

Full documentation is on the website: the **[User & Integrator Guide](https://nexus.veloxs.ai/nexus-guide.html)** (install, tutorials, how-to) and the **[Documentation](https://nexus.veloxs.ai/documentation.html)** (architecture, API reference, release notes). The repository guides:

| Guide | What it covers |
|---|---|
| [Integrator Guide](docs/USING_NEXUS.md) | The comprehensive reference — every layer in detail, the security model, extension points, and what is production-grade today. **Start here after the quick start.** |
| [Architecture Overview](docs/ARCHITECTURE_OVERVIEW.md) | Design principles, the loose-coupling rule, and per-layer capabilities |
| [Integration Guide](docs/INTEGRATION_GUIDE.md) | Installation, library vs. CLI integration patterns, environment variables |
| [Processing Reference](docs/PROCESSING_REFERENCE.md) | Ingestion formats, the five processing phases, output structure, database setup |
| [Processing & Embedding Spec](docs/PROCESSING_AND_EMBEDDING_SPEC.md) | Chunking rules and how chunks are embedded, specified precisely |

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
