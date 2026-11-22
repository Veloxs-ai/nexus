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

"""``NexusClient.process_email``: RFC 822 messages to header, body and attachment chunks.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from nexus.chunk_limits import bounded_output
from nexus.models import ProcessedChunk, ProcessedDocumentPayload, ProcessingStageTrace

try:
    from nexus.processing.email_chat import process_email_binary
except (ImportError, ModuleNotFoundError):
    from nexus_processing.email_chat import process_email_binary

__all__ = ["EmailMixin"]


class EmailMixin:
    """Mixed into ``NexusClient``."""

    @bounded_output
    def process_email(
        self,
        email_id: str,
        name: str,
        email_bytes: bytes | None = None,
        file_path: str | Path | None = None,
        metadata: dict[str, Any] | None = None,
        enable_guardrails: bool = True,
        shallow_mode: bool = False,
        ocr_provider: Any = None,
        auto_extract: bool = True,
    ) -> ProcessedDocumentPayload:
        """Processes an RFC 5322 MIME email message (.eml) through header extraction,
        multipart attachment resolution, chronological reconstruction, PII sanitization.
        """
        t_start_total = time.perf_counter()
        traces: list[ProcessingStageTrace] = []
        apply_guardrails = enable_guardrails and (not shallow_mode)

        if email_bytes is not None:
            raw_data = email_bytes
        elif file_path is not None:
            raw_data = Path(file_path).read_bytes()
        else:
            raise ValueError("Either email_bytes or file_path must be provided to process_email.")

        file_size_bytes = len(raw_data)
        content_hash = hashlib.md5(raw_data).hexdigest()

        # Step 1: MIME Container & Header Graph Parsing
        t0 = time.perf_counter()
        email_payload = process_email_binary(
            raw_data,
            filename=name,
            ocr_provider=ocr_provider,
            auto_extract=auto_extract,
        )
        meta = email_payload.metadata
        dt_step1 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=1,
                stage_name="MIME Container & Header Graph Parsing",
                status="completed",
                duration_ms=round(dt_step1, 2),
                summary=(
                    f"Parsed RFC 5322 headers (From: {meta.sender}, "
                    f"Subject: '{meta.subject}', Date: {meta.date})."
                ),
                details={
                    "sender": meta.sender,
                    "recipients": meta.recipients,
                    "cc": meta.cc,
                    "subject": meta.subject,
                    "date": meta.date,
                    "message_id": meta.message_id,
                },
            )
        )

        # Step 2: Multipart Body & Attachment Graph Extraction
        t0 = time.perf_counter()
        att_count = len(email_payload.attachments)
        dt_step2 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=2,
                stage_name="Multipart Body & Attachment Graph Extraction",
                status="completed",
                duration_ms=round(dt_step2, 2),
                summary=(
                    f"Extracted {len(email_payload.body_plain)} plain characters "
                    f"and discovered {att_count} attachment(s)."
                ),
                details={
                    "plain_chars": len(email_payload.body_plain),
                    "html_chars": len(email_payload.body_html),
                    "attachments": [
                        {"name": a.filename, "type": a.content_type, "size": a.size_bytes}
                        for a in email_payload.attachments
                    ],
                },
            )
        )

        # Step 3: Thread Reference & Chronological Reconstruction
        t0 = time.perf_counter()
        dt_step3 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=3,
                stage_name="Thread Reference & Chronological Reconstruction",
                status="completed",
                duration_ms=round(dt_step3, 2),
                summary=(
                    f"Resolved thread references (In-Reply-To: {bool(meta.in_reply_to)}, "
                    f"References: {len(meta.references)})."
                ),
                details={
                    "in_reply_to": meta.in_reply_to,
                    "references_count": len(meta.references),
                    "chunks_count": len(email_payload.chunks),
                },
            )
        )

        # Step 4: Safety Guardrails & PII Sanitization
        t0 = time.perf_counter()
        sanitized_chunks: list[tuple[Any, str]] = []
        total_masked_items = 0

        for chk in email_payload.chunks:
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
                    f"Applied PII sanitization across {len(sanitized_chunks)} email chunk(s). "
                    f"Masked {total_masked_items} item(s)."
                ),
                details={
                    "guardrails_enabled": apply_guardrails,
                    "masked_items": total_masked_items,
                },
            )
        )

        # Step 5: Email-Grounded Chunk Assembly
        t0 = time.perf_counter()
        processed_chunks: list[ProcessedChunk] = []

        for chk, scrubbed_text in sanitized_chunks:
            chunk_meta: dict[str, Any] = {
                "chunk_index": chk.chunk_index,
                "sender": meta.sender,
                "subject": meta.subject,
                "date": meta.date,
                "message_id": meta.message_id,
                "attachments_count": len(email_payload.attachments),
                "is_email": True,
            }
            if metadata:
                chunk_meta.update(metadata)

            processed_chunks.append(
                ProcessedChunk(
                    chunk_id=f"{email_id}:{chk.chunk_index}",
                    document_id=email_id,
                    chunk_index=chk.chunk_index,
                    text=scrubbed_text,
                    metadata=chunk_meta,
                )
            )

        dt_step5 = (time.perf_counter() - t0) * 1000.0
        traces.append(
            ProcessingStageTrace(
                step_number=5,
                stage_name="Email-Grounded Chunk Assembly",
                status="completed",
                duration_ms=round(dt_step5, 2),
                summary="Assembled final chunks with grounded metadata (vectors are produced at "
                "storage time by embed_texts()).",
                details={},
            )
        )

        doc_meta: dict[str, Any] = {
            "format": meta.format,
            "sender": meta.sender,
            "recipients": meta.recipients,
            "subject": meta.subject,
            "date": meta.date,
            "message_id": meta.message_id,
            "attachments": [
                {
                    "filename": a.filename,
                    "content_type": a.content_type,
                    "size_bytes": a.size_bytes,
                }
                for a in email_payload.attachments
            ],
            "is_email": True,
        }
        if metadata:
            doc_meta.update(metadata)

        total_ms = (time.perf_counter() - t_start_total) * 1000.0
        summary_msg = (
            f"Processed {meta.format} email '{name}' ({len(processed_chunks)} chunks) "
            f"into chunks in {total_ms:.1f}ms."
        )

        return ProcessedDocumentPayload(
            document_id=email_id,
            name=name,
            file_type="email",
            file_size_bytes=file_size_bytes,
            content_hash=content_hash,
            classification=doc_meta.get("classification", "email"),
            chunks=processed_chunks,
            metadata=doc_meta,
            execution_trace=traces,
            summary=summary_msg,
        )
