# Copyright 2026 Veloxs AI Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Reference storage schemas for Nexus chunks (PostgreSQL/pgvector, MySQL, MongoDB Atlas).

All builders take the embedding dimension of the configured model, e.g.
``NexusClient().embedding_info()["dimensions"]`` (384 for bge-small, 1536/3072 for
OpenAI text-embedding-3-*). pgvector's HNSW index supports up to 2000 dimensions for
``vector``; larger models are stored as ``halfvec`` automatically.
"""

from typing import Any


def get_pgvector_column_type(dimensions: int) -> Any:
    """Native pgvector SQLAlchemy column type (``vector`` <= 2000 dims, else ``halfvec``)."""
    try:
        if dimensions <= 2000:
            from pgvector.sqlalchemy import Vector

            return Vector(dimensions)
        from pgvector.sqlalchemy import HALFVEC

        return HALFVEC(dimensions)
    except ImportError as exc:
        raise ImportError(
            f"The 'pgvector' package is required for a vector({dimensions}) column. "
            "Install it with: pip install 'veloxs-nexus[postgres]'"
        ) from exc


def pgvector_ddl(dimensions: int) -> str:
    """PostgreSQL DDL: documents + chunks with HNSW vector index and full-text search."""
    vec = f"vector({dimensions})" if dimensions <= 2000 else f"halfvec({dimensions})"
    ops = "vector_cosine_ops" if dimensions <= 2000 else "halfvec_cosine_ops"
    return f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS knowledge_documents (
    document_id         VARCHAR(128) PRIMARY KEY,
    name                VARCHAR(255) NOT NULL,
    file_type           VARCHAR(32) NOT NULL,
    file_size_bytes     BIGINT NOT NULL,
    content_hash        VARCHAR(64) NOT NULL,
    classification      VARCHAR(64) DEFAULT 'general',
    embedding_model     VARCHAR(128),
    created_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    chunk_id            VARCHAR(128) PRIMARY KEY,
    document_id         VARCHAR(128) NOT NULL REFERENCES knowledge_documents(document_id) ON DELETE CASCADE,
    chunk_index         INTEGER NOT NULL,
    chunk_text          TEXT NOT NULL,
    metadata            JSONB DEFAULT '{{}}'::jsonb,
    embedding           {vec},
    embedding_model     VARCHAR(128),
    text_search         TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', coalesce(chunk_text, ''))) STORED,
    created_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_embedding_hnsw
    ON knowledge_chunks USING hnsw (embedding {ops}) WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_text_search ON knowledge_chunks USING gin (text_search);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_doc ON knowledge_chunks (document_id, chunk_index);
"""


def mysql_ddl(dimensions: int) -> str:
    """MySQL 8 DDL (vectors stored as JSON arrays; use an external ANN index for search)."""
    return f"""
CREATE TABLE IF NOT EXISTS knowledge_documents (
    document_id         VARCHAR(128) NOT NULL PRIMARY KEY,
    name                VARCHAR(255) NOT NULL,
    file_type           VARCHAR(32) NOT NULL,
    file_size_bytes     BIGINT NOT NULL,
    content_hash        VARCHAR(64) NOT NULL,
    classification      VARCHAR(64) DEFAULT 'database',
    embedding_model     VARCHAR(128) NULL,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_doc_hash (content_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    chunk_id            VARCHAR(128) NOT NULL PRIMARY KEY,
    document_id         VARCHAR(128) NOT NULL,
    source_table        VARCHAR(128) NOT NULL,
    chunk_index         INT NOT NULL,
    chunk_text          TEXT NOT NULL,
    metadata            JSON NULL,
    embedding           JSON NULL COMMENT '{dimensions}-dim float array',
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES knowledge_documents(document_id) ON DELETE CASCADE,
    INDEX idx_chunks_doc (document_id),
    INDEX idx_chunks_table (source_table),
    FULLTEXT INDEX ft_chunks_text (chunk_text)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""


def mongo_atlas_vector_index(dimensions: int) -> dict[str, Any]:
    """MongoDB Atlas Vector Search index definition for chunk documents."""
    return {
        "fields": [
            {"type": "vector", "path": "embedding", "numDimensions": dimensions, "similarity": "cosine"},
            {"type": "filter", "path": "collection_name"},
            {"type": "filter", "path": "document_id"},
        ]
    }
