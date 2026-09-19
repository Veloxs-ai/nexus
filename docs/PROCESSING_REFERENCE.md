# Nexus — Document Processing Reference

> **Platform:** Nexus (7-Layer Enterprise AI Data & Retrieval Engine)  
> **Embedding Standard:** 3072-Dimensional Multi-Gram Vector Projection (`vector(3072)`)  
> **Processing Standard:** Format-Aware Tabular & Structural Document Chunking + PII Redaction  
> **Version:** 2.0.0 Production  

---

## 📑 Table of Contents
1. [Overview & Architecture](#1-overview--architecture)
2. [How to Use Nexus](#2-how-to-use-nexus)
3. [How to Ingest & Provide Documents](#3-how-to-ingest--provide-documents)
4. [How Nexus Processes Documents](#4-how-nexus-processes-documents)
5. [Output Structure & Format](#5-output-structure--format)
6. [How to Set Up the Output Table](#6-how-to-set-up-the-output-table)
7. [Required Technologies & Infrastructure](#7-required-technologies--infrastructure)
8. [End-to-End Execution Flow](#8-end-to-end-execution-flow)

---

## 1. Overview & Architecture

Nexus is the **Enterprise Intelligence Framework** — a headless, seven-layer framework for data intelligence and vector retrieval. It operates upstream of large language models, converting raw unstructured and semi-structured enterprise documents into high-dimensional, normalized 3072D vector embeddings with strict fail-closed safety guardrails.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            1. INGESTION LAYER                               │
│      CSV Tables · JSON Objects · Markdown Files · TXT / Documents           │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     2. PROCESSING & ENRICHMENT LAYER                        │
│   • CSV: Structured row-level narrative serialization ([Row ID: x] ...)     │
│   • JSON: Isolated structural record extraction                             │
│   • Text/MD: Smart paragraph (\n\n) & sentence (. ) boundary chunking       │
│   • PII Redaction: Automatic email ([REDACTED_EMAIL]) & phone scrubbing     │
│   • Metadata Enrichment: Entities, dates, classification, & MD5 hashes      │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    3. EMBEDDING & RETRIEVAL LAYER                           │
│   • 3072-Dimensional Multi-Gram Vector Projection:                          │
│       - Unigrams (1.5x): Base vocabulary tokens                             │
│       - Bigrams  (2.0x): Multi-word phrase semantics                        │
│       - Trigrams (2.5x): Named entities & compound phrases                  │
│       - L2 Unit Normalization: ||V||₂ = 1.0 for exact Cosine Similarity     │
│   • Hybrid Inverted Lexical + Entity Knowledge Graph + Reciprocal Rank (RRF)│
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                   4. ORCHESTRATION & GUARDRAILS LAYER                       │
│   • PII Masking (Luhn Credit Cards, SSNs, Emails, Phone Numbers)            │
│   • Prompt Injection & Leakage Defense                                      │
│   • Grounding Confidence & Mathematical Citation Overlap Verification       │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          5. OUTPUT DESTINATIONS                             │
│     PostgreSQL pgvector (vector(3072)) · ClickHouse · JSONL Indices         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. How to Use Nexus

Nexus is structured with decoupled layer packages and a unified platform CLI (`nexus.cli`).

### 2.1 Installation & Environment Setup

Nexus requires Python 3.11 or 3.12. Any environment manager works; the
example uses the standard library's `venv`.

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip

pip install veloxs-nexus
```

The single root package exposes all seven layers under the `nexus.*`
namespace — there is no need to install them individually. To work from a
source checkout instead:

```bash
git clone https://github.com/Veloxs-ai/nexus.git
cd nexus
python -m pip install -e ".[dev]"
```

See the [Integration Guide](INTEGRATION_GUIDE.md) for the full setup,
including how to install individual layers for isolated CLI or test use.

### 2.2 CLI Commands

| Command | Syntax | Description |
|---|---|---|
| **Validate Platform** | `python -m nexus.cli validate-platform configs/nexus.json` | Validates configuration integrity across all 7 layers. |
| **Prepare / Ingest Data** | `python -m nexus.cli prepare-demo configs/nexus.json` | Processes raw documents, extracts chunks, and builds 3072D vector indices. |
| **Semantic Query** | `python -m nexus.cli ask configs/nexus.json "<Query>"` | Performs hybrid retrieval, guardrail verification, and returns citations. |

---

## 3. How to Ingest & Provide Documents

You can supply documents to Nexus through multiple channels:

### 3.1 Supported File Types & Input Formats

Nexus provides zero-dependency, pure-Python native decoders for 8 enterprise format categories:

* **Office Documents**:
  - **Word (`.docx`)**: OpenXML archive decompression, heading hierarchy (`Heading1..6`), bullet lists, and markdown tables.
  - **Spreadsheets (`.xlsx`)**: Shared string table resolution, multi-sheet cell matrices, formula handling, and row-level grounded narratives.
  - **Presentations (`.pptx`)**: Slide shape graph extraction, text boxes, layouts, and speaker notes.
* **Documents & Plain Text**:
  - **PDF (`.pdf`)**: ISO 32000-1 object graph parser, FlateDecode decompression, and page-grounded citations (`[Page N]`).
  - **CSV (`.csv`)**: Relational tables, spreadsheets, billing records, departmental budgets converted to row narratives.
  - **Markdown (`.md`, `.markdown`)**: Handbooks, policy manuals, and system documentation.
  - **Plain Text (`.txt`)**: Notes, memos, raw text files.
  - **JSON / JSONL (`.json`, `.jsonl`)**: Structured API responses, event logs, customer records.
* **Audio & Speech**:
  - **Audio Files (`.wav`, `.aiff`, `.mp3`)**: Python 3.13-safe signal decoding, RMS loudness profiling, Zero-Crossing Rate (ZCR), Voice Activity Detection (VAD), 7-band spectral decomposition (20Hz–20kHz), and temporal window framing (`[00:00 - 00:10]`).
* **Video & Images**:
  - **Video Files (`.mp4`, `.mov`, `.m4v`, `.webm`)**: ISO BMFF container parser (`moov`/`trak`), temporal scene chunking, and motion variance.
  - **Image Files (`.png`, `.jpeg`, `.jpg`, `.bmp`)**: 8×8 luminance grid, 64-bin RGB color distribution, and 64-bit dHash perceptual hashing.
* **Source Code & APIs**:
  - **Source Code (`.py`, `.ts`, `.js`, `.go`, `.rs`, `.java`, `.cpp`, `.cs`)**: Python standard library AST (classes, functions, decorators, typed signatures, cyclomatic complexity) and polyglot regex scanners.
  - **OpenAPI / Swagger (`.json`, `.yaml`)**: OpenAPI 3.0/3.1 and Swagger 2.0 route, parameter, and schema model extraction.
* **Databases & Messaging**:
  - **SQLite (`.db`, `.sqlite`)**: Binary SQLite header parsing, page decoding, and table extraction.
  - **MySQL**: Relational row serialization and CDC binlog change event normalizer.
  - **MongoDB**: BSON document deserialization and dot-notation document flattener.
  - **Email & Chat (`.eml`, `slack`, `teams`)**: Multipart MIME decoder, DKIM/SPF headers, and threaded conversation turns.

### 3.2 File-Drop / Batch Directory Ingestion
Drop your files into the raw landing directory:
```
data-processing-enrichment/data/raw/
├── policy_documents.jsonl
├── customer_profiles.jsonl
├── company_financials.csv
├── master_agreement.docx
├── quarterly_briefing.wav
└── employee_handbook.md
```

### 3.3 Programmatic Python Ingestion (`NexusClient`)

Nexus supports both **Universal Auto-Routing** and **Dedicated Modality Methods**:

```python
import nexus

client = nexus.NexusClient(in_memory_only=True)

# 1. Universal Ingestion (pass bytes or file path — Nexus auto-routes)
doc_xlsx = client.process_document(name="budget.xlsx", text=xlsx_bytes)
doc_docx = client.process_document(name="contract.docx", text=docx_bytes)
doc_audio = client.process_document(name="call.wav", text=wav_bytes)
doc_video = client.process_document(name="demo.mp4", text=mp4_bytes)
doc_img = client.process_document(name="chart.png", text=png_bytes)

# 2. Dedicated Modality Methods
doc = client.process_word(name="contract.docx", docx_bytes=docx_bytes)
doc = client.process_spreadsheet(name="budget.xlsx", spreadsheet_bytes=xlsx_bytes)
doc = client.process_presentation(name="slides.pptx", presentation_bytes=pptx_bytes)
doc = client.process_audio(name="call.wav", audio_bytes=wav_bytes, window_seconds=10.0)
doc = client.process_video(name="demo.mp4", video_bytes=mp4_bytes, window_seconds=10.0)
doc = client.process_image(name="chart.png", image_bytes=png_bytes)
doc = client.process_sqlite(name="app.db", db_bytes=sqlite_bytes)
doc = client.process_code(name="service.py", code_input=source_code)
```

---

## 4. How Nexus Processes Documents

Nexus processes documents through a standardized 5-stage execution pipeline:

### Phase 1: Encoding & Container Parsing
* Decompresses binary containers (ZIP/OpenXML for DOCX/XLSX/PPTX, ISO BMFF for MP4, RIFF/AIFF/ID3 for audio, ISO 32000-1 for PDF).
* Enforces strict UTF-8 decoding and NFKC Unicode normalization for text streams.

### Phase 2: Format-Aware Structural Chunking & Grounding
* **Word (`.docx`)**: Heading hierarchy (`Heading1..6`), section nesting, bullet items, and markdown tables.
* **Spreadsheets (`.xlsx`)**: Converts rows into rich contextual narratives:
  `[Workbook: fin.xlsx | Sheet: Revenue | Row 4] Department: Sales | Budget: 150000`
* **Audio (`.wav`, `.mp3`)**: Slices temporal windows with VAD energy classification and 7-band spectral decomposition:
  `[00:00 - 00:10] Audio Segment | RMS: 0.380 (Active) | Centroid: 1650Hz`
* **Video (`.mp4`, `.mov`)**: Temporal scene framing with motion variance.
* **Tabular CSV (`chunk_csv`)**: Contextual row narratives:
  `[Row ID: 1] department: Engineering | quarter: Q3 | budget_usd: 1250000`
* **Text / Markdown (`chunk_smart_text`)**: Boundary-aware paragraph (`\n\n`) and sentence (`. `) splitting.
* **Code AST (`.py`)**: Function and class definitions with typed signatures and line citations (`[Code AST: file.py | Function: foo | Lines: 10-25]`).

### Phase 3: PII Redaction & Safety Guardrails
* Automatically scrubs email addresses (`[EMAIL]`), phone numbers, SSNs, and credit card numbers (Luhn check).
* Enforces prompt injection defenses and secret scrubbing.

### Phase 4: Metadata Enrichment & Content Hashing
* Extracts named entities, ISO dates, and assigns classification categories.
* Generates an MD5 `content_hash` for deduplication and incremental sync.

### Phase 5: 3072-Dimensional Vector Projection
* Projects every chunk into a normalized 3072-dimensional vector space:
  * **Multi-Gram Token Projection**: Unigrams (1.5x), Bigrams (2.0x), Trigrams (2.5x).
  * **Acoustic & Perceptual Features**: RMS envelope, spectral distribution, dHash bit-grids.
  * **Exact L2 Unit Normalization**: $\|V\|_2 = 1.0$ for deterministic cosine similarity across all modalities.

---

## 5. Output Structure & Format

Each processed document chunk produces a structured record containing its text, metadata, and 3072-dimensional vector:

```json
{
  "chunk_id": "policy_documents:doc-001:0",
  "document_id": "doc-001",
  "source_job": "policy_documents",
  "chunk_index": 0,
  "text": "All employees must use MFA for sensitive systems. Access reviews are required quarterly.",
  "metadata": {
    "document_title": "Security Access Policy",
    "classification": "security",
    "tags": ["access", "encryption", "mfa", "security"],
    "entities": ["Access", "Mfa", "Security Access Policy"],
    "emails": ["[REDACTED_EMAIL]"],
    "content_hash": "e4d909c290d0fb1ca068ffaddf22cbd0"
  },
  "embedding": [
    0.024152,
    -0.018431,
    0.039120,
    "...",
    0.008412
  ]
}
```

---

## 6. How to Set Up the Output Table

To store Nexus chunks and embeddings in a production relational/vector database, use **PostgreSQL** with the **pgvector** extension.

### 6.1 PostgreSQL DDL (`pgvector`)

```sql
-- 1. Enable the pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 2. Master Documents Table (3NF Compliant)
CREATE TABLE knowledge_documents (
    document_id         VARCHAR(128) PRIMARY KEY,
    name                VARCHAR(255) NOT NULL,
    file_type           VARCHAR(32) NOT NULL,
    file_size_bytes     BIGINT NOT NULL,
    content_hash        VARCHAR(64) NOT NULL,
    classification      VARCHAR(64) DEFAULT 'general',
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Document Chunks & 3072D Embedding Table
CREATE TABLE knowledge_chunks (
    chunk_id            VARCHAR(128) PRIMARY KEY,
    document_id         VARCHAR(128) NOT NULL REFERENCES knowledge_documents(document_id) ON DELETE CASCADE,
    source_job          VARCHAR(64) NOT NULL,
    chunk_index         INTEGER NOT NULL,
    chunk_text          TEXT NOT NULL,
    metadata            JSONB DEFAULT '{}'::jsonb,
    
    -- 3072-Dimensional Vector Column
    embedding           VECTOR(3072) NOT NULL,
    
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. High-Performance HNSW Vector Index (Sub-millisecond Cosine ANN Search)
CREATE INDEX idx_knowledge_chunks_embedding_hnsw 
ON knowledge_chunks 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- 5. Foreign Key & Metadata B-Tree Indexes
CREATE INDEX idx_knowledge_chunks_doc_id ON knowledge_chunks(document_id);
CREATE INDEX idx_knowledge_chunks_metadata ON knowledge_chunks USING gin(metadata);
```

### 6.2 Python Insertion Example

```python
import psycopg2
from pgvector.psycopg2 import register_vector
from nexus_retrieval.embeddings import HashingEmbedder

# Connect to database
conn = psycopg2.connect("postgresql://postgres:postgres@localhost:5432/nexus_enterprise")
register_vector(conn)
cursor = conn.cursor()

# Generate 3072D embedding
embedder = HashingEmbedder(dimensions=3072, normalize=True)
chunk_text = "All employees must use MFA for sensitive systems."
vector_3072 = embedder.embed(chunk_text)

# Insert chunk
cursor.execute(
    """
    INSERT INTO knowledge_chunks (chunk_id, document_id, source_job, chunk_index, chunk_text, embedding)
    VALUES (%s, %s, %s, %s, %s, %s)
    ON CONFLICT (chunk_id) DO UPDATE SET
        chunk_text = EXCLUDED.chunk_text,
        embedding = EXCLUDED.embedding;
""",
    ("doc-001:0", "doc-001", "policy_documents", 0, chunk_text, vector_3072),
)

conn.commit()
cursor.close()
conn.close()
```

### 6.3 Cosine Similarity Query Example

```sql
-- Retrieve Top 5 Most Relevant Chunks for a 3072D Query Vector
SELECT 
    chunk_id,
    document_id,
    chunk_text,
    metadata->>'document_title' AS title,
    1 - (embedding <=> '[0.024152, -0.018431, ...]'::vector(3072)) AS cosine_similarity
FROM knowledge_chunks
ORDER BY embedding <=> '[0.024152, -0.018431, ...]'::vector(3072)
LIMIT 5;
```

---

## 7. Required Technologies & Infrastructure

To operate and deploy the Nexus processing and output pipeline, the following technologies are recommended:

| Component | Technology | Recommended Version | Purpose |
|---|---|---|---|
| **Runtime** | Python | `3.11` or `3.12` | Core pipeline execution engine. |
| **Package Manager** | pip | `venv` (stdlib), or any of conda / uv / Poetry | Isolated virtual environment. |
| **Vector Database** | PostgreSQL + pgvector | PostgreSQL `15+`, pgvector `v0.5+` | Storage and indexing for `vector(3072)`. |
| **Index Algorithm** | HNSW (Hierarchical Navigable Small World) | Built into pgvector | Sub-millisecond approximate nearest neighbor search. |
| **Object Storage (Optional)** | AWS S3 / Google Cloud Storage | Standard | Landing zone for raw multi-gigabyte document batches. |
| **Orchestration (Optional)** | Celery / Temporal / FastStream | Latest | Scalable distributed job scheduling. |

---

## 8. End-to-End Execution Flow

```bash
# 1. Place raw documents into landing zone
cp my_policy.md data-processing-enrichment/data/raw/

# 2. Run Nexus pipeline
python -m nexus.cli prepare-demo configs/nexus.json

# 3. Query the platform with natural language
python -m nexus.cli ask configs/nexus.json "What is our company policy on MFA?"
```
