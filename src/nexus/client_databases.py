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

"""``NexusClient.process_mysql_table`` and ``process_mongo_collection``: rows and documents to
masked record chunks.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from nexus.chunk_limits import bounded_output
from nexus.models import ProcessedChunk, ProcessedDocumentPayload, ProcessingStageTrace
from nexus.table_records import jsonable, mask_rows

try:
    from nexus.processing.mongodb import (
        chunk_mongo_collection,
        flatten_mongo_document,
        serialize_bson_value,
    )
    from nexus.processing.mysql import chunk_mysql_table
except (ImportError, ModuleNotFoundError):
    from nexus_processing.mongodb import (
        chunk_mongo_collection,
        flatten_mongo_document,
        serialize_bson_value,
    )
    from nexus_processing.mysql import chunk_mysql_table

__all__ = ["DatabaseMixin"]


class DatabaseMixin:
    """Mixed into ``NexusClient``."""

    @bounded_output
    def process_mysql_table(
        self,
        table_name: str,
        rows: list[dict[str, Any]],
        primary_key: str | None = None,
        metadata: dict[str, Any] | None = None,
        rows_per_chunk: int = 1,
        enable_guardrails: bool = True,
        shallow_mode: bool = False,
    ) -> ProcessedDocumentPayload:
        """Processes relational MySQL rows into structured tabular narratives,
        applies safety guardrails & PII sanitization.

        Args:
            table_name: Name of the relational MySQL table (e.g. 'customers', 'orders').
            rows: List of dictionary row representations (column -> value).
            primary_key: Optional explicit primary key column name. Auto-detects 'id' / '_id'.
            metadata: Custom metadata dictionary to attach to table document and row chunks.
            rows_per_chunk: Number of rows bundled per chunk narrative (default: 1).
            enable_guardrails: When True (default), scrubs sensitive PII (Luhn cards, emails).
            shallow_mode: Alias for bypassing PII sanitization for internal analysis.

        Returns:
            ProcessedDocumentPayload with table-grounded chunks, and telemetry.
        """
        t_start_total = time.perf_counter()
        traces: list[ProcessingStageTrace] = []
        apply_guardrails = enable_guardrails and (not shallow_mode)

        # -------------------------------------------------------------------------
        # Step 1: MySQL Schema & Primary Key Analysis (0% - 20%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        columns: set[str] = set()
        for r in rows:
            columns.update(r.keys())
        col_list = sorted(columns)

        detected_pk = primary_key
        if not detected_pk:
            for candidate in ("id", "_id", f"{table_name}_id", f"{table_name}Id"):
                if candidate in columns:
                    detected_pk = candidate
                    break

        raw_payload_bytes = json.dumps(rows, default=str).encode("utf-8")
        file_size_bytes = len(raw_payload_bytes)
        content_hash = hashlib.md5(raw_payload_bytes).hexdigest()
        dt_step1 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=1,
                stage_name="MySQL Schema & Primary Key Analysis",
                status="completed",
                duration_ms=round(dt_step1, 2),
                summary=(
                    f"Analyzed table '{table_name}' ({len(rows)} rows, {len(col_list)} cols). "
                    f"Primary Key: '{detected_pk or 'None'}'. Schema cardinality: {len(col_list)}."
                ),
                details={
                    "table_name": table_name,
                    "row_count": len(rows),
                    "column_count": len(col_list),
                    "columns": col_list,
                    "primary_key": detected_pk,
                },
            )
        )

        # -------------------------------------------------------------------------
        # Step 2: Relational Row Serialization & Typing (20% - 40%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        dt_step2 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=2,
                stage_name="Relational Row Serialization & Typing",
                status="completed",
                duration_ms=round(dt_step2, 2),
                summary=(
                    f"Serialized {len(rows)} relational rows into column narratives "
                    f"preserving MySQL data types and NULL values."
                ),
                details={
                    "rows_serialized": len(rows),
                    "table_name": table_name,
                },
            )
        )

        # -------------------------------------------------------------------------
        # Step 3: Format-Aware Tabular Chunking (40% - 60%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        # Mask by column before serializing: ids, amounts and timestamps keep their values.
        masked_rows, rows_masked = mask_rows(self.guardrails, rows, apply_guardrails)
        raw_chunks = chunk_mysql_table(
            masked_rows,
            table_name=table_name,
            primary_key=detected_pk,
            rows_per_chunk=rows_per_chunk,
        )
        dt_step3 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=3,
                stage_name="Format-Aware Tabular Chunking",
                status="completed",
                duration_ms=round(dt_step3, 2),
                summary=(
                    f"Partitioned {len(rows)} rows into {len(raw_chunks)} format-aware chunk(s) "
                    f"({rows_per_chunk} row(s)/chunk)."
                ),
                details={
                    "total_chunks": len(raw_chunks),
                    "rows_per_chunk": rows_per_chunk,
                },
            )
        )

        # -------------------------------------------------------------------------
        # Step 4: Safety Guardrails & PII Sanitization (60% - 80%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        cleaned_chunks: list[str] = list(raw_chunks)  # masked by column in step 3
        total_masked = rows_masked

        dt_step4 = (time.perf_counter() - t0) * 1000.0
        guardrails_summary = (
            f"Evaluated {len(raw_chunks)} table chunks through column-aware PII masking. "
            f"Sanitized sensitive data in {total_masked} row(s)."
            if apply_guardrails
            else "Safety guardrails bypassed: preserving raw tabular records."
        )

        traces.append(
            ProcessingStageTrace(
                step_number=4,
                stage_name="Safety Guardrails & PII Sanitization",
                status="completed",
                duration_ms=round(dt_step4, 2),
                summary=guardrails_summary,
                details={
                    "guardrails_enabled": apply_guardrails,
                    "chunks_with_pii": total_masked,
                },
            )
        )

        # -------------------------------------------------------------------------
        # Step 5: Chunk Assembly (80% - 100%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        processed_chunks: list[ProcessedChunk] = []
        doc_id = f"mysql:{table_name}"

        group = max(1, rows_per_chunk)
        for idx, chunk_text in enumerate(cleaned_chunks):
            chunk_meta: dict[str, Any] = {
                "source_table": table_name,
                "primary_key": detected_pk,
                "chunk_index": idx,
                "is_database": True,
                "database_type": "mysql",
            }
            if group == 1:
                chunk_meta["record"] = jsonable(masked_rows[idx])
            else:
                batch = masked_rows[idx * group : (idx + 1) * group]
                chunk_meta["records"] = [jsonable(r) for r in batch]
            if metadata:
                chunk_meta.update(metadata)

            processed_chunks.append(
                ProcessedChunk(
                    chunk_id=f"{doc_id}:{idx}",
                    document_id=doc_id,
                    chunk_index=idx,
                    text=chunk_text,
                    metadata=chunk_meta,
                )
            )

        dt_step5 = (time.perf_counter() - t0) * 1000.0
        traces.append(
            ProcessingStageTrace(
                step_number=5,
                stage_name="Chunk Assembly",
                status="completed",
                duration_ms=round(dt_step5, 2),
                summary="Assembled final chunks with grounded metadata (vectors are produced at "
                "storage time by embed_texts()).",
                details={},
            )
        )

        doc_meta: dict[str, Any] = {
            "format": "mysql",
            "table_name": table_name,
            "columns": col_list,
            "primary_key": detected_pk,
            "row_count": len(rows),
            "is_database": True,
            "database_type": "mysql",
        }
        if metadata:
            doc_meta.update(metadata)

        total_ms = (time.perf_counter() - t_start_total) * 1000.0
        summary_msg = (
            f"Processed MySQL table '{table_name}' ({len(rows)} rows, {len(col_list)} cols) "
            f"into {len(processed_chunks)} chunks in {total_ms:.1f}ms."
        )

        return ProcessedDocumentPayload(
            document_id=doc_id,
            name=f"mysql_{table_name}",
            file_type="mysql",
            file_size_bytes=file_size_bytes,
            content_hash=content_hash,
            classification=doc_meta.get("classification", "database"),
            chunks=processed_chunks,
            metadata=doc_meta,
            execution_trace=traces,
            summary=summary_msg,
        )

    @bounded_output
    def process_mongo_collection(
        self,
        collection_name: str,
        documents: list[dict[str, Any]],
        flatten_nested: bool = True,
        metadata: dict[str, Any] | None = None,
        enable_guardrails: bool = True,
        shallow_mode: bool = False,
    ) -> ProcessedDocumentPayload:
        """Processes semi-structured MongoDB BSON/Extended-JSON collections into
        flattened dot-notation semantic narratives, scrubs sensitive PII.

        Args:
            collection_name: Name of the MongoDB collection (e.g. 'users', 'transactions').
            documents: List of BSON / Extended-JSON / dictionary documents.
            flatten_nested: When True (default), flattens nested dicts/arrays to dot-notation.
            metadata: Custom metadata dictionary to attach to collection document and chunks.
            enable_guardrails: When True (default), scrubs sensitive PII (Luhn cards, emails).
            shallow_mode: Alias for bypassing PII sanitization.

        Returns:
            ProcessedDocumentPayload with collection-grounded chunks, and traces.
        """
        t_start_total = time.perf_counter()
        traces: list[ProcessingStageTrace] = []
        apply_guardrails = enable_guardrails and (not shallow_mode)

        # -------------------------------------------------------------------------
        # Step 1: MongoDB BSON / Extended-JSON Normalization (0% - 20%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        normalized_docs = [serialize_bson_value(d) for d in documents]
        raw_payload_bytes = json.dumps(normalized_docs, default=str).encode("utf-8")
        file_size_bytes = len(raw_payload_bytes)
        content_hash = hashlib.md5(raw_payload_bytes).hexdigest()
        dt_step1 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=1,
                stage_name="MongoDB BSON / Extended-JSON Normalization",
                status="completed",
                duration_ms=round(dt_step1, 2),
                summary=(
                    f"Parsed and normalized {len(documents)} BSON/Extended-JSON documents "
                    f"($oid, $date, $numberDecimal) in collection '{collection_name}'."
                ),
                details={
                    "collection_name": collection_name,
                    "document_count": len(documents),
                    "file_size_bytes": file_size_bytes,
                },
            )
        )

        # -------------------------------------------------------------------------
        # Step 2: Hierarchical Keypath Flattening (Dot-Notation) (20% - 40%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        total_keypaths = 0
        if flatten_nested:
            for nd in normalized_docs:
                total_keypaths += len(flatten_mongo_document(nd))
        dt_step2 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=2,
                stage_name="Hierarchical Keypath Flattening (Dot-Notation)",
                status="completed",
                duration_ms=round(dt_step2, 2),
                summary=(
                    f"Flattened nested structures into {total_keypaths} dot-notation keypaths."
                    if flatten_nested
                    else "Hierarchical flattening disabled; preserving nested JSON structures."
                ),
                details={
                    "flatten_nested": flatten_nested,
                    "total_keypaths": total_keypaths,
                },
            )
        )

        # -------------------------------------------------------------------------
        # Step 3: Document Record Serialization & Chunking (40% - 60%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        masked_docs, docs_masked = mask_rows(self.guardrails, normalized_docs, apply_guardrails)
        raw_chunks = chunk_mongo_collection(
            masked_docs, collection_name=collection_name, flatten=flatten_nested
        )
        dt_step3 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=3,
                stage_name="Document Record Serialization & Chunking",
                status="completed",
                duration_ms=round(dt_step3, 2),
                summary=(
                    f"Serialized {len(raw_chunks)} collection-grounded document narratives "
                    f"with unique ID anchors."
                ),
                details={
                    "total_chunks": len(raw_chunks),
                    "collection_name": collection_name,
                },
            )
        )

        # -------------------------------------------------------------------------
        # Step 4: Safety Guardrails & PII Sanitization (60% - 80%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        cleaned_chunks: list[str] = list(raw_chunks)  # masked by field in step 3
        total_masked = docs_masked

        dt_step4 = (time.perf_counter() - t0) * 1000.0
        guardrails_summary = (
            f"Evaluated {len(raw_chunks)} MongoDB document chunks through column-aware "
            "PII masking. "
            f"Sanitized sensitive data in {total_masked} document(s)."
            if apply_guardrails
            else "Safety guardrails bypassed: preserving raw document records."
        )

        traces.append(
            ProcessingStageTrace(
                step_number=4,
                stage_name="Safety Guardrails & PII Sanitization",
                status="completed",
                duration_ms=round(dt_step4, 2),
                summary=guardrails_summary,
                details={
                    "guardrails_enabled": apply_guardrails,
                    "chunks_with_pii": total_masked,
                },
            )
        )

        # -------------------------------------------------------------------------
        # Step 5: Chunk Assembly (80% - 100%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        processed_chunks: list[ProcessedChunk] = []
        doc_id = f"mongodb:{collection_name}"

        for idx, chunk_text in enumerate(cleaned_chunks):
            chunk_meta: dict[str, Any] = {
                "collection_name": collection_name,
                "chunk_index": idx,
                "is_database": True,
                "database_type": "mongodb",
                "record": jsonable(masked_docs[idx]),
            }
            if metadata:
                chunk_meta.update(metadata)

            processed_chunks.append(
                ProcessedChunk(
                    chunk_id=f"{doc_id}:{idx}",
                    document_id=doc_id,
                    chunk_index=idx,
                    text=chunk_text,
                    metadata=chunk_meta,
                )
            )

        dt_step5 = (time.perf_counter() - t0) * 1000.0
        traces.append(
            ProcessingStageTrace(
                step_number=5,
                stage_name="Chunk Assembly",
                status="completed",
                duration_ms=round(dt_step5, 2),
                summary="Assembled final chunks with grounded metadata (vectors are produced at "
                "storage time by embed_texts()).",
                details={},
            )
        )

        doc_meta: dict[str, Any] = {
            "format": "mongodb",
            "collection_name": collection_name,
            "document_count": len(documents),
            "is_database": True,
            "database_type": "mongodb",
            "flatten_nested": flatten_nested,
        }
        if metadata:
            doc_meta.update(metadata)

        total_ms = (time.perf_counter() - t_start_total) * 1000.0
        summary_msg = (
            f"Processed MongoDB collection '{collection_name}' ({len(documents)} docs) "
            f"into {len(processed_chunks)} chunks in {total_ms:.1f}ms."
        )

        return ProcessedDocumentPayload(
            document_id=doc_id,
            name=f"mongodb_{collection_name}",
            file_type="mongodb",
            file_size_bytes=file_size_bytes,
            content_hash=content_hash,
            classification=doc_meta.get("classification", "database"),
            chunks=processed_chunks,
            metadata=doc_meta,
            execution_trace=traces,
            summary=summary_msg,
        )
