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

import sqlite3

import pytest

from nexus_processing.sqlite import (
    process_sqlite_binary,
    process_sqlite_file,
)


def make_test_sqlite_bytes() -> bytes:
    """Creates an in-memory SQLite database with tables, FKs, and views, and serializes to bytes."""
    con = sqlite3.connect(":memory:")
    con.execute("""
    CREATE TABLE categories (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL
    );
    """)
    con.execute("""
    CREATE TABLE products (
        id INTEGER PRIMARY KEY,
        title TEXT NOT NULL,
        price REAL NOT NULL,
        category_id INTEGER,
        FOREIGN KEY (category_id) REFERENCES categories(id)
    );
    """)
    con.execute("""
    CREATE VIEW active_catalog AS
    SELECT p.id, p.title, p.price, c.name as category
    FROM products p JOIN categories c ON p.category_id = c.id;
    """)
    con.execute("INSERT INTO categories VALUES (1, 'Hardware');")
    con.execute("INSERT INTO categories VALUES (2, 'Software');")
    con.execute("INSERT INTO products VALUES (101, 'Nexus Server Node', 4999.99, 1);")
    con.execute("INSERT INTO products VALUES (102, 'Vector Engine License', 1200.00, 2);")
    con.commit()

    serialized = con.serialize()
    con.close()
    return serialized


def test_sqlite_validation():
    """Validates error handling for empty or malformed SQLite payloads."""
    with pytest.raises(ValueError, match="Cannot process empty SQLite database bytes"):
        process_sqlite_binary(b"")

    with pytest.raises(ValueError, match="SQLite binary payload is too small"):
        process_sqlite_binary(b"SHORT")

    with pytest.raises(ValueError, match="missing 'SQLite format 3"):
        process_sqlite_binary(b"X" * 128)


def test_sqlite_binary_introspection():
    """Validates in-memory SQLite schema discovery, foreign keys, views, and row chunks."""
    raw = make_test_sqlite_bytes()
    payload = process_sqlite_binary(raw, db_name="catalog.db")

    assert payload.metadata.format == "sqlite"
    assert payload.metadata.db_name == "catalog.db"
    assert payload.metadata.total_tables == 2
    assert payload.metadata.total_views == 1
    assert payload.metadata.total_rows == 4  # 2 in categories + 2 in products

    # Verify tables
    table_map = {t.name: t for t in payload.tables}
    assert "categories" in table_map
    assert "products" in table_map
    assert "active_catalog" in table_map

    prod_t = table_map["products"]
    assert prod_t.primary_keys == ["id"]
    assert len(prod_t.foreign_keys) == 1
    assert prod_t.foreign_keys[0].target_table == "categories"
    assert prod_t.foreign_keys[0].from_column == "category_id"

    # Verify chunks: schemas + rows
    schema_chunks = [c for c in payload.all_chunks if c.is_schema]
    row_chunks = [c for c in payload.all_chunks if not c.is_schema]

    assert len(schema_chunks) == 3  # 2 tables + 1 view DDL
    assert len(row_chunks) == 4

    p_chunk = next(c for c in row_chunks if c.table_name == "products" and c.row_pk == "101")
    assert "[SQLite: catalog.db | Table: products | Row PK: 101]" in p_chunk.narrative_text
    assert "title: Nexus Server Node" in p_chunk.narrative_text
    assert "price: 4999.99" in p_chunk.narrative_text


def test_sqlite_file_introspection(tmp_path):
    """Validates SQLite file reading and introspection directly from disk."""
    raw = make_test_sqlite_bytes()
    db_file = tmp_path / "test.db"
    db_file.write_bytes(raw)

    payload = process_sqlite_file(db_file)
    assert payload.metadata.db_name == "test.db"
    assert payload.metadata.total_tables == 2
    assert len(payload.tables) == 3
