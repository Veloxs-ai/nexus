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

from typing import Any


def get_pgvector_column_type(dimensions: int = 3072) -> Any:
    """Returns the native pgvector SQLAlchemy Column type.

    Raises an explicit, actionable ImportError if pgvector is missing,
    rather than silently falling back to a string descriptor.
    """
    try:
        from pgvector.sqlalchemy import Vector

        return Vector(dimensions)
    except ImportError as exc:
        raise ImportError(
            f"The 'pgvector' package is required to compile a native vector({dimensions}) column. "
            "Install it with: pip install nexus-enterprise-ai[postgres] or pip install pgvector"
        ) from exc


PGVECTOR_DDL_SCHEMA = """
-- PostgreSQL + pgvector 3072D Document & Embedding Schema
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS knowledge_documents (
    document_id         VARCHAR(128) PRIMARY KEY,
    name                VARCHAR(255) NOT NULL,
    file_type           VARCHAR(32) NOT NULL,
    file_size_bytes     BIGINT NOT NULL,
    content_hash        VARCHAR(64) NOT NULL,
    classification      VARCHAR(64) DEFAULT 'general',
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    chunk_id            VARCHAR(128) PRIMARY KEY,
    document_id         VARCHAR(128) NOT NULL REFERENCES knowledge_documents(document_id) ON DELETE CASCADE,
    source_job          VARCHAR(64) NOT NULL,
    chunk_index         INTEGER NOT NULL,
    chunk_text          TEXT NOT NULL,
    metadata            JSONB DEFAULT '{}'::jsonb,
    embedding           VECTOR(3072) NOT NULL,
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_embedding_hnsw 
ON knowledge_chunks 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_doc_id ON knowledge_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_metadata ON knowledge_chunks USING gin(metadata);
"""
