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

"""Zero-dependency Embedded SQLite database processor."""

from __future__ import annotations

import sqlite3
import struct
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "ColumnSchema",
    "ForeignKeyInfo",
    "SQLiteMetadata",
    "SQLitePayload",
    "SQLiteRowChunk",
    "TableSchema",
    "process_sqlite_binary",
    "process_sqlite_file",
]

SQLITE_HEADER_MAGIC = b"SQLite format 3\x00"


@dataclass
class ColumnSchema:
    """Introspected table column definition."""

    cid: int
    name: str
    data_type: str
    not_null: bool
    default_value: Any
    is_primary_key: bool


@dataclass
class ForeignKeyInfo:
    """Foreign key relationship between tables."""

    target_table: str
    from_column: str
    to_column: str


@dataclass
class TableSchema:
    """Schema and metadata for an SQLite table or view."""

    name: str
    type: str  # "table" or "view"
    sql: str
    columns: list[ColumnSchema]
    primary_keys: list[str]
    foreign_keys: list[ForeignKeyInfo]
    row_count: int


@dataclass
class SQLiteRowChunk:
    """Grounded tabular row or schema chunk from an SQLite database."""

    table_name: str
    row_pk: str
    data: dict[str, Any]
    narrative_text: str
    is_schema: bool = False


@dataclass
class SQLiteMetadata:
    """Database-level metadata and binary header attributes."""

    db_name: str
    format: str  # "sqlite"
    page_size: int
    total_tables: int
    total_views: int
    table_names: list[str]
    total_rows: int
    file_size_bytes: int


@dataclass
class SQLitePayload:
    """Comprehensive processed SQLite database payload."""

    metadata: SQLiteMetadata
    tables: list[TableSchema] = field(default_factory=list)
    all_chunks: list[SQLiteRowChunk] = field(default_factory=list)


def _validate_sqlite_binary(raw_bytes: bytes) -> int:
    """Validates 16-byte magic header and extracts database page size."""
    if len(raw_bytes) < 100:
        raise ValueError("SQLite binary payload is too small to be a valid database file.")
    if not raw_bytes.startswith(SQLITE_HEADER_MAGIC):
        raise ValueError("Invalid SQLite header: missing 'SQLite format 3\\x00' magic bytes.")
    page_size_val = struct.unpack(">H", raw_bytes[16:18])[0]
    return 65536 if page_size_val == 1 else page_size_val


def _introspect_connection(
    con: sqlite3.Connection,
    db_name: str,
    page_size: int,
    file_size_bytes: int,
    max_rows_per_table: int = 500,
) -> SQLitePayload:
    """Introspects an active SQLite connection, extracts schemas, and formats row chunks."""
    cursor = con.cursor()

    # 1. Discover tables and views
    cursor.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master "
        "WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' "
        "ORDER BY type, name;"
    )
    entities = cursor.fetchall()

    table_schemas: list[TableSchema] = []
    all_chunks: list[SQLiteRowChunk] = []
    table_names: list[str] = []
    total_views = 0
    total_rows_all = 0

    for ent_type, name, _tbl_name, sql in entities:
        table_names.append(name)
        if ent_type == "view":
            total_views += 1

        # Introspect columns via PRAGMA table_info
        # Columns: (cid, name, type, notnull, dflt_value, pk)
        cursor.execute(f'PRAGMA table_info("{name}");')
        col_rows = cursor.fetchall()

        columns: list[ColumnSchema] = []
        pks: list[str] = []
        for cid, col_name, col_type, notnull, dflt, pk in col_rows:
            is_pk = bool(pk)
            if is_pk:
                pks.append(col_name)
            columns.append(
                ColumnSchema(
                    cid=cid,
                    name=col_name,
                    data_type=col_type or "BLOB",
                    not_null=bool(notnull),
                    default_value=dflt,
                    is_primary_key=is_pk,
                )
            )

        # Introspect foreign keys
        # Columns: (id, seq, table, from, to, on_update, on_delete, match)
        cursor.execute(f'PRAGMA foreign_key_list("{name}");')
        fk_rows = cursor.fetchall()
        fks: list[ForeignKeyInfo] = [
            ForeignKeyInfo(
                target_table=fk[2],
                from_column=fk[3],
                to_column=fk[4],
            )
            for fk in fk_rows
        ]

        # Count rows
        try:
            cursor.execute(f'SELECT COUNT(*) FROM "{name}";')
            t_count = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            t_count = 0
        if ent_type == "table":
            total_rows_all += t_count

        # Schema chunk (DDL) for semantic SQL query planning
        if sql:
            schema_narrative = (
                f"[SQLite: {db_name} | Schema DDL | Table: {name}]\n"
                f"DDL: {sql.strip()}\n"
                f"Columns: {', '.join(c.name + ' ' + c.data_type for c in columns)}"
            )
            if fks:
                schema_narrative += "\nForeign Keys: " + ", ".join(
                    f"{fk.from_column} -> {fk.target_table}({fk.to_column})" for fk in fks
                )
            all_chunks.append(
                SQLiteRowChunk(
                    table_name=name,
                    row_pk="SCHEMA_DDL",
                    data={"sql": sql, "type": ent_type},
                    narrative_text=schema_narrative,
                    is_schema=True,
                )
            )

        # Query table rows (skip views for row extraction to prevent duplicate records)
        if ent_type == "table":
            col_names = [c.name for c in columns]
            if col_names:
                col_list_str = ", ".join(f'"{c}"' for c in col_names)
                cursor.execute(f'SELECT {col_list_str} FROM "{name}" LIMIT {max_rows_per_table};')
                fetched_rows = cursor.fetchall()

                for row_idx, r_values in enumerate(fetched_rows, 1):
                    row_dict: dict[str, Any] = {}
                    narrative_items: list[str] = []

                    for c_name, val in zip(col_names, r_values, strict=False):
                        row_dict[c_name] = val
                        narrative_items.append(f"{c_name}: {val}")

                    # Determine primary key citation tag
                    if pks:
                        pk_val = "-".join(str(row_dict.get(pk, "")) for pk in pks)
                    else:
                        pk_val = f"row_{row_idx}"

                    all_chunks.append(
                        SQLiteRowChunk(
                            table_name=name,
                            row_pk=pk_val,
                            data=row_dict,
                            narrative_text=(
                                f"[SQLite: {db_name} | Table: {name} | Row PK: {pk_val}] "
                                f"{' | '.join(narrative_items)}"
                            ),
                            is_schema=False,
                        )
                    )

        table_schemas.append(
            TableSchema(
                name=name,
                type=ent_type,
                sql=sql or "",
                columns=columns,
                primary_keys=pks,
                foreign_keys=fks,
                row_count=t_count,
            )
        )

    meta = SQLiteMetadata(
        db_name=db_name,
        format="sqlite",
        page_size=page_size,
        total_tables=len(table_schemas) - total_views,
        total_views=total_views,
        table_names=table_names,
        total_rows=total_rows_all,
        file_size_bytes=file_size_bytes,
    )

    return SQLitePayload(
        metadata=meta,
        tables=table_schemas,
        all_chunks=all_chunks,
    )


def process_sqlite_binary(
    raw_bytes: bytes,
    db_name: str = "database.db",
    max_rows_per_table: int = 500,
) -> SQLitePayload:
    """Parses an in-memory SQLite database binary into schemas and grounded row narratives.

    Zero third-party dependencies: uses standard library ``sqlite3`` and ``struct``.

    Args:
        raw_bytes: Binary bytes of the SQLite database.
        db_name: Descriptive name for citations.
        max_rows_per_table: Maximum rows to extract per table (default: 500).

    Returns:
        SQLitePayload containing tables, schemas, foreign keys, and row chunks.

    Raises:
        ValueError: If raw_bytes is not a valid SQLite database.
    """
    if not raw_bytes:
        raise ValueError("Cannot process empty SQLite database bytes.")

    page_size = _validate_sqlite_binary(raw_bytes)

    # In-memory deserialization (Python 3.10+) or temporary fallback
    con = sqlite3.connect(":memory:")
    if hasattr(con, "deserialize"):
        try:
            con.deserialize(raw_bytes)
            return _introspect_connection(
                con,
                db_name=db_name,
                page_size=page_size,
                file_size_bytes=len(raw_bytes),
                max_rows_per_table=max_rows_per_table,
            )
        finally:
            con.close()
    else:
        con.close()
        # Fallback to temp file
        with tempfile.NamedTemporaryFile(suffix=".db", delete=True) as tmp:
            tmp.write(raw_bytes)
            tmp.flush()
            return process_sqlite_file(
                tmp.name,
                db_name=db_name,
                max_rows_per_table=max_rows_per_table,
            )


def process_sqlite_file(
    file_path: str | Path,
    db_name: str | None = None,
    max_rows_per_table: int = 500,
) -> SQLitePayload:
    """Parses an SQLite database from disk into schemas and grounded row narratives.

    Args:
        file_path: Path to the SQLite database file (.sqlite, .db).
        db_name: Optional descriptive database name. Defaults to filename.
        max_rows_per_table: Maximum rows to extract per table (default: 500).

    Returns:
        SQLitePayload containing tables, schemas, foreign keys, and row chunks.

    Raises:
        ValueError: If file does not exist or is not a valid SQLite database.
    """
    p = Path(file_path)
    if not p.is_file():
        raise ValueError(f"SQLite file does not exist or is not a file: {file_path}")

    actual_db_name = db_name or p.name
    raw_header = p.read_bytes()[:100]
    page_size = _validate_sqlite_binary(raw_header)
    file_size_bytes = p.stat().st_size

    con = sqlite3.connect(f"file:{p.resolve()}?mode=ro", uri=True)
    try:
        return _introspect_connection(
            con,
            db_name=actual_db_name,
            page_size=page_size,
            file_size_bytes=file_size_bytes,
            max_rows_per_table=max_rows_per_table,
        )
    finally:
        con.close()
