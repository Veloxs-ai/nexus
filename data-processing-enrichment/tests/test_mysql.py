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

from nexus_processing.cdc import normalize_change_event
from nexus_processing.mysql import (
    chunk_mysql_table,
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


def test_debezium_mysql_insert():
    debezium_event = {
        "payload": {
            "op": "c",
            "ts_ms": 1726765200000,
            "source": {"db": "production", "table": "orders"},
            "after": {"order_id": 5001, "amount": 299.99},
            "before": None,
        }
    }
    ev = normalize_change_event(debezium_event)
    assert ev.operation == "INSERT" and ev.source_format == "debezium"
    assert ev.database == "production" and ev.table == "orders"
    assert ev.record["order_id"] == 5001
    assert ev.timestamp_ms == 1726765200000


def test_debezium_mysql_update_and_delete():
    update_event = {
        "payload": {
            "op": "u",
            "source": {"db": "app_db", "table": "users"},
            "before": {"id": 42, "email": "old@example.com"},
            "after": {"id": 42, "email": "new@example.com"},
        }
    }
    ev_update = normalize_change_event(update_event)
    assert ev_update.operation == "UPDATE"
    assert ev_update.record["email"] == "new@example.com" and ev_update.key == "42"

    delete_event = {
        "payload": {
            "op": "d",
            "source": {"db": "app_db", "table": "users"},
            "before": {"id": 42, "email": "new@example.com"},
            "after": None,
        }
    }
    ev_delete = normalize_change_event(delete_event)
    assert ev_delete.operation == "DELETE" and ev_delete.is_delete
    assert ev_delete.record["id"] == 42
