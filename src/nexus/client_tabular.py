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

"""``NexusClient.process_spreadsheet`` and ``process_sqlite``: workbooks and SQLite files to
masked row-group chunks.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from nexus.chunk_limits import bounded_output
from nexus.models import ProcessedChunk, ProcessedDocumentPayload, ProcessingStageTrace
from nexus.table_records import jsonable, mask_rows

try:
    from nexus.processing.office import process_spreadsheet_binary, spreadsheet_row_text
    from nexus.processing.sqlite import process_sqlite_binary, process_sqlite_file
except (ImportError, ModuleNotFoundError):
    from nexus_processing.office import process_spreadsheet_binary, spreadsheet_row_text
    from nexus_processing.sqlite import process_sqlite_binary, process_sqlite_file

__all__ = ["TabularMixin"]


class TabularMixin:
    """Mixed into ``NexusClient``."""

    @bounded_output
    def process_spreadsheet(
        self,
        spreadsheet_id: str,
        name: str,
        spreadsheet_bytes: bytes | None = None,
        file_path: str | Path | None = None,
        metadata: dict[str, Any] | None = None,
        enable_guardrails: bool = True,
        shallow_mode: bool = False,
        ocr_provider: Any = None,
        auto_extract: bool = True,
    ) -> ProcessedDocumentPayload:
        """Processes an Excel spreadsheet (.xlsx) through native pure-Python container
        decompression, shared string resolution, worksheet tabular framing, PII sanitization.
        """
        t_start_total = time.perf_counter()
        traces: list[ProcessingStageTrace] = []
        apply_guardrails = enable_guardrails and (not shallow_mode)

        if spreadsheet_bytes is not None:
            raw_data = spreadsheet_bytes
        elif file_path is not None:
            raw_data = Path(file_path).read_bytes()
        else:
            raise ValueError(
                "Either spreadsheet_bytes or file_path must be provided to process_spreadsheet."
            )

        file_size_bytes = len(raw_data)
        content_hash = hashlib.md5(raw_data).hexdigest()

        # Step 1: OPC Archive Decompression & Workbook Discovery
        t0 = time.perf_counter()
        spreadsheet_payload = process_spreadsheet_binary(
            raw_data,
            filename=name,
            ocr_provider=ocr_provider,
            auto_extract=auto_extract,
        )
        meta = spreadsheet_payload.metadata
        dt_step1 = (time.perf_counter() - t0) * 1000.0

        sheet_preview = ", ".join(meta.sheet_names[:5])
        if len(meta.sheet_names) > 5:
            sheet_preview += "..."

        traces.append(
            ProcessingStageTrace(
                step_number=1,
                stage_name="OPC Archive Decompression & Workbook Discovery",
                status="completed",
                duration_ms=round(dt_step1, 2),
                summary=(
                    f"Decompressed OpenXML archive and discovered {meta.total_sheets} "
                    f"worksheet(s): {sheet_preview}."
                ),
                details={
                    "format": meta.format,
                    "total_sheets": meta.total_sheets,
                    "sheet_names": meta.sheet_names,
                    "file_size_bytes": file_size_bytes,
                },
            )
        )

        # Step 2: Shared Strings & XML Schema Resolution
        t0 = time.perf_counter()
        dt_step2 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=2,
                stage_name="Shared Strings & XML Schema Resolution",
                status="completed",
                duration_ms=round(dt_step2, 2),
                summary=(
                    f"Resolved shared strings and tabular schemas across {meta.total_sheets} "
                    f"sheet(s) with {meta.total_cells} total populated cells."
                ),
                details={
                    "total_cells": meta.total_cells,
                    "total_sheets": meta.total_sheets,
                },
            )
        )

        # Step 3: Worksheet Tabular Framing & Cell Parsing
        t0 = time.perf_counter()
        total_data_chunks = len(spreadsheet_payload.all_chunks)
        dt_step3 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=3,
                stage_name="Worksheet Tabular Framing & Cell Parsing",
                status="completed",
                duration_ms=round(dt_step3, 2),
                summary=(
                    f"Framed {meta.total_rows} rows into {total_data_chunks} tabular chunk(s) "
                    f"with column coordinate mappings."
                ),
                details={
                    "total_rows": meta.total_rows,
                    "total_chunks": total_data_chunks,
                    "sheets": [
                        {"name": s.sheet_name, "rows": s.total_rows, "cols": s.total_columns}
                        for s in spreadsheet_payload.sheets
                    ],
                },
            )
        )

        # Step 4: Safety Guardrails & PII Sanitization
        t0 = time.perf_counter()
        # Rows are masked by column, one classification per sheet; the row text is
        # rebuilt from the masked row so text and record always agree.
        masked_data: dict[int, dict[str, Any]] = {}
        total_masked_items = 0
        for sheet in spreadsheet_payload.sheets:
            data = [r.data for r in sheet.rows]
            masked, changed = mask_rows(self.guardrails, data, apply_guardrails)
            total_masked_items += changed
            for row_chunk, row in zip(sheet.rows, masked, strict=True):
                masked_data[id(row_chunk)] = row
        sanitized_chunks: list[tuple[Any, str]] = []
        for chunk in spreadsheet_payload.all_chunks:
            n_text = chunk.narrative_text
            if id(chunk) in masked_data:
                if apply_guardrails:
                    n_text = spreadsheet_row_text(
                        name, chunk.sheet_name, chunk.row_index, masked_data[id(chunk)]
                    )
            elif apply_guardrails and n_text:
                scrubbed_text = self.guardrails.mask_pii(n_text)
                total_masked_items += int(scrubbed_text != n_text)
                n_text = scrubbed_text
            sanitized_chunks.append((chunk, n_text))
        data_sheets = [s for s in spreadsheet_payload.sheets if s.rows]

        dt_step4 = (time.perf_counter() - t0) * 1000.0
        traces.append(
            ProcessingStageTrace(
                step_number=4,
                stage_name="Safety Guardrails & PII Sanitization",
                status="completed",
                duration_ms=round(dt_step4, 2),
                summary=(
                    f"Applied PII detection across {len(sanitized_chunks)} tabular row(s). "
                    f"Masked {total_masked_items} sensitive items."
                ),
                details={
                    "guardrails_enabled": apply_guardrails,
                    "masked_items": total_masked_items,
                },
            )
        )

        # Step 5: Sheet-Grounded Chunk Assembly
        t0 = time.perf_counter()
        processed_chunks: list[ProcessedChunk] = []

        for idx, (chunk, scrubbed_text) in enumerate(sanitized_chunks):
            chunk_meta: dict[str, Any] = {
                "sheet_name": chunk.sheet_name,
                "sheet": chunk.sheet_name,
                "row_index": chunk.row_index,
                "is_spreadsheet": True,
            }
            if id(chunk) in masked_data:
                # Typed (numbers, ISO dates), masked row; with several data sheets the
                # sheet is a field so one workbook can be queried per sheet.
                record = jsonable(masked_data[id(chunk)])
                if len(data_sheets) > 1 and "sheet" not in record:
                    record["sheet"] = chunk.sheet_name
                chunk_meta["record"] = record
                chunk_meta["data"] = jsonable(masked_data[id(chunk)])
            if metadata:
                chunk_meta.update(metadata)

            processed_chunks.append(
                ProcessedChunk(
                    chunk_id=f"{spreadsheet_id}:{chunk.sheet_name}:{chunk.row_index}",
                    document_id=spreadsheet_id,
                    chunk_index=idx,
                    text=scrubbed_text,
                    metadata=chunk_meta,
                )
            )

        dt_step5 = (time.perf_counter() - t0) * 1000.0
        traces.append(
            ProcessingStageTrace(
                step_number=5,
                stage_name="Sheet-Grounded Chunk Assembly",
                status="completed",
                duration_ms=round(dt_step5, 2),
                summary="Assembled final chunks with grounded metadata (vectors are produced at "
                "storage time by embed_texts()).",
                details={},
            )
        )

        doc_meta: dict[str, Any] = {
            "format": meta.format,
            "sheet_names": meta.sheet_names,
            "total_sheets": meta.total_sheets,
            "total_rows": meta.total_rows,
            "total_cells": meta.total_cells,
            "is_spreadsheet": True,
        }
        if metadata:
            doc_meta.update(metadata)

        total_ms = (time.perf_counter() - t_start_total) * 1000.0
        summary_msg = (
            f"Processed {meta.format} workbook '{name}' ({meta.total_sheets} sheets, "
            f"{meta.total_rows} rows) into {len(processed_chunks)} chunks "
            f"in {total_ms:.1f}ms."
        )

        return ProcessedDocumentPayload(
            document_id=spreadsheet_id,
            name=name,
            file_type="spreadsheet",
            file_size_bytes=file_size_bytes,
            content_hash=content_hash,
            classification=doc_meta.get("classification", "spreadsheet"),
            chunks=processed_chunks,
            metadata=doc_meta,
            execution_trace=traces,
            summary=summary_msg,
        )

    @bounded_output
    def process_sqlite(
        self,
        db_id: str,
        name: str,
        db_bytes: bytes | None = None,
        file_path: str | Path | None = None,
        max_rows_per_table: int = 500,
        metadata: dict[str, Any] | None = None,
        enable_guardrails: bool = True,
        shallow_mode: bool = False,
    ) -> ProcessedDocumentPayload:
        """Processes an Embedded SQLite database (.sqlite, .db) through binary header validation,
        schema DDL introspection, foreign-key relationship graph extraction, PII sanitization.
        """
        t_start_total = time.perf_counter()
        traces: list[ProcessingStageTrace] = []
        apply_guardrails = enable_guardrails and (not shallow_mode)

        if db_bytes is not None:
            raw_data = db_bytes
            file_size_bytes = len(raw_data)
            content_hash = hashlib.md5(raw_data).hexdigest()
            t0 = time.perf_counter()
            payload = process_sqlite_binary(
                raw_data, db_name=name, max_rows_per_table=max_rows_per_table
            )
        elif file_path is not None:
            p = Path(file_path)
            file_size_bytes = p.stat().st_size
            content_hash = hashlib.md5(p.read_bytes()[:1024]).hexdigest()
            t0 = time.perf_counter()
            payload = process_sqlite_file(p, db_name=name, max_rows_per_table=max_rows_per_table)
        else:
            raise ValueError("Either db_bytes or file_path must be provided to process_sqlite.")

        meta = payload.metadata
        dt_step1 = (time.perf_counter() - t0) * 1000.0

        table_preview = ", ".join(meta.table_names[:5])
        if len(meta.table_names) > 5:
            table_preview += "..."

        # Step 1: SQLite Binary Validation & Schema Introspection
        traces.append(
            ProcessingStageTrace(
                step_number=1,
                stage_name="SQLite Binary Validation & Schema Introspection",
                status="completed",
                duration_ms=round(dt_step1, 2),
                summary=(
                    f"Validated SQLite format 3 binary (Page size: {meta.page_size}B). "
                    f"Discovered {meta.total_tables} table(s) and {meta.total_views} view(s): "
                    f"{table_preview}."
                ),
                details={
                    "page_size": meta.page_size,
                    "total_tables": meta.total_tables,
                    "total_views": meta.total_views,
                    "table_names": meta.table_names,
                },
            )
        )

        # Step 2: Table Graph & Foreign Key Relationship Discovery
        t0 = time.perf_counter()
        total_fks = sum(len(t.foreign_keys) for t in payload.tables)
        dt_step2 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=2,
                stage_name="Table Graph & Foreign Key Relationship Discovery",
                status="completed",
                duration_ms=round(dt_step2, 2),
                summary=(
                    f"Mapped relational schema graph across {len(payload.tables)} entities "
                    f"with {total_fks} foreign key constraint(s)."
                ),
                details={
                    "entities_count": len(payload.tables),
                    "foreign_keys_count": total_fks,
                },
            )
        )

        # Step 3: Tabular Row Extraction & Record Framing
        t0 = time.perf_counter()
        data_chunks_count = sum(1 for c in payload.all_chunks if not c.is_schema)
        schema_chunks_count = sum(1 for c in payload.all_chunks if c.is_schema)
        dt_step3 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=3,
                stage_name="Tabular Row Extraction & Record Framing",
                status="completed",
                duration_ms=round(dt_step3, 2),
                summary=(
                    f"Extracted {meta.total_rows} total rows, producing {data_chunks_count} "
                    f"row chunk(s) and {schema_chunks_count} schema DDL chunk(s)."
                ),
                details={
                    "total_rows": meta.total_rows,
                    "data_chunks": data_chunks_count,
                    "schema_chunks": schema_chunks_count,
                },
            )
        )

        # Step 4: Safety Guardrails & PII Sanitization
        t0 = time.perf_counter()
        sanitized_chunks: list[tuple[Any, str]] = []
        total_masked_items = 0

        for chk in payload.all_chunks:
            n_text = chk.narrative_text
            if apply_guardrails and n_text and not chk.is_schema:
                scrubbed_text = self.guardrails.mask_pii(n_text)
                if scrubbed_text != n_text:
                    total_masked_items += 1
            else:
                scrubbed_text = n_text
            sanitized_chunks.append((chk, scrubbed_text))

        dt_step4 = (time.perf_counter() - t0) * 1000.0
        traces.append(
            ProcessingStageTrace(
                step_number=4,
                stage_name="Safety Guardrails & PII Sanitization",
                status="completed",
                duration_ms=round(dt_step4, 2),
                summary=(
                    f"Applied PII detection across {len(sanitized_chunks)} database chunk(s). "
                    f"Masked {total_masked_items} sensitive item(s)."
                ),
                details={
                    "guardrails_enabled": apply_guardrails,
                    "masked_items": total_masked_items,
                },
            )
        )

        # Step 5: Relational-Grounded Chunk Assembly
        t0 = time.perf_counter()
        processed_chunks: list[ProcessedChunk] = []

        for idx, (chk, scrubbed_text) in enumerate(sanitized_chunks):
            chunk_meta: dict[str, Any] = {
                "table_name": chk.table_name,
                "row_pk": chk.row_pk,
                "is_schema": chk.is_schema,
                "is_sqlite": True,
            }
            if metadata:
                chunk_meta.update(metadata)

            processed_chunks.append(
                ProcessedChunk(
                    chunk_id=f"{db_id}:{chk.table_name}:{chk.row_pk}:{idx}",
                    document_id=db_id,
                    chunk_index=idx,
                    text=scrubbed_text,
                    metadata=chunk_meta,
                )
            )

        dt_step5 = (time.perf_counter() - t0) * 1000.0
        traces.append(
            ProcessingStageTrace(
                step_number=5,
                stage_name="Relational-Grounded Chunk Assembly",
                status="completed",
                duration_ms=round(dt_step5, 2),
                summary="Assembled final chunks with grounded metadata (vectors are produced at "
                "storage time by embed_texts()).",
                details={},
            )
        )

        doc_meta: dict[str, Any] = {
            "format": meta.format,
            "page_size": meta.page_size,
            "total_tables": meta.total_tables,
            "total_views": meta.total_views,
            "table_names": meta.table_names,
            "total_rows": meta.total_rows,
            "is_sqlite": True,
        }
        if metadata:
            doc_meta.update(metadata)

        total_ms = (time.perf_counter() - t_start_total) * 1000.0
        summary_msg = (
            f"Processed {meta.format} database '{name}' ({meta.total_tables} tables, "
            f"{meta.total_rows} rows) into {len(processed_chunks)} chunks "
            f"in {total_ms:.1f}ms."
        )

        return ProcessedDocumentPayload(
            document_id=db_id,
            name=name,
            file_type="sqlite",
            file_size_bytes=file_size_bytes,
            content_hash=content_hash,
            classification=doc_meta.get("classification", "sqlite"),
            chunks=processed_chunks,
            metadata=doc_meta,
            execution_trace=traces,
            summary=summary_msg,
        )
