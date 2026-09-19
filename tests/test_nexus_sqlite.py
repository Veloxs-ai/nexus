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

import math
import sqlite3

from nexus.client import NexusClient


def make_test_sqlite_bytes() -> bytes:
    """Generates an SQLite binary payload with PII in row data."""
    con = sqlite3.connect(":memory:")
    con.execute("""
    CREATE TABLE customers (
        id INTEGER PRIMARY KEY,
        full_name TEXT NOT NULL,
        contact_email TEXT
    );
    """)
    con.execute("INSERT INTO customers VALUES (1, 'Alice Smith', 'alice.smith@example.com');")
    con.commit()
    raw = con.serialize()
    con.close()
    return raw


def test_nexus_client_process_sqlite():
    """Validates NexusClient.process_sqlite execution traces and 3072D vector projections."""
    client = NexusClient()
    raw = make_test_sqlite_bytes()

    doc = client.process_sqlite(
        db_id="doc_sqlite_1",
        name="crm.db",
        db_bytes=raw,
        metadata={"environment": "staging"},
        enable_guardrails=True,
    )

    assert doc.document_id == "doc_sqlite_1"
    assert doc.file_type == "sqlite"
    assert doc.metadata["total_tables"] == 1
    assert doc.metadata["environment"] == "staging"

    # 5-stage trace validation
    assert len(doc.execution_trace) == 5
    stage_names = [t.stage_name for t in doc.execution_trace]
    assert stage_names == [
        "SQLite Binary Validation & Schema Introspection",
        "Table Graph & Foreign Key Relationship Discovery",
        "Tabular Row Extraction & Record Framing",
        "Safety Guardrails & PII Sanitization",
        "Relational-Grounded 3072D Vector Projection",
    ]
    for t in doc.execution_trace:
        assert t.status == "completed"
        assert t.duration_ms >= 0.0

    # Chunks validation: 1 schema DDL + 1 row
    assert len(doc.chunks) == 2
    schema_chunk = next(c for c in doc.chunks if c.metadata["is_schema"])
    row_chunk = next(c for c in doc.chunks if not c.metadata["is_schema"])

    assert "[SQLite: crm.db | Schema DDL | Table: customers]" in schema_chunk.text
    assert "[SQLite: crm.db | Table: customers | Row PK: 1]" in row_chunk.text

    # PII sanitization in row chunk
    assert "alice.smith@example.com" not in row_chunk.text
    assert "[EMAIL]" in row_chunk.text

    # 3072D vector norm verification
    assert len(row_chunk.embedding) == 3072
    l2_norm = math.sqrt(sum(x * x for x in row_chunk.embedding))
    assert math.isclose(l2_norm, 1.0, rel_tol=1e-5)


def test_nexus_client_process_document_sqlite_routing(tmp_path):
    """Validates auto-routing in NexusClient.process_document for SQLite binaries and files."""
    client = NexusClient()
    raw = make_test_sqlite_bytes()

    # Route via raw bytes with magic header
    doc_bytes = client.process_document(
        document_id="auto_sqlite_bytes",
        text=raw,
        name="sales.db",
    )
    assert doc_bytes.file_type == "sqlite"
    assert doc_bytes.metadata["total_tables"] == 1

    # Route via file path string
    db_file = tmp_path / "orders.sqlite3"
    db_file.write_bytes(raw)

    doc_file = client.process_document(
        document_id="auto_sqlite_file",
        name="orders.sqlite3",
        text=str(db_file),
    )
    assert doc_file.file_type == "sqlite"
    assert doc_file.metadata["total_tables"] == 1
