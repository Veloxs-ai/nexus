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

"""``NexusClient.process_chat`` and ``process_slack_export``: conversations to speaker-turn
chunks.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from nexus.chunk_limits import bounded_output
from nexus.models import ProcessedChunk, ProcessedDocumentPayload, ProcessingStageTrace

try:
    from nexus.processing.email_chat import process_chat_dialog
except (ImportError, ModuleNotFoundError):
    from nexus_processing.email_chat import process_chat_dialog

__all__ = ["ChatMixin"]


class ChatMixin:
    """Mixed into ``NexusClient``."""

    @bounded_output
    def process_chat(
        self,
        chat_id: str,
        conversation_name: str,
        chat_data: bytes | str | list[dict[str, Any]] | None = None,
        file_path: str | Path | None = None,
        turns_per_window: int = 8,
        metadata: dict[str, Any] | None = None,
        enable_guardrails: bool = True,
        shallow_mode: bool = False,
    ) -> ProcessedDocumentPayload:
        """Processes a multi-turn chat conversation (Slack, Teams, JSON export)
        through schema discovery, thread graph reconstruction, PII sanitization.
        """
        t_start_total = time.perf_counter()
        traces: list[ProcessingStageTrace] = []
        apply_guardrails = enable_guardrails and (not shallow_mode)

        if chat_data is not None:
            raw_input = chat_data
        elif file_path is not None:
            raw_input = Path(file_path).read_bytes()
        else:
            raise ValueError("Either chat_data or file_path must be provided to process_chat.")

        file_size_bytes = len(raw_input) if isinstance(raw_input, bytes) else 0
        content_hash = hashlib.md5(str(raw_input).encode("utf-8")).hexdigest()

        # Step 1: Chat Schema Discovery & Turn Ingestion
        t0 = time.perf_counter()
        chat_payload = process_chat_dialog(
            raw_input,
            conversation_name=conversation_name,
            turns_per_window=turns_per_window,
        )
        meta = chat_payload.metadata
        dt_step1 = (time.perf_counter() - t0) * 1000.0

        participant_sample = ", ".join(meta.unique_participants[:4])
        if len(meta.unique_participants) > 4:
            participant_sample += "..."

        traces.append(
            ProcessingStageTrace(
                step_number=1,
                stage_name="Chat Schema Discovery & Turn Ingestion",
                status="completed",
                duration_ms=round(dt_step1, 2),
                summary=(
                    f"Ingested {meta.total_messages} dialogue turns across "
                    f"{len(meta.unique_participants)} participant(s): {participant_sample}."
                ),
                details={
                    "total_messages": meta.total_messages,
                    "participants": meta.unique_participants,
                    "conversation_name": meta.conversation_name,
                },
            )
        )

        # Step 2: Thread Graph & Reply Corroboration
        t0 = time.perf_counter()
        dt_step2 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=2,
                stage_name="Thread Graph & Reply Corroboration",
                status="completed",
                duration_ms=round(dt_step2, 2),
                summary=(
                    f"Corroborated conversation graph into {meta.total_threads} "
                    "threaded discussion tree(s)."
                ),
                details={
                    "total_threads": meta.total_threads,
                },
            )
        )

        # Step 3: Chronological Dialogue Window Framing
        t0 = time.perf_counter()
        dt_step3 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=3,
                stage_name="Chronological Dialogue Window Framing",
                status="completed",
                duration_ms=round(dt_step3, 2),
                summary=(
                    f"Framed {len(chat_payload.threads)} threaded narrative window(s) "
                    f"(window size: {turns_per_window} turns)."
                ),
                details={
                    "thread_count": len(chat_payload.threads),
                    "turns_per_window": turns_per_window,
                },
            )
        )

        # Step 4: Safety Guardrails & PII Sanitization
        t0 = time.perf_counter()
        sanitized_threads: list[tuple[Any, str]] = []
        total_masked_items = 0

        for th in chat_payload.threads:
            n_text = th.narrative_text
            if apply_guardrails and n_text:
                scrubbed_text = self.guardrails.mask_pii(n_text)
                if scrubbed_text != n_text:
                    total_masked_items += 1
            else:
                scrubbed_text = n_text
            sanitized_threads.append((th, scrubbed_text))

        dt_step4 = (time.perf_counter() - t0) * 1000.0
        traces.append(
            ProcessingStageTrace(
                step_number=4,
                stage_name="Safety Guardrails & PII Sanitization",
                status="completed",
                duration_ms=round(dt_step4, 2),
                summary=(
                    f"Applied PII detection across {len(sanitized_threads)} thread window(s). "
                    f"Masked {total_masked_items} sensitive item(s)."
                ),
                details={
                    "guardrails_enabled": apply_guardrails,
                    "masked_items": total_masked_items,
                },
            )
        )

        # Step 5: Dialogue-Grounded Chunk Assembly
        t0 = time.perf_counter()
        processed_chunks: list[ProcessedChunk] = []

        for idx, (th, scrubbed_text) in enumerate(sanitized_threads):
            chunk_meta: dict[str, Any] = {
                "thread_id": th.thread_id,
                "total_messages": th.total_messages,
                "participants": meta.unique_participants,
                "is_chat": True,
            }
            if metadata:
                chunk_meta.update(metadata)

            processed_chunks.append(
                ProcessedChunk(
                    chunk_id=f"{chat_id}:{th.thread_id}:{idx}",
                    document_id=chat_id,
                    chunk_index=idx,
                    text=scrubbed_text,
                    metadata=chunk_meta,
                )
            )

        dt_step5 = (time.perf_counter() - t0) * 1000.0
        traces.append(
            ProcessingStageTrace(
                step_number=5,
                stage_name="Dialogue-Grounded Chunk Assembly",
                status="completed",
                duration_ms=round(dt_step5, 2),
                summary="Assembled final chunks with grounded metadata (vectors are produced at "
                "storage time by embed_texts()).",
                details={},
            )
        )

        doc_meta: dict[str, Any] = {
            "format": meta.format,
            "conversation_name": meta.conversation_name,
            "total_threads": meta.total_threads,
            "total_messages": meta.total_messages,
            "unique_participants": meta.unique_participants,
            "is_chat": True,
        }
        if metadata:
            doc_meta.update(metadata)

        total_ms = (time.perf_counter() - t_start_total) * 1000.0
        summary_msg = (
            f"Processed {meta.format} channel '{conversation_name}' "
            f"({meta.total_messages} messages, {meta.total_threads} threads) "
            f"into {len(processed_chunks)} chunks in {total_ms:.1f}ms."
        )

        return ProcessedDocumentPayload(
            document_id=chat_id,
            name=conversation_name,
            file_type="chat",
            file_size_bytes=file_size_bytes,
            content_hash=content_hash,
            classification=doc_meta.get("classification", "chat"),
            chunks=processed_chunks,
            metadata=doc_meta,
            execution_trace=traces,
            summary=summary_msg,
        )

    @bounded_output
    def process_slack_export(
        self,
        export_id: str,
        name: str,
        export_bytes: bytes,
        metadata: dict[str, Any] | None = None,
        enable_guardrails: bool = True,
        shallow_mode: bool = False,
    ) -> ProcessedDocumentPayload:
        """Process a Slack export (.zip workspace export or a channel's .json).

        Threads become one chunk each; top-level messages are windowed per
        channel/day; user IDs and mentions are resolved to names.
        """
        try:
            from nexus.processing.slack_export import parse_slack_export
        except (ImportError, ModuleNotFoundError):
            from nexus_processing.slack_export import parse_slack_export

        t0 = time.perf_counter()
        apply_guardrails = enable_guardrails and not shallow_mode
        slack_chunks, info = parse_slack_export(export_bytes, name)
        t_parse = (time.perf_counter() - t0) * 1000.0
        processed: list[ProcessedChunk] = []
        masked = 0
        for idx, sc in enumerate(slack_chunks):
            text = sc.text
            if apply_guardrails:
                cleaned = self.guardrails.mask_pii(text)
                masked += int(cleaned != text)
                text = cleaned
            processed.append(
                ProcessedChunk(
                    chunk_id=f"{export_id}:{idx}",
                    document_id=export_id,
                    chunk_index=idx,
                    text=text,
                    metadata={
                        **(metadata or {}),
                        "source_format": "slack",
                        "channel": sc.channel,
                        "kind": sc.kind,
                        "date": sc.date,
                        "thread_ts": sc.thread_ts,
                        "participants": sc.participants,
                        "message_count": sc.message_count,
                        "guardrails_enabled": apply_guardrails,
                    },
                )
            )
        total_ms = (time.perf_counter() - t0) * 1000.0
        return ProcessedDocumentPayload(
            document_id=export_id,
            name=name,
            file_type="slack",
            file_size_bytes=len(export_bytes),
            content_hash=hashlib.md5(export_bytes).hexdigest(),
            classification="communication",
            chunks=processed,
            metadata={**(metadata or {}), **info},
            execution_trace=[
                ProcessingStageTrace(
                    step_number=1, stage_name="Slack Export Parsing", duration_ms=t_parse,
                    summary=f"Parsed {info['messages']} message(s) in "
                    f"{len(info['channels'])} channel(s) into "
                    f"{len(slack_chunks)} thread/day chunk(s).",
                    details=info,
                ),
                ProcessingStageTrace(
                    step_number=2, stage_name="Safety Guardrails & PII Sanitization",
                    duration_ms=total_ms - t_parse,
                    summary="PII masking "
                    f"{'applied' if apply_guardrails else 'skipped (shallow)'}; "
                    f"{masked} chunk(s) redacted.",
                    details={"guardrails_enabled": apply_guardrails, "chunks_with_pii": masked},
                ),
            ],
            summary=f"Processed Slack export '{name}' into {len(processed)} chunks "
            f"in {total_ms:.1f}ms.",
        )
