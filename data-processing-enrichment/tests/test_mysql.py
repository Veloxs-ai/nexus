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

from nexus_processing.mysql import (
    MYSQL_DDL_SCHEMA,
    chunk_mysql_table,
    normalize_mysql_cdc_event,
    serialize_mysql_row,
)


def test_serialize_mysql_row_auto_pk():
    row = {
        "id": 101,
        "name": "Acme Corp",
        "balance": 1500.75,
        "active": True,
        "notes": "Premium\r\nclient",
    }
    narrative = serialize_mysql_row(row, table_name="customers")
    assert narrative.startswith("[Table: customers | PK: 101]")
    assert "name: Acme Corp" in narrative
    assert "balance: 1500.75" in narrative
    assert "active: True" in narrative
    assert "notes: Premium client" in narrative


def test_serialize_mysql_row_custom_pk():
    row = {"customer_code": "CUST_99", "tier": "Enterprise", "manager": None}
    narrative = serialize_mysql_row(row, table_name="accounts", primary_key="customer_code")
    assert narrative.startswith("[Table: accounts | PK: CUST_99]")
    assert "tier: Enterprise" in narrative
    assert "manager: NULL" in narrative


def test_chunk_mysql_table_single_and_batch():
    rows = [
        {"id": 1, "action": "login"},
        {"id": 2, "action": "view_dashboard"},
        {"id": 3, "action": "logout"},
    ]

    # Single row per chunk
    single_chunks = chunk_mysql_table(rows, table_name="audit_logs", rows_per_chunk=1)
    assert len(single_chunks) == 3
    assert "PK: 1]" in single_chunks[0]
    assert "PK: 2]" in single_chunks[1]
    assert "PK: 3]" in single_chunks[2]

    # Batched rows per chunk
    batched_chunks = chunk_mysql_table(rows, table_name="audit_logs", rows_per_chunk=2)
    assert len(batched_chunks) == 2
    assert "PK: 1]" in batched_chunks[0] and "PK: 2]" in batched_chunks[0]
    assert "PK: 3]" in batched_chunks[1]

    # Empty rows
    assert chunk_mysql_table([], table_name="audit_logs") == []


def test_normalize_mysql_cdc_event_insert():
    debezium_event = {
        "payload": {
            "op": "c",
            "ts_ms": 1726765200000,
            "source": {"db": "production", "table": "orders"},
            "after": {"order_id": 5001, "amount": 299.99},
            "before": None,
        }
    }
    normalized = normalize_mysql_cdc_event(debezium_event)
    assert normalized["operation"] == "INSERT"
    assert normalized["database"] == "production"
    assert normalized["table"] == "orders"
    assert normalized["record"]["order_id"] == 5001
    assert normalized["timestamp_ms"] == 1726765200000


def test_normalize_mysql_cdc_event_update_and_delete():
    update_event = {
        "payload": {
            "op": "u",
            "source": {"db": "app_db", "table": "users"},
            "before": {"id": 42, "email": "old@example.com"},
            "after": {"id": 42, "email": "new@example.com"},
        }
    }
    norm_update = normalize_mysql_cdc_event(update_event)
    assert norm_update["operation"] == "UPDATE"
    assert norm_update["record"]["email"] == "new@example.com"
    assert norm_update["before"]["email"] == "old@example.com"

    delete_event = {
        "payload": {
            "op": "d",
            "source": {"db": "app_db", "table": "users"},
            "before": {"id": 42, "email": "new@example.com"},
            "after": None,
        }
    }
    norm_delete = normalize_mysql_cdc_event(delete_event)
    assert norm_delete["operation"] == "DELETE"
    assert norm_delete["record"]["id"] == 42


def test_mysql_ddl_schema():
    assert "CREATE TABLE IF NOT EXISTS knowledge_documents" in MYSQL_DDL_SCHEMA
    assert "CREATE TABLE IF NOT EXISTS knowledge_chunks" in MYSQL_DDL_SCHEMA
    assert "ENGINE=InnoDB" in MYSQL_DDL_SCHEMA
