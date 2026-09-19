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

"""Zero-dependency MySQL relational table processor, CDC normalizer, and DDL generator.

Transforms relational database rows into rich, table-grounded semantic narratives,
normalizes Debezium/Maxwell binlog events, and defines production MySQL 8.0+ schemas.
"""

from __future__ import annotations

from typing import Any

MYSQL_DDL_SCHEMA = """
-- MySQL 8.0+ Knowledge Documents & Vector Storage Schema
CREATE TABLE IF NOT EXISTS knowledge_documents (
    document_id         VARCHAR(128) NOT NULL PRIMARY KEY,
    name                VARCHAR(255) NOT NULL,
    file_type           VARCHAR(32) NOT NULL,
    file_size_bytes     BIGINT NOT NULL,
    content_hash        VARCHAR(64) NOT NULL,
    classification      VARCHAR(64) DEFAULT 'database',
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
    embedding           JSON NOT NULL COMMENT '3072D IEEE 754 float array',
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES knowledge_documents(document_id) ON DELETE CASCADE,
    INDEX idx_chunks_doc (document_id),
    INDEX idx_chunks_table (source_table)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""


def serialize_mysql_row(
    row: dict[str, Any], table_name: str, primary_key: str | None = None
) -> str:
    """Transforms a single relational table row into a structured, contextual narrative."""
    # Determine primary key value
    pk_val = None
    if primary_key and primary_key in row:
        pk_val = row[primary_key]
    elif "id" in row:
        pk_val = row["id"]
    elif "_id" in row:
        pk_val = row["_id"]

    if pk_val is not None:
        pk_header = f"[Table: {table_name} | PK: {pk_val}] "
    else:
        pk_header = f"[Table: {table_name}] "

    items: list[str] = []
    for col, val in row.items():
        if val is None:
            items.append(f"{col}: NULL")
        elif isinstance(val, int | float | bool):
            items.append(f"{col}: {val}")
        else:
            clean_str = str(val).replace("\r\n", " ").replace("\n", " ").strip()
            items.append(f"{col}: {clean_str}")

    return pk_header + " | ".join(items)


def chunk_mysql_table(
    rows: list[dict[str, Any]],
    table_name: str,
    primary_key: str | None = None,
    rows_per_chunk: int = 1,
) -> list[str]:
    """Chunks a list of relational table rows into individual or batched narrative chunks."""
    if not rows:
        return []

    r_size = max(1, rows_per_chunk)
    chunks: list[str] = []

    if r_size == 1:
        for row in rows:
            chunks.append(serialize_mysql_row(row, table_name=table_name, primary_key=primary_key))
    else:
        for i in range(0, len(rows), r_size):
            batch = rows[i : i + r_size]
            batch_narratives = [
                serialize_mysql_row(r, table_name=table_name, primary_key=primary_key)
                for r in batch
            ]
            chunks.append("\n".join(batch_narratives))

    return chunks


def normalize_mysql_cdc_event(event: dict[str, Any]) -> dict[str, Any]:
    """Normalizes MySQL Debezium or Maxwell binlog Change Data Capture event messages."""
    payload = event.get("payload", event)
    op_code = payload.get("op", payload.get("type", "r")).lower()

    op_map = {
        "c": "INSERT",
        "insert": "INSERT",
        "u": "UPDATE",
        "update": "UPDATE",
        "d": "DELETE",
        "delete": "DELETE",
        "r": "READ",
        "read": "READ",
    }
    operation = op_map.get(op_code, "UNKNOWN")

    before_state = payload.get("before")
    after_state = payload.get("after", payload.get("data"))

    record = after_state if operation != "DELETE" else before_state
    source_info = payload.get("source", {})
    table_name = source_info.get("table", event.get("table", "unknown_table"))
    db_name = source_info.get("db", event.get("database", "unknown_db"))

    return {
        "operation": operation,
        "database": db_name,
        "table": table_name,
        "record": record or {},
        "before": before_state,
        "after": after_state,
        "timestamp_ms": payload.get("ts_ms", source_info.get("ts_ms", 0)),
    }
