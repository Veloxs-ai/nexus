# Embedding & Retrieval Intelligence Layer

> Part of **[Nexus — Enterprise Intelligence Framework](../README.md)**, the open-source framework for secure, governed AI applications.
> This layer provides the **Knowledge & Retrieval** capability.


Transforms processed enterprise data into high-dimensional semantic vector representations and enables intelligent retrieval through 3072D vector similarity search, knowledge graph relationships, and hybrid Reciprocal Rank Fusion (RRF).

---

## 🛠️ Capabilities

- **3072-Dimensional Multi-Gram Vector Projection**:
  - **Unigram Projection (1.5x)**: Base vocabulary tokens.
  - **Bigram Projection (2.0x)**: Preserves multi-word phrase semantics (e.g. `"cloud infrastructure"`).
  - **Trigram Projection (2.5x)**: Preserves compound entity relationships.
  - **L2 Unit Normalization**: Enforces $\|\hat{V}\|_2 = 1.0$ for exact Cosine Similarity.
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
