# Nexus — Processing & Embedding Specification

> **Document Version:** 3.0 (Nexus 3.0.1)  
> **Status:** Production Standard  
> **Applicable Layers:** `data-processing-enrichment`, `embedding-retrieval-intelligence`

---

## 1. Overview

Nexus separates **processing** (format-aware parsing, chunking, PII masking, citations) from **embedding** (turning chunk text into vectors). Processing is deterministic and returns text chunks only; embedding happens once, at storage time, with one model for the whole index.

```
Raw documents ──▶ process_*()  ──▶ grounded text chunks (text · citation · metadata)
                                            │
                                            ▼
                               embed_texts()  ──▶ vector store (pgvector / MySQL 9 / Atlas)
query ──▶ embed_query() ──▶ dense + lexical candidates ──▶ RRF fusion ──▶ rerank() ──▶ answer
```

---

## 2. Format-Aware Chunking Specifications

### 2.1 Tabular CSV Processing (`chunk_csv`)
* **Problem with Naive Chunking:** Splitting CSV files by word count severs the relationship between column headers and cell values.
* **Nexus Implementation:** Serializes each data row into an explicit narrative record with row metadata:
  ```
  Columns: department, quarter, budget_usd, status
  [Row ID: 1] department: Engineering | quarter: Q3 2025 | budget_usd: 1250000 | status: Completed
  [Row ID: 2] department: Operations  | quarter: Q3 2025 | budget_usd: 420000  | status: Over Budget
  ```
  Rows are packed into ~1,500-character chunks that repeat the column header, so each chunk stands alone.

### 2.2 Structural JSON Processing (`chunk_json`)
* **Problem with Naive Chunking:** Arbitrary splits break JSON syntax and lose key-value hierarchy.
* **Nexus Implementation:** Extracts discrete top-level objects and array items as independent, fully-formed JSON records with indentation.

### 2.3 Markdown Processing (`chunk_markdown`)
* Chunks never straddle a heading; each chunk carries a `Section: A > B` breadcrumb so a passage keeps its context after retrieval.

### 2.4 Document Text Processing (`chunk_smart_text`)
* **Problem with Naive Chunking:** Fixed token counts slice sentences in half, causing fragmented meaning.
* **Nexus Implementation:** Uses a prioritized boundary split:
  1. **Paragraphs:** Double newline (`\n\n`) boundaries.
  2. **Sentences:** Period followed by space (`. `).
  3. **Words:** Whitespace boundaries.
  4. **Overlap:** Configurable sliding-window overlap (e.g., 200 characters / tokens) to maintain cross-chunk context.

---

## 3. Embedding Specification

| Property | Default | Notes |
|---|---|---|
| Provider | `fastembed` | Local ONNX runtime on CPU; no API calls. `openai` is the hosted alternative. |
| Model | `BAAI/bge-small-en-v1.5` | 384 dimensions, L2-normalized, cosine similarity |
| Query encoding | `embed_query()` | Asymmetric: queries get the model's query instruction, passages do not |
| Re-ranker | `Xenova/ms-marco-MiniLM-L-6-v2` | Cross-encoder, `rerank(query, passages)` returns (0, 1) scores |
| Cache | `NEXUS_MODEL_CACHE_DIR` | Models download once (~100 MB total) |

Rules:

1. **One model per index.** Store the model name with each vector (`embedding_info()`); re-embed when it changes.
2. **Embed what you retrieve.** Embed the final chunk text (after PII masking), optionally prefixed with the document name for context.
3. **Batch.** `embed_texts()` accepts lists; batching is far faster than one call per chunk.

---

## 4. Storage

```python
from nexus import pgvector_ddl

print(pgvector_ddl(384))
```

`pgvector_ddl(dim)` creates `knowledge_documents` and `knowledge_chunks` with a `vector(dim)` column (`halfvec` above 2000 dimensions), an HNSW cosine index, and a generated `tsvector` column with a GIN index for the lexical half of hybrid search. `mysql_ddl(dim)` and `mongo_atlas_vector_index(dim)` provide the MySQL 9 and MongoDB Atlas equivalents.

---

## 5. End-to-End Example

```python
import nexus

client = nexus.NexusClient(in_memory_only=True)
doc = client.process_document(name="budget.csv", text=csv_text, file_type="csv")

texts = [c.text for c in doc.chunks]
vectors = client.embed_texts(texts)                      # store alongside texts
query_vector = client.embed_query("What was the engineering budget?")
scores = client.rerank("What was the engineering budget?", texts)
```
