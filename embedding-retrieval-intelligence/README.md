# Embedding & Retrieval Intelligence Layer

Transforms processed enterprise data into semantic representations and enables intelligent retrieval through vector search, knowledge graph relationships, hybrid search, and ranking.

This layer forms a unified knowledge layer for AI systems by combining:

- **Vector Database**: Stores high-dimensional embeddings for semantic similarity search.
- **Knowledge Graph**: Models relationships between records, entities, tags, documents, and chunks.
- **Hybrid Search**: Combines lexical keyword matching with semantic embedding search.
- **Ranking & Re-ranking**: Scores and reorders results to return the most contextually relevant answers.

## Current Status

This project is runnable locally and includes:

- deterministic local embedding generation
- file-backed vector index
- file-backed knowledge graph index
- lexical inverted index
- hybrid search and ranking
- config-driven indexing from processed JSONL outputs
- CLI commands
- tests

The implementation intentionally avoids external vector database and graph database dependencies for local development. Production adapters can later replace the file-backed stores with services such as pgvector, OpenSearch, Pinecone, Weaviate, Neo4j, Neptune, or a platform-native retrieval service.

## Project Layout

```text
embedding-retrieval-intelligence/
  configs/
    retrieval.yaml
  data/
    indexes/
      .gitkeep
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
  tests/
    conftest.py
    test_cli.py
    test_config.py
    test_embeddings.py
    test_graph.py
    test_hybrid.py
    test_indexing.py
    test_lexical.py
    test_ranking.py
    test_vector_store.py
  pyproject.toml
```

## Prerequisites

Install:

- Python 3.11 or newer
- `pip`

Check your Python version:

```bash
python3 --version
```

## Setup

From the repository root:

```bash
cd path/to/nexus/embedding-retrieval-intelligence
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Confirm the CLI is available:

```bash
retrieval --help
```

If you do not install the package, run commands with:

```bash
PYTHONPATH=src python -m nexus_retrieval.cli --help
```

## Configuration

Retrieval indexes are configured in [configs/retrieval.yaml](configs/retrieval.yaml).

The config includes:

- `integration`: loose references to upstream layers
- `embedding`: embedding provider and dimensions
- `stores`: local index file locations
- `ranking`: hybrid scoring weights
- `collections`: processed JSONL inputs to index

Example:

```yaml
integration:
  processing_project: ../data-processing-enrichment
  processing_config: ../data-processing-enrichment/configs/processing.yaml
  ingestion_project: ../enterprise-data-pipeline

collections:
  policy_documents:
    input_uri: ../data-processing-enrichment/data/processed/policy_documents.chunks.jsonl
    id_field: chunk_id
    text_field: text
    metadata_field: metadata
    graph:
      entity_fields:
        - metadata.entities
      tag_fields:
        - metadata.tags
      parent_field: document_id
```

This project does not import code from `data-processing-enrichment` or `enterprise-data-pipeline`. It integrates through JSONL outputs and config references.

## Upstream Contract

This layer expects processed JSONL records from the Data Processing & Enrichment layer.

Supported shapes:

Processed record:

```json
{"record_id":"c001","source_job":"customer_profiles","payload":{"name":"Acme"},"metadata":{"tags":["customer"]}}
```

Document chunk:

```json
{"chunk_id":"doc-001:0","document_id":"doc-001","source_job":"policy_documents","text":"All employees must use MFA.","metadata":{"tags":["security"],"entities":["Security Policy"]}}
```

## Validate Config

```bash
retrieval validate-config configs/retrieval.yaml
```

Expected output:

```text
Loaded 2 retrieval collections.
```

Without package installation:

```bash
PYTHONPATH=src python -m nexus_retrieval.cli validate-config configs/retrieval.yaml
```

## Build Indexes

```bash
retrieval build-index configs/retrieval.yaml
```

This command:

- reads configured processed JSONL files
- creates deterministic embeddings
- writes a vector index
- writes a lexical index
- writes a graph index

Default outputs:

```text
data/indexes/vector_index.json
data/indexes/lexical_index.json
data/indexes/graph_index.json
```

Without package installation:

```bash
PYTHONPATH=src python -m nexus_retrieval.cli build-index configs/retrieval.yaml
```

## Search

Run a hybrid semantic plus lexical search:

```bash
retrieval search configs/retrieval.yaml "MFA access security policy"
```

Without package installation:

```bash
PYTHONPATH=src python -m nexus_retrieval.cli search configs/retrieval.yaml "MFA access security policy"
```

Optional result count:

```bash
retrieval search configs/retrieval.yaml "customer renewal support" --limit 3
```

## Run Tests

Run all tests:

```bash
python -m pytest
```

Run one test file:

```bash
python -m pytest tests/test_hybrid.py
```

Run with verbose output:

```bash
python -m pytest -v
```

Expected result:

```text
16 passed
```

## Integration Flow

The intended architecture flow is:

1. `enterprise-data-pipeline` ingests raw data.
2. `data-processing-enrichment` cleans, standardizes, chunks, and enriches that data.
3. `embedding-retrieval-intelligence` indexes enriched records and chunks.
4. AI systems query the retrieval layer for semantically and contextually relevant information.

The layers are loosely coupled through data files and config:

- ingestion output feeds processing input
- processing output feeds retrieval input
- retrieval indexes are independently rebuildable

## Production Next Steps

1. Add an embedding provider interface for OpenAI, local models, or platform embedding services.
2. Add adapters for pgvector, OpenSearch, Pinecone, Weaviate, or another vector database.
3. Add a graph database adapter for Neo4j, Neptune, or a platform graph service.
4. Add cross-encoder or LLM-based reranking.
5. Add access-control filters and tenant isolation.
6. Add index versioning, incremental indexing, and deletion propagation.
