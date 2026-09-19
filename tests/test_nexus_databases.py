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

import json
import math

from nexus import (
    MONGO_ATLAS_VECTOR_SEARCH_INDEX,
    MYSQL_DDL_SCHEMA,
    NexusClient,
)


def test_nexus_client_process_mysql_table():
    client = NexusClient(in_memory_only=True)

    rows = [
        {
            "id": 101,
            "username": "alice_dev",
            "email": "alice@corporate.com",
            "department": "Infrastructure",
            "credit_card": "4111-1111-1111-1111",
            "salary": 145000.0,
        },
        {
            "id": 102,
            "username": "bob_ops",
            "email": "bob@security.internal",
            "department": "Platform Reliability",
            "credit_card": None,
            "salary": 160000.0,
        },
    ]

    doc = client.process_mysql_table(
        table_name="employees",
        rows=rows,
        primary_key="id",
        metadata={"environment": "production"},
        enable_guardrails=True,
    )

    assert doc.document_id == "mysql:employees"
    assert doc.name == "mysql_employees"
    assert doc.file_type == "mysql"
    assert doc.classification == "database"
    assert len(doc.chunks) == 2

    # Check Chunk 0 PII masking and structure
    chunk_0 = doc.chunks[0]
    assert chunk_0.chunk_id == "mysql:employees:0"
    assert "[Table: employees | PK: 101]" in chunk_0.text
    assert "username: alice_dev" in chunk_0.text
    assert "[EMAIL]" in chunk_0.text
    assert "[CREDIT_CARD]" in chunk_0.text
    assert "4111-1111-1111-1111" not in chunk_0.text
    assert chunk_0.metadata["source_table"] == "employees"
    assert chunk_0.metadata["primary_key"] == "id"
    assert chunk_0.metadata["is_database"] is True
    assert chunk_0.metadata["database_type"] == "mysql"
    assert chunk_0.metadata["environment"] == "production"

    # Check 3072D vector normalization
    assert len(chunk_0.embedding) == 3072
    norm = math.sqrt(sum(x * x for x in chunk_0.embedding))
    assert abs(norm - 1.0) < 1e-7

    # Check 5-stage telemetry trace
    assert len(doc.execution_trace) == 5
    for idx, trace in enumerate(doc.execution_trace, start=1):
        assert trace.step_number == idx
        assert trace.status == "completed"
        assert trace.duration_ms >= 0.0

    assert doc.execution_trace[0].stage_name == "MySQL Schema & Primary Key Analysis"
    assert doc.execution_trace[1].stage_name == "Relational Row Serialization & Typing"
    assert doc.execution_trace[2].stage_name == "Format-Aware Tabular Chunking"
    assert doc.execution_trace[3].stage_name == "Safety Guardrails & PII Sanitization"
    assert doc.execution_trace[4].stage_name == "3072D Multi-Gram Vector Projection"

    # Verify indexing and retrieval
    client.index_document(doc, collection="database_records")
    results = client.search("Platform Reliability engineer bob_ops", limit=5)
    assert len(results) >= 1
    assert any("mysql:employees:1" in r.id for r in results)


def test_nexus_client_process_mongo_collection():
    client = NexusClient(in_memory_only=True)

    documents = [
        {
            "_id": {"$oid": "60a8b9f1e1f3a245d8b45678"},
            "customer": {
                "name": "Sarah Connor",
                "email": "sarah@cyberdyne.io",
                "address": {
                    "city": "Los Angeles",
                    "state": "CA",
                    "postal": "90001",
                },
            },
            "orders": [
                {"order_id": "ORD-101", "total": {"$numberDecimal": "499.50"}},
            ],
            "created_at": {"$date": "2026-09-19T12:00:00Z"},
            "active": True,
        },
        {
            "_id": {"$oid": "60a8b9f1e1f3a245d8b45679"},
            "customer": {
                "name": "John Connor",
                "email": "john@cyberdyne.io",
                "address": {
                    "city": "San Francisco",
                    "state": "CA",
                    "postal": "94105",
                },
            },
            "orders": [],
            "created_at": {"$date": "2026-09-19T13:00:00Z"},
            "active": False,
        },
    ]

    doc = client.process_mongo_collection(
        collection_name="customers",
        documents=documents,
        flatten_nested=True,
        metadata={"system": "crm"},
        enable_guardrails=True,
    )

    assert doc.document_id == "mongodb:customers"
    assert doc.name == "mongodb_customers"
    assert doc.file_type == "mongodb"
    assert len(doc.chunks) == 2

    # Check Chunk 0 dot-notation flattening and PII masking
    chunk_0 = doc.chunks[0]
    assert chunk_0.chunk_id == "mongodb:customers:0"
    assert "[Collection: customers | ID: 60a8b9f1e1f3a245d8b45678]" in chunk_0.text
    assert "customer.name: Sarah Connor" in chunk_0.text
    assert "customer.address.city: Los Angeles" in chunk_0.text
    assert "[EMAIL]" in chunk_0.text
    assert chunk_0.metadata["collection_name"] == "customers"
    assert chunk_0.metadata["is_database"] is True
    assert chunk_0.metadata["database_type"] == "mongodb"
    assert chunk_0.metadata["system"] == "crm"

    # Check 3072D vector normalization
    assert len(chunk_0.embedding) == 3072
    norm = math.sqrt(sum(x * x for x in chunk_0.embedding))
    assert abs(norm - 1.0) < 1e-7

    # Check 5-stage telemetry trace
    assert len(doc.execution_trace) == 5
    for idx, trace in enumerate(doc.execution_trace, start=1):
        assert trace.step_number == idx
        assert trace.status == "completed"
        assert trace.duration_ms >= 0.0

    assert doc.execution_trace[0].stage_name == "MongoDB BSON / Extended-JSON Normalization"
    assert doc.execution_trace[1].stage_name == "Hierarchical Keypath Flattening (Dot-Notation)"
    assert doc.execution_trace[2].stage_name == "Document Record Serialization & Chunking"
    assert doc.execution_trace[3].stage_name == "Safety Guardrails & PII Sanitization"
    assert doc.execution_trace[4].stage_name == "3072D Multi-Gram Vector Projection"

    # Verify indexing and retrieval
    client.index_document(doc, collection="mongodb_crm")
    results = client.search("San Francisco customer John Connor", limit=5)
    assert len(results) >= 1
    assert any("mongodb:customers:1" in r.id for r in results)


def test_nexus_client_process_document_db_routing():
    client = NexusClient(in_memory_only=True)

    # Test MySQL routing via process_document
    mysql_rows = [
        {"id": 50, "service": "auth_api", "status": "healthy"},
        {"id": 51, "service": "payment_gateway", "status": "degraded"},
    ]
    mysql_doc = client.process_document(
        document_id="mysql_routing_test",
        name="services_table",
        text=json.dumps(mysql_rows),
        file_type="mysql",
    )
    assert mysql_doc.document_id == "mysql:services_table"
    assert mysql_doc.file_type == "mysql"
    assert len(mysql_doc.chunks) == 2
    assert "[Table: services_table | PK: 50]" in mysql_doc.chunks[0].text

    # Test MongoDB routing via process_document
    mongo_docs = [
        {"_id": "cfg_01", "setting": "max_connections", "val": 1000},
    ]
    mongo_doc = client.process_document(
        document_id="mongo_routing_test",
        name="system_configs",
        text=json.dumps(mongo_docs),
        file_type="mongodb",
    )
    assert mongo_doc.document_id == "mongodb:system_configs"
    assert mongo_doc.file_type == "mongodb"
    assert len(mongo_doc.chunks) == 1
    assert "[Collection: system_configs | ID: cfg_01]" in mongo_doc.chunks[0].text


def test_database_schemas_and_indexes():
    assert "CREATE TABLE IF NOT EXISTS knowledge_documents" in MYSQL_DDL_SCHEMA
    assert "CREATE TABLE IF NOT EXISTS knowledge_chunks" in MYSQL_DDL_SCHEMA
    assert "fields" in MONGO_ATLAS_VECTOR_SEARCH_INDEX
    dims = next(
        f["numDimensions"]
        for f in MONGO_ATLAS_VECTOR_SEARCH_INDEX["fields"]
        if f.get("type") == "vector"
    )
    assert dims == 3072
