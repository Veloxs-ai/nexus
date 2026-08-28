# Nexus — Processing & Embedding Specification

> **Document Version:** 2.0  
> **Status:** Production Standard  
> **Applicable Layers:** `data-processing-enrichment`, `embedding-retrieval-intelligence`

---

## 1. Overview

Nexus employs an **industry-standard, format-aware document processing pipeline** coupled with a **3072-dimensional Multi-Gram Vector Projection Embedder**.

This architecture eliminates the flaws of naive word-splitting and low-dimensional hashing by preserving tabular structure, JSON hierarchy, sentence boundaries, and phrase-level semantic context.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            INPUT RAW DOCUMENTS                              │
│                CSV Tables · JSON Objects · Markdown / Text                  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FORMAT-AWARE INTELLIGENT CHUNKING                        │
│   • CSV: Contextual Row Narratives ([Row ID: x] Col: Val | ...)             │
│   • JSON: Structural Object & Record Serialization                          │
│   • Text/MD: Sentence (. ) & Paragraph (\n\n) Sliding Window Boundaries     │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│               3072-DIMENSIONAL MULTI-GRAM VECTOR PROJECTION                 │
│   • Unigrams (1.5x): Base vocabulary tokens                                 │
│   • Bigrams  (2.0x): Multi-word phrases (e.g., "cloud_optimization")        │
│   • Trigrams (2.5x): Entities & named compounds                             │
│   • L2 Normalization: Unit-length projection for exact Cosine Similarity    │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     OUTPUT VECTOR & RETRIEVAL STORAGE                       │
│       PostgreSQL pgvector (vector(3072)) · JSONL Indices · Hybrid RRF       │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Format-Aware Chunking Specifications

### 2.1 Tabular CSV Processing (`chunk_csv`)
* **Problem with Naive Chunking:** Splitting CSV files by word count severs the relationship between column headers and cell values.
* **Nexus Implementation:** Serializes each data row into an explicit narrative record with row metadata:
  ```
  [Row ID: 1] department: Engineering | quarter: Q3 2025 | budget_usd: 1250000 | status: Completed
  [Row ID: 2] department: Operations  | quarter: Q3 2025 | budget_usd: 420000  | status: Over Budget
  ```

### 2.2 Structural JSON Processing (`chunk_json`)
* **Problem with Naive Chunking:** Arbitrary splits break JSON syntax and lose key-value hierarchy.
* **Nexus Implementation:** Extracts discrete top-level objects and array items as independent, fully-formed JSON records with indentation.

### 2.3 Document Text & Markdown Processing (`chunk_smart_text`)
* **Problem with Naive Chunking:** Fixed token counts slice sentences in half, causing fragmented meaning.
* **Nexus Implementation:** Uses a prioritized boundary split:
  1. **Paragraphs:** Double newline (`\n\n`) boundaries.
  2. **Sentences:** Period followed by space (`. `).
  3. **Words:** Whitespace boundaries.
  4. **Overlap:** Configurable sliding-window overlap (e.g., 200 characters / tokens) to maintain cross-chunk context.

---

## 3. 3072-Dimensional Vector Projection Specification

### 3.1 Mathematical Formulation
For any chunk $T$, the vector $V \in \mathbb{R}^{3072}$ is computed as:

$$V = \sum_{w_i \in \text{Unigrams}} 1.5 \cdot \mathbf{h}_1(w_i) + \sum_{(w_i, w_{i+1}) \in \text{Bigrams}} 2.0 \cdot \mathbf{h}_2(w_i, w_{i+1}) + \sum_{(w_i, w_{i+1}, w_{i+2}) \in \text{Trigrams}} 2.5 \cdot \mathbf{h}_3(w_i, w_{i+1}, w_{i+2})$$

Followed by **L2 Unit Normalization**:

$$\hat{V} = \frac{V}{\|V\|_2} = \frac{V}{\sqrt{\sum_{k=1}^{3072} V_k^2}}$$

### 3.2 Benefits of 3072D Multi-Gram Projection
1. **Phrase Preservation (Bigrams):** Differentiates `"cloud optimization"` from `"cost optimization"`.
2. **Entity Matching (Trigrams):** Captures multi-word enterprise entities (e.g., `"acme_tech_corp"`).
3. **Exact Cosine Metric:** Because $\|\hat{V}\|_2 = 1.0$, cosine similarity simplifies to the dot product $\hat{V}_A \cdot \hat{V}_B$.

---

## 4. Recommended Database Schema / Output Table

When storing Nexus processed chunks and embeddings in relational or vector databases (e.g. PostgreSQL with `pgvector` or ClickHouse), use the following schema:

### PostgreSQL DDL (`pgvector`)

```sql
-- Enable the vector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Document Chunks & 3072D Embedding Table
CREATE TABLE document_embeddings (
    chunk_id            VARCHAR(128) PRIMARY KEY,
    document_id         VARCHAR(128) NOT NULL,
    source_job          VARCHAR(64) NOT NULL,
    chunk_index         INTEGER NOT NULL,
    chunk_text          TEXT NOT NULL,
    document_title      VARCHAR(255),
    classification      VARCHAR(64),
    metadata            JSONB DEFAULT '{}'::jsonb,
    
    -- 3072-Dimensional Semantic Vector Column
    embedding           VECTOR(3072) NOT NULL,
    
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create HNSW or IVFFlat Index for sub-millisecond approximate nearest neighbor (ANN) search
CREATE INDEX idx_document_embeddings_hnsw 
ON document_embeddings 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

### Column Type Definitions

| Column Name | SQL Type | Description |
|---|---|---|
| `chunk_id` | `VARCHAR(128)` | Unique compound identifier (`{doc_id}:{chunk_index}`). |
| `document_id` | `VARCHAR(128)` | Source document primary key. |
| `source_job` | `VARCHAR(64)` | The processing job or ingestion pipeline identifier. |
| `chunk_index` | `INTEGER` | 0-indexed position of chunk in the source document. |
| `chunk_text` | `TEXT` | Extracted chunk text or structured narrative. |
| `document_title` | `VARCHAR(255)` | Original document or file title. |
| `classification` | `VARCHAR(64)` | Categorical classification (`security`, `finance`, `customer`, `general`). |
| `metadata` | `JSONB` | Extracted entities, dates, emails, and custom tags. |
| `embedding` | `VECTOR(3072)` | **3072-Dimensional L2-Normalized float vector**. |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | Indexing timestamp. |

---

## 5. Programmatic Usage in Python

```python
from nexus_processing.chunking import chunk_text
from nexus_retrieval.embeddings import HashingEmbedder, cosine_similarity

# 1. Process document into format-aware chunks
raw_csv = "department,budget,status\nEngineering,1250000,Completed\nSales,520000,Completed"
chunks = chunk_text(raw_csv)

# 2. Generate 3072-dimensional vector embeddings
embedder = HashingEmbedder(dimensions=3072, normalize=True)
vectors = [embedder.embed(chunk) for chunk in chunks]

# 3. Query similarity search
query_vector = embedder.embed("What was the engineering budget?")
scores = [cosine_similarity(query_vector, vec) for vec in vectors]

for chunk, score in zip(chunks, scores):
    print(f"[{score:.4f}] {chunk}")
```
