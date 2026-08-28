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
* **CSV Files (`.csv`)**: Relational tables, spreadsheets, billing records, departmental budgets.
* **JSON / JSONL (`.json`, `.jsonl`)**: Structured API responses, event logs, customer records.
* **Markdown (`.md`, `.markdown`)**: Handbooks, policy manuals, system documentation.
* **Plain Text (`.txt`)**: Notes, emails, memos, raw logs.

### 3.2 File-Drop / Batch Directory Ingestion
Drop your files into the raw landing directory:
```
data-processing-enrichment/data/raw/
├── policy_documents.jsonl
├── customer_profiles.jsonl
├── company_financials.csv
└── employee_handbook.md
```

### 3.3 Programmatic Python Ingestion
```python
from nexus_pipeline.batch import read_file
from pathlib import Path

# Read any supported file format automatically
records = read_file(Path("data-processing-enrichment/data/raw/employee_handbook.md"))
```

---

## 4. How Nexus Processes Documents

Nexus processes documents in 5 distinct phases:

### Phase 1: Encoding & Cleaning
* Enforces strict UTF-8 decoding.
* Strips invalid ASCII and normalizes whitespace characters.

### Phase 2: Format-Aware Structural Chunking
* **Tabular CSV (`chunk_csv`)**: Converts rows into rich contextual narratives so column headers are never severed from their values:
  ```text
  [Row ID: 1] department: Engineering | quarter: Q3 2025 | budget_usd: 1250000 | status: Completed
  ```
* **Structural JSON (`chunk_json`)**: Extracts discrete object and array items as valid indented JSON blocks.
* **Text / Markdown (`chunk_smart_text`)**: Recursively splits on paragraph (`\n\n`) and sentence (`. `) boundaries to guarantee no sentence is cut in half.

### Phase 3: PII Redaction & Metadata Enrichment
* **PII Redaction**: Automatically scrubs email addresses (`[REDACTED_EMAIL]`) and telephone numbers (`[REDACTED_PHONE]`).
* **Metadata Extraction**: Extracts named entities, ISO dates, monetary values, and assigns classification categories (`security`, `finance`, `customer`).
* **Content Hashing**: Generates an MD5 `content_hash` for deduplication and incremental sync.

### Phase 4: 3072-Dimensional Vector Projection
* Projects the chunk into a 3072-dimensional vector space using:
  * **Unigram Projection (1.5x)**: Base vocabulary tokens.
  * **Bigram Projection (2.0x)**: Preserves multi-word phrases (e.g., `"cloud optimization"`).
  * **Trigram Projection (2.5x)**: Preserves entity compounds (e.g., `"acme_tech_corp"`).
  * **L2 Normalization**: Unit-length projection $\frac{V}{\|V\|_2}$ for exact Cosine Similarity.

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
