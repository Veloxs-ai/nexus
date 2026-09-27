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

import datetime
from typing import Any




def serialize_mysql_row(
    row: dict[str, Any], table_name: str, primary_key: str | list[str] | None = None
) -> str:
    """Transforms a single relational table row into a structured, contextual narrative."""
    pk_val = None
    if isinstance(primary_key, list):
        pk_parts = [str(row.get(k, "")) for k in primary_key if k in row]
        pk_val = "-".join(pk_parts) if pk_parts else None
    elif isinstance(primary_key, str) and primary_key in row:
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
        elif isinstance(val, bool | int | float):
            items.append(f"{col}: {val}")
        elif isinstance(val, bytes):
            items.append(f"<Binary:{len(val)}B>")
        elif isinstance(
            val, datetime.datetime | datetime.date | datetime.time
        ):
            items.append(f"{col}: {val.isoformat()}")
        elif isinstance(val, datetime.timedelta):
            total_secs = int(val.total_seconds())
            items.append(f"{col}: {total_secs}s")
        else:
            clean_str = (
                str(val).replace("\r\n", " ").replace("\n", " ").strip()
            )
            items.append(f"{col}: {clean_str}")

    return pk_header + " | ".join(items)


def chunk_mysql_table(
    rows: list[dict[str, Any]],
    table_name: str,
    primary_key: str | list[str] | None = None,
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


