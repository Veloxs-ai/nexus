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

"""``NexusClient.process_presentation`` and ``process_word_document``: PPTX slides and DOCX
sections to chunks.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from nexus.chunk_limits import bounded_output
from nexus.models import ProcessedChunk, ProcessedDocumentPayload, ProcessingStageTrace

try:
    from nexus.processing.office import (
        group_word_sections,
        process_presentation_binary,
        process_word_binary,
    )
except (ImportError, ModuleNotFoundError):
    from nexus_processing.office import (
        group_word_sections,
        process_presentation_binary,
        process_word_binary,
    )

__all__ = ["OfficeMixin"]


class OfficeMixin:
    """Mixed into ``NexusClient``."""

    @bounded_output
    def process_presentation(
        self,
        presentation_id: str,
        name: str,
        presentation_bytes: bytes | None = None,
        file_path: str | Path | None = None,
        metadata: dict[str, Any] | None = None,
        enable_guardrails: bool = True,
        shallow_mode: bool = False,
        ocr_provider: Any = None,
        auto_extract: bool = True,
    ) -> ProcessedDocumentPayload:
        """Processes a PowerPoint presentation (.pptx) through native pure-Python container
        decompression, slide shape extraction, speaker notes resolution, PII sanitization.
        """
        t_start_total = time.perf_counter()
        traces: list[ProcessingStageTrace] = []
        apply_guardrails = enable_guardrails and (not shallow_mode)

        if presentation_bytes is not None:
            raw_data = presentation_bytes
        elif file_path is not None:
            raw_data = Path(file_path).read_bytes()
        else:
            raise ValueError(
                "Either presentation_bytes or file_path must be provided to process_presentation."
            )

        file_size_bytes = len(raw_data)
        content_hash = hashlib.md5(raw_data).hexdigest()

        # Step 1: OPC Archive Decompression & Slide Graph Discovery
        t0 = time.perf_counter()
        pres_payload = process_presentation_binary(
            raw_data,
            filename=name,
            ocr_provider=ocr_provider,
            auto_extract=auto_extract,
        )
        meta = pres_payload.metadata
        dt_step1 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=1,
                stage_name="OPC Archive Decompression & Slide Graph Discovery",
                status="completed",
                duration_ms=round(dt_step1, 2),
                summary=(
                    f"Discovered presentation graph with {meta.total_slides} ordered slide(s) "
                    f"and {meta.total_words} total words."
                ),
                details={
                    "format": meta.format,
                    "total_slides": meta.total_slides,
                    "slide_titles": meta.slide_titles,
                    "file_size_bytes": file_size_bytes,
                },
            )
        )

        # Step 2: Slide XML & DrawingML Text Extraction
        t0 = time.perf_counter()
        total_shapes = sum(s.shape_count for s in pres_payload.slides)
        dt_step2 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=2,
                stage_name="Slide XML & DrawingML Text Extraction",
                status="completed",
                duration_ms=round(dt_step2, 2),
                summary=(
                    f"Extracted titles and body paragraphs across {total_shapes} shape elements."
                ),
                details={
                    "total_shapes": total_shapes,
                    "slides_count": len(pres_payload.slides),
                },
            )
        )

        # Step 3: Speaker Notes & Hierarchy Resolution
        t0 = time.perf_counter()
        slides_with_notes = sum(1 for s in pres_payload.slides if s.speaker_notes.strip())
        dt_step3 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=3,
                stage_name="Speaker Notes & Hierarchy Resolution",
                status="completed",
                duration_ms=round(dt_step3, 2),
                summary=(
                    f"Resolved speaker notes for {slides_with_notes}/{meta.total_slides} slide(s) "
                    f"and linked contextual narrations."
                ),
                details={
                    "slides_with_notes": slides_with_notes,
                    "total_slides": meta.total_slides,
                },
            )
        )

        # Step 4: Safety Guardrails & PII Sanitization
        t0 = time.perf_counter()
        sanitized_slides: list[tuple[Any, str]] = []
        total_masked_items = 0

        for s in pres_payload.slides:
            n_text = s.narrative_text
            if apply_guardrails and n_text:
                scrubbed_text = self.guardrails.mask_pii(n_text)
                if scrubbed_text != n_text:
                    total_masked_items += 1
            else:
                scrubbed_text = n_text
            sanitized_slides.append((s, scrubbed_text))

        dt_step4 = (time.perf_counter() - t0) * 1000.0
        traces.append(
            ProcessingStageTrace(
                step_number=4,
                stage_name="Safety Guardrails & PII Sanitization",
                status="completed",
                duration_ms=round(dt_step4, 2),
                summary=(
                    f"Applied PII detection across {len(sanitized_slides)} slide(s). "
                    f"Masked {total_masked_items} sensitive items."
                ),
                details={
                    "guardrails_enabled": apply_guardrails,
                    "masked_items": total_masked_items,
                },
            )
        )

        # Step 5: Slide-Grounded Chunk Assembly
        t0 = time.perf_counter()
        processed_chunks: list[ProcessedChunk] = []

        for idx, (s, scrubbed_text) in enumerate(sanitized_slides):
            chunk_meta: dict[str, Any] = {
                "slide_number": s.slide_number,
                "title": s.title,
                "has_speaker_notes": bool(s.speaker_notes.strip()),
                "shape_count": s.shape_count,
                "word_count": s.word_count,
                "is_presentation": True,
            }
            if metadata:
                chunk_meta.update(metadata)

            processed_chunks.append(
                ProcessedChunk(
                    chunk_id=f"{presentation_id}:{s.slide_number - 1}",
                    document_id=presentation_id,
                    chunk_index=idx,
                    text=scrubbed_text,
                    metadata=chunk_meta,
                )
            )

        dt_step5 = (time.perf_counter() - t0) * 1000.0
        traces.append(
            ProcessingStageTrace(
                step_number=5,
                stage_name="Slide-Grounded Chunk Assembly",
                status="completed",
                duration_ms=round(dt_step5, 2),
                summary="Assembled final chunks with grounded metadata (vectors are produced at "
                "storage time by embed_texts()).",
                details={},
            )
        )

        doc_meta: dict[str, Any] = {
            "format": meta.format,
            "total_slides": meta.total_slides,
            "total_words": meta.total_words,
            "slide_titles": meta.slide_titles,
            "is_presentation": True,
        }
        if metadata:
            doc_meta.update(metadata)

        total_ms = (time.perf_counter() - t_start_total) * 1000.0
        summary_msg = (
            f"Processed {meta.format} presentation '{name}' ({meta.total_slides} slides, "
            f"{meta.total_words} words) into {len(processed_chunks)} chunks "
            f"in {total_ms:.1f}ms."
        )

        return ProcessedDocumentPayload(
            document_id=presentation_id,
            name=name,
            file_type="presentation",
            file_size_bytes=file_size_bytes,
            content_hash=content_hash,
            classification=doc_meta.get("classification", "presentation"),
            chunks=processed_chunks,
            metadata=doc_meta,
            execution_trace=traces,
            summary=summary_msg,
        )

    @bounded_output
    def process_word_document(
        self,
        document_id: str | None = None,
        name: str | None = None,
        docx_bytes: bytes | None = None,
        file_path: str | Path | None = None,
        metadata: dict[str, Any] | None = None,
        enable_guardrails: bool = True,
        shallow_mode: bool = False,
        ocr_provider: Any = None,
        auto_extract: bool = True,
        *,
        word_id: str | None = None,
        word_bytes: bytes | None = None,
    ) -> ProcessedDocumentPayload:
        """Processes a Word document (.docx) through native pure-Python container decompression,
        heading hierarchy extraction, paragraph/table framing, PII sanitization.
        """
        t_start_total = time.perf_counter()
        traces: list[ProcessingStageTrace] = []
        apply_guardrails = enable_guardrails and (not shallow_mode)

        doc_id = document_id or word_id or "doc_word"
        doc_name = name or "document.docx"

        if docx_bytes is not None:
            raw_data = docx_bytes
        elif word_bytes is not None:
            raw_data = word_bytes
        elif file_path is not None:
            raw_data = Path(file_path).read_bytes()
        else:
            raise ValueError("Either docx_bytes/word_bytes or file_path must be provided.")

        file_size_bytes = len(raw_data)
        content_hash = hashlib.md5(raw_data).hexdigest()

        # Step 1: OPC Archive Decompression & Document Discovery
        t0 = time.perf_counter()
        word_payload = process_word_binary(
            raw_data,
            filename=doc_name,
            ocr_provider=ocr_provider,
            auto_extract=auto_extract,
        )
        meta = word_payload.metadata
        dt_step1 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=1,
                stage_name="OPC Archive Decompression & Document Discovery",
                status="completed",
                duration_ms=round(dt_step1, 2),
                summary=(
                    f"Decompressed OpenXML Word archive '{doc_name}' ({file_size_bytes}B). "
                    f"Title: '{meta.title or 'Untitled'}', Author: '{meta.author or 'Unknown'}'."
                ),
                details={
                    "format": meta.format,
                    "title": meta.title,
                    "author": meta.author,
                    "file_size_bytes": file_size_bytes,
                },
            )
        )

        # Step 2: Document XML & Heading Hierarchy Parsing
        t0 = time.perf_counter()
        dt_step2 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=2,
                stage_name="Document XML & Heading Hierarchy Parsing",
                status="completed",
                duration_ms=round(dt_step2, 2),
                summary=(
                    f"Traversed Word OpenXML DOM and resolved hierarchical structure: "
                    f"{meta.total_headings} headings, {meta.total_paragraphs} paragraphs, "
                    f"{meta.total_tables} tables."
                ),
                details={
                    "headings": meta.headings,
                    "total_headings": meta.total_headings,
                    "total_paragraphs": meta.total_paragraphs,
                    "total_tables": meta.total_tables,
                },
            )
        )

        # Step 3: Section & Tabular Structure Framing
        t0 = time.perf_counter()
        # Section-sized chunks (heading + its paragraphs/list items); tables stay separate.
        framed_chunks = group_word_sections(word_payload.chunks, name)
        dt_step3 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=3,
                stage_name="Section & Tabular Structure Framing",
                status="completed",
                duration_ms=round(dt_step3, 2),
                summary=(
                    f"Structured document into {len(framed_chunks)} contextual section chunks "
                    f"grounded by heading hierarchy and markdown table representations."
                ),
                details={"chunk_count": len(framed_chunks)},
            )
        )

        # Step 4: Safety Guardrails & PII Sanitization
        t0 = time.perf_counter()
        sanitized_chunks: list[tuple[Any, str]] = []
        total_masked_items = 0

        for chk in framed_chunks:
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
                    f"Scanned {len(sanitized_chunks)} document chunk(s) for PII and "
                    f"sensitive entities. Masked {total_masked_items} sensitive item(s)."
                ),
                details={
                    "guardrails_enabled": apply_guardrails,
                    "masked_items": total_masked_items,
                },
            )
        )

        # Step 5: Document-Grounded Chunk Assembly
        t0 = time.perf_counter()
        processed_chunks: list[ProcessedChunk] = []

        for idx, (chk, scrubbed_text) in enumerate(sanitized_chunks):
            chunk_meta: dict[str, Any] = {
                "section_title": chk.section_title,
                "heading_level": chk.heading_level,
                "item_type": chk.item_type,
                "word_count": chk.word_count,
                "is_word": True,
            }
            if chk.metadata:
                chunk_meta.update(chk.metadata)
            if metadata:
                chunk_meta.update(metadata)

            processed_chunks.append(
                ProcessedChunk(
                    chunk_id=f"{doc_id}:{chk.chunk_id}:{idx}",
                    document_id=doc_id,
                    chunk_index=idx,
                    text=scrubbed_text,
                    metadata=chunk_meta,
                )
            )

        dt_step5 = (time.perf_counter() - t0) * 1000.0
        traces.append(
            ProcessingStageTrace(
                step_number=5,
                stage_name="Document-Grounded Chunk Assembly",
                status="completed",
                duration_ms=round(dt_step5, 2),
                summary="Assembled final chunks with grounded metadata (vectors are produced at "
                "storage time by embed_texts()).",
                details={},
            )
        )

        doc_meta: dict[str, Any] = {
            "format": meta.format,
            "title": meta.title,
            "author": meta.author,
            "total_headings": meta.total_headings,
            "total_paragraphs": meta.total_paragraphs,
            "total_tables": meta.total_tables,
            "total_words": meta.total_words,
            "headings": meta.headings,
            "is_word": True,
        }
        if metadata:
            doc_meta.update(metadata)

        total_ms = (time.perf_counter() - t_start_total) * 1000.0
        summary_msg = (
            f"Processed Word document '{doc_name}' ({meta.total_paragraphs} paragraphs, "
            f"{meta.total_tables} tables, {meta.total_words} words) into "
            f"{len(processed_chunks)} chunks in {total_ms:.1f}ms."
        )

        return ProcessedDocumentPayload(
            document_id=doc_id,
            name=doc_name,
            file_type="word",
            file_size_bytes=file_size_bytes,
            content_hash=content_hash,
            classification=doc_meta.get("classification", "word_document"),
            chunks=processed_chunks,
            metadata=doc_meta,
            execution_trace=traces,
            summary=summary_msg,
        )

    def process_word(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> ProcessedDocumentPayload:
        """Alias for process_word_document."""
        return self.process_word_document(*args, **kwargs)
