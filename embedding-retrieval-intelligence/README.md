# Embedding & Retrieval Intelligence Layer

> Part of **[Nexus — Enterprise Intelligence Framework](../README.md)**, the open-source framework for secure, governed AI applications.
> This layer provides the **Knowledge & Retrieval** capability.


Transforms processed enterprise data into high-dimensional semantic vector representations and enables intelligent retrieval through semantic vector similarity search, cross-encoder re-ranking, knowledge graph relationships, and hybrid Reciprocal Rank Fusion (RRF).

---

## 🛠️ Capabilities

- **Semantic Embeddings** (`semantic.py`): FastEmbed `BAAI/bge-small-en-v1.5` (384D, local ONNX) or OpenAI; asymmetric `embed_query` / `embed_documents`; configured by `EmbeddingConfig(provider, model, dimensions)`.
- **Cross-Encoder Re-ranking**: `create_reranker()` scores (query, passage) pairs in (0, 1).
- **Knowledge Graph Indexing**: Models relationships between documents, entities, categories, and tags.
- **Lexical Inverted Indexing**: Inverted term index for high-precision exact keyword search.
- **Hybrid Retrieval (RRF)**: Combines semantic vector similarity, lexical scoring, and graph traversal.

---

## 📂 Project Layout

```text
embedding-retrieval-intelligence/
  configs/
    retrieval.json
  data/
    indexes/
  docs/
    architecture.md
  src/nexus_retrieval/
    cli.py
    config.py
    embeddings.py
    graph.py
    hybrid.py
    indexing.py
    io.py
    lexical.py
    models.py
    ranking.py
    vector_store.py
  pyproject.toml
```
