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

"""``NexusClient.process_code`` and ``process_openapi``: source files and API specs to
symbol/operation chunks.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from nexus.chunk_limits import bounded_output
from nexus.models import ProcessedChunk, ProcessedDocumentPayload, ProcessingStageTrace

try:
    from nexus.processing.code import process_code, process_openapi_spec
except (ImportError, ModuleNotFoundError):
    from nexus_processing.code import process_code, process_openapi_spec

__all__ = ["CodeMixin"]


class CodeMixin:
    """Mixed into ``NexusClient``."""

    @bounded_output
    def process_code(
        self,
        code_id: str,
        name: str,
        code_input: str | bytes,
        language: str | None = None,
        metadata: dict[str, Any] | None = None,
        enable_guardrails: bool = True,
        shallow_mode: bool = False,
    ) -> ProcessedDocumentPayload:
        """Processes source code (.py, .ts, .js, .go, .rs, etc.) through AST/grammar parsing,
        symbol & scope extraction, PII sanitization.
        """
        t_start_total = time.perf_counter()
        traces: list[ProcessingStageTrace] = []
        apply_guardrails = enable_guardrails and (not shallow_mode)

        if isinstance(code_input, bytes):
            raw_bytes = code_input
            text = raw_bytes.decode("utf-8", errors="replace")
        else:
            text = str(code_input)
            raw_bytes = text.encode("utf-8")

        file_size_bytes = len(raw_bytes)
        content_hash = hashlib.md5(raw_bytes).hexdigest()

        # Step 1: Source Code Ingestion & Format Identification
        t0 = time.perf_counter()
        payload = process_code(text, file_name=name, language=language)
        meta = payload.metadata
        dt_step1 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=1,
                stage_name="Source Code Ingestion & Format Identification",
                status="completed",
                duration_ms=round(dt_step1, 2),
                summary=(
                    f"Parsed {meta.language} ({meta.format}) source file '{name}' with "
                    f"{meta.total_lines} line(s). Hash: {content_hash[:8]}..."
                ),
                details={
                    "language": meta.language,
                    "format": meta.format,
                    "total_lines": meta.total_lines,
                },
            )
        )

        # Step 2: AST Grammar & Lexical Tokenization
        t0 = time.perf_counter()
        dt_step2 = (time.perf_counter() - t0) * 1000.0
        traces.append(
            ProcessingStageTrace(
                step_number=2,
                stage_name="AST Grammar & Lexical Tokenization",
                status="completed",
                duration_ms=round(dt_step2, 2),
                summary=(
                    f"Decomposed syntax tree discovering {meta.total_symbols} total symbol(s) "
                    f"and {len(meta.imports)} module import(s)."
                ),
                details={
                    "total_symbols": meta.total_symbols,
                    "imports": meta.imports,
                },
            )
        )

        # Step 3: Scope Hierarchy & Signature Extraction
        t0 = time.perf_counter()
        dt_step3 = (time.perf_counter() - t0) * 1000.0
        traces.append(
            ProcessingStageTrace(
                step_number=3,
                stage_name="Scope Hierarchy & Signature Extraction",
                status="completed",
                duration_ms=round(dt_step3, 2),
                summary=(
                    f"Extracted {meta.total_functions} function/method(s) and {meta.total_classes} "
                    f"class/interface/struct(s) into {len(payload.chunks)} grounded code chunk(s)."
                ),
                details={
                    "total_functions": meta.total_functions,
                    "total_classes": meta.total_classes,
                    "total_chunks": len(payload.chunks),
                },
            )
        )

        # Step 4: Safety Guardrails & Secret Scrubbing
        t0 = time.perf_counter()
        sanitized_chunks: list[tuple[Any, str]] = []
        total_masked_items = 0

        for chk in payload.chunks:
            n_text = chk.narrative_text
            if apply_guardrails and n_text:
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
                stage_name="Safety Guardrails & Secret Scrubbing",
                status="completed",
                duration_ms=round(dt_step4, 2),
                summary=(
                    f"Scanned {len(sanitized_chunks)} code chunk(s) for sensitive keys, "
                    f"tokens, and PII. Masked {total_masked_items} sensitive item(s)."
                ),
                details={
                    "guardrails_enabled": apply_guardrails,
                    "masked_items": total_masked_items,
                },
            )
        )

        # Step 5: AST-Grounded Chunk Assembly
        t0 = time.perf_counter()
        processed_chunks: list[ProcessedChunk] = []

        for idx, (chk, scrubbed_text) in enumerate(sanitized_chunks):
            chunk_meta: dict[str, Any] = {
                "symbol_name": chk.symbol_name,
                "symbol_type": chk.symbol_type,
                "language": chk.language,
                "start_line": chk.start_line,
                "end_line": chk.end_line,
                "signature": chk.signature,
                "is_code": True,
            }
            if chk.metadata:
                chunk_meta.update(chk.metadata)
            if metadata:
                chunk_meta.update(metadata)

            processed_chunks.append(
                ProcessedChunk(
                    chunk_id=f"{code_id}:{chk.symbol_name}:{idx}",
                    document_id=code_id,
                    chunk_index=idx,
                    text=scrubbed_text,
                    metadata=chunk_meta,
                )
            )

        dt_step5 = (time.perf_counter() - t0) * 1000.0
        traces.append(
            ProcessingStageTrace(
                step_number=5,
                stage_name="AST-Grounded Chunk Assembly",
                status="completed",
                duration_ms=round(dt_step5, 2),
                summary="Assembled final chunks with grounded metadata (vectors are produced at "
                "storage time by embed_texts()).",
                details={},
            )
        )

        doc_meta: dict[str, Any] = {
            "format": meta.format,
            "language": meta.language,
            "total_lines": meta.total_lines,
            "total_symbols": meta.total_symbols,
            "total_functions": meta.total_functions,
            "total_classes": meta.total_classes,
            "imports": meta.imports,
            "is_code": True,
        }
        if metadata:
            doc_meta.update(metadata)

        total_ms = (time.perf_counter() - t_start_total) * 1000.0
        summary_msg = (
            f"Processed {meta.language} code '{name}' ({meta.total_symbols} symbols, "
            f"{meta.total_lines} lines) into {len(processed_chunks)} chunks "
            f"in {total_ms:.1f}ms."
        )

        return ProcessedDocumentPayload(
            document_id=code_id,
            name=name,
            file_type="code",
            file_size_bytes=file_size_bytes,
            content_hash=content_hash,
            classification=doc_meta.get("classification", f"code_{meta.language}"),
            chunks=processed_chunks,
            metadata=doc_meta,
            execution_trace=traces,
            summary=summary_msg,
        )

    @bounded_output
    def process_openapi(
        self,
        spec_id: str,
        name: str,
        spec_data: str | bytes | dict[str, Any],
        metadata: dict[str, Any] | None = None,
        enable_guardrails: bool = True,
        shallow_mode: bool = False,
    ) -> ProcessedDocumentPayload:
        """Processes OpenAPI 3.0/3.1 or Swagger 2.0 specs through endpoint & schema decomposition,
        parameter extraction, safety guardrails.
        """
        t_start_total = time.perf_counter()
        traces: list[ProcessingStageTrace] = []
        apply_guardrails = enable_guardrails and (not shallow_mode)

        if isinstance(spec_data, bytes):
            raw_bytes = spec_data
            text = raw_bytes.decode("utf-8", errors="replace")
        elif isinstance(spec_data, dict):
            text = json.dumps(spec_data)
            raw_bytes = text.encode("utf-8")
        else:
            text = str(spec_data)
            raw_bytes = text.encode("utf-8")

        file_size_bytes = len(raw_bytes)
        content_hash = hashlib.md5(raw_bytes).hexdigest()

        # Step 1: OpenAPI Specification Parsing & Validation
        t0 = time.perf_counter()
        payload = process_openapi_spec(text, file_name=name)
        meta = payload.metadata
        dt_step1 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=1,
                stage_name="OpenAPI Specification Parsing & Validation",
                status="completed",
                duration_ms=round(dt_step1, 2),
                summary=(
                    f"Parsed OpenAPI/Swagger specification '{name}'. Discovered "
                    f"{meta.total_endpoints} endpoint operation(s) and "
                    f"{meta.total_classes} component schema(s)."
                ),
                details={
                    "format": meta.format,
                    "total_endpoints": meta.total_endpoints,
                    "total_schemas": meta.total_classes,
                },
            )
        )

        # Step 2: Path & Operation Route Discovery
        t0 = time.perf_counter()
        dt_step2 = (time.perf_counter() - t0) * 1000.0
        traces.append(
            ProcessingStageTrace(
                step_number=2,
                stage_name="Path & Operation Route Discovery",
                status="completed",
                duration_ms=round(dt_step2, 2),
                summary=(f"Indexed {meta.total_endpoints} HTTP operation routes across paths."),
                details={
                    "total_endpoints": meta.total_endpoints,
                },
            )
        )

        # Step 3: Component Schema & Parameter Extraction
        t0 = time.perf_counter()
        dt_step3 = (time.perf_counter() - t0) * 1000.0
        traces.append(
            ProcessingStageTrace(
                step_number=3,
                stage_name="Component Schema & Parameter Extraction",
                status="completed",
                duration_ms=round(dt_step3, 2),
                summary=(
                    f"Extracted parameters and response models into {len(payload.chunks)} "
                    "grounded API chunk(s)."
                ),
                details={
                    "total_chunks": len(payload.chunks),
                },
            )
        )

        # Step 4: Safety Guardrails & PII Sanitization
        t0 = time.perf_counter()
        sanitized_chunks: list[tuple[Any, str]] = []
        total_masked_items = 0

        for chk in payload.chunks:
            n_text = chk.narrative_text
            if apply_guardrails and n_text:
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
                    f"Evaluated {len(sanitized_chunks)} API chunk(s) against security policies. "
                    f"Masked {total_masked_items} sensitive item(s)."
                ),
                details={
                    "guardrails_enabled": apply_guardrails,
                    "masked_items": total_masked_items,
                },
            )
        )

        # Step 5: API-Grounded Chunk Assembly
        t0 = time.perf_counter()
        processed_chunks: list[ProcessedChunk] = []

        for idx, (chk, scrubbed_text) in enumerate(sanitized_chunks):
            chunk_meta: dict[str, Any] = {
                "symbol_name": chk.symbol_name,
                "symbol_type": chk.symbol_type,
                "signature": chk.signature,
                "is_openapi": True,
            }
            if chk.metadata:
                chunk_meta.update(chk.metadata)
            if metadata:
                chunk_meta.update(metadata)

            processed_chunks.append(
                ProcessedChunk(
                    chunk_id=f"{spec_id}:{chk.symbol_name}:{idx}",
                    document_id=spec_id,
                    chunk_index=idx,
                    text=scrubbed_text,
                    metadata=chunk_meta,
                )
            )

        dt_step5 = (time.perf_counter() - t0) * 1000.0
        traces.append(
            ProcessingStageTrace(
                step_number=5,
                stage_name="API-Grounded Chunk Assembly",
                status="completed",
                duration_ms=round(dt_step5, 2),
                summary="Assembled final chunks with grounded metadata (vectors are produced at "
                "storage time by embed_texts()).",
                details={},
            )
        )

        doc_meta: dict[str, Any] = {
            "format": meta.format,
            "total_endpoints": meta.total_endpoints,
            "total_schemas": meta.total_classes,
            "total_symbols": meta.total_symbols,
            "is_openapi": True,
        }
        if metadata:
            doc_meta.update(metadata)

        total_ms = (time.perf_counter() - t_start_total) * 1000.0
        summary_msg = (
            f"Processed OpenAPI specification '{name}' ({meta.total_endpoints} endpoints, "
            f"{meta.total_classes} schemas) into {len(processed_chunks)} chunks "
            f"in {total_ms:.1f}ms."
        )

        return ProcessedDocumentPayload(
            document_id=spec_id,
            name=name,
            file_type="openapi",
            file_size_bytes=file_size_bytes,
            content_hash=content_hash,
            classification=doc_meta.get("classification", "openapi_spec"),
            chunks=processed_chunks,
            metadata=doc_meta,
            execution_trace=traces,
            summary=summary_msg,
        )
