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

from __future__ import annotations

import hashlib
import time
import unicodedata
from pathlib import Path
from typing import Any

from nexus.models import (
    NexusConfig,
    ProcessedChunk,
    ProcessedDocumentPayload,
    ProcessingStageTrace,
)

try:
    from nexus.experience.config import AuthConfig, EngagementConfig
    from nexus.experience.config import TenantConfig as ExpTenantConfig
    from nexus.experience.gateway import InMemoryGuardrailsGateway
    from nexus.experience.models import AskRequest, AskResponse, Principal
    from nexus.experience.service import ExperienceService
    from nexus.guardrails.engine import GuardrailsEngine
    from nexus.processing.engine import ProcessingEngine
    from nexus.retrieval.engine import RetrievalEngine
except (ImportError, ModuleNotFoundError):
    from nexus_experience.config import AuthConfig, EngagementConfig
    from nexus_experience.config import TenantConfig as ExpTenantConfig
    from nexus_experience.gateway import InMemoryGuardrailsGateway
    from nexus_experience.models import AskRequest, AskResponse, Principal
    from nexus_experience.service import ExperienceService
    from nexus_guardrails.engine import GuardrailsEngine
    from nexus_processing.engine import ProcessingEngine
    from nexus_retrieval.engine import RetrievalEngine


class NexusClient:
    """Unified in-memory Python library client for the Nexus Enterprise Intelligence Framework.

    Provides high-performance, thread-safe, single-process document processing,
    format-aware chunking, configurable PII scrubbing, 3072D vector generation,
    semantic retrieval, execution telemetry traces, and grounded guardrail Q&A
    with zero disk I/O.
    """

    def __init__(
        self,
        config: NexusConfig | None = None,
        base_dir: Path | None = None,
        tenant_id: str = "default",
        in_memory_only: bool = True,
        processing_engine: ProcessingEngine | None = None,
        retrieval_engine: RetrievalEngine | None = None,
        guardrails_engine: GuardrailsEngine | None = None,
        experience_service: ExperienceService | None = None,
    ) -> None:
        self.config = config
        self.base_dir = base_dir or Path.cwd()
        self.tenant_id = tenant_id
        self.in_memory_only = in_memory_only

        self.processing = processing_engine or ProcessingEngine()
        self.retrieval = retrieval_engine or RetrievalEngine(
            base_dir=self.base_dir,
            in_memory_only=self.in_memory_only,
        )
        self.guardrails = guardrails_engine or GuardrailsEngine(
            base_dir=self.base_dir,
            retrieval_engine=self.retrieval,
        )

        if experience_service is not None:
            self.experience = experience_service
        else:
            exp_config = EngagementConfig(
                tenant=ExpTenantConfig(id=self.tenant_id, display_name=f"Tenant {self.tenant_id}"),
                auth=AuthConfig(enabled=False),
            )
            gateway = InMemoryGuardrailsGateway(self.guardrails)
            self.experience = ExperienceService(exp_config, gateway)

    def process_document(
        self,
        document_id: str,
        name: str,
        text: str,
        file_type: str | None = None,
        metadata: dict[str, Any] | None = None,
        enable_guardrails: bool = True,
        shallow_mode: bool = False,
    ) -> ProcessedDocumentPayload:
        """Pipeline raw text through format-aware chunking, optional PII
        masking, and 3072D vector projection.

        Args:
            document_id: Unique identifier for the document.
            name: Filename or table descriptor.
            text: Raw extracted text payload.
            file_type: Extension or format ('csv', 'json', 'md', 'txt', 'pdf').
            metadata: Custom metadata dictionary to attach to document and chunks.
            enable_guardrails: When True (default), applies PII detection and
                regex masking (Luhn cards, emails, SSNs).
                               When False, preserves exact verbatim text without any masking.
            shallow_mode: Alias for bypassing PII masking for internal reviews.

        Returns:
            ProcessedDocumentPayload with chunks, embeddings, execution trace, and metadata.
        """
        t_start_total = time.perf_counter()
        traces: list[ProcessingStageTrace] = []
        apply_guardrails = enable_guardrails and (not shallow_mode)

        # -------------------------------------------------------------------------
        # Step 1: Text Normalization & Hash Computation (0% - 20%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        detected_format = (file_type or Path(name).suffix.removeprefix(".") or "text").lower()
        clean_text = text.replace("\r\n", "\n").replace("\r", "\n")
        normalized_text = unicodedata.normalize("NFKC", clean_text)
        file_size_bytes = len(normalized_text.encode("utf-8"))
        content_hash = hashlib.md5(normalized_text.encode("utf-8")).hexdigest()
        dt_step1 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=1,
                stage_name="Document Ingestion & UTF-8 Normalization",
                status="completed",
                duration_ms=round(dt_step1, 2),
                summary=(
                    f"Normalized {file_size_bytes} bytes of UTF-8 content "
                    f"for format '{detected_format}'. "
                    f"Computed MD5: {content_hash[:8]}..."
                ),
                details={
                    "detected_format": detected_format,
                    "size_bytes": file_size_bytes,
                    "content_hash": content_hash,
                },
            )
        )

        # -------------------------------------------------------------------------
        # Step 2: Format-Aware Structural Chunking (20% - 40%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        raw_chunks = self.processing.chunk_document(normalized_text, file_type=detected_format)
        if not raw_chunks:
            raw_chunks = [normalized_text] if normalized_text.strip() else []
        dt_step2 = (time.perf_counter() - t0) * 1000.0

        chunk_desc = (
            "CSV row narratives"
            if detected_format == "csv"
            else ("JSON object blocks" if detected_format == "json" else "semantic paragraphs")
        )
        traces.append(
            ProcessingStageTrace(
                step_number=2,
                stage_name="Format-Aware Structural Chunking",
                status="completed",
                duration_ms=round(dt_step2, 2),
                summary=f"Generated {len(raw_chunks)} {chunk_desc} preserving contextual layout.",
                details={"chunk_count": len(raw_chunks), "strategy": chunk_desc},
            )
        )

        # -------------------------------------------------------------------------
        # Step 3: Document Metadata & Classification Extraction (40% - 60%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        doc_metadata = self.processing.extract_metadata(normalized_text)
        if metadata:
            doc_metadata.update(metadata)
        doc_metadata["file_type"] = detected_format
        doc_metadata["source_format"] = detected_format
        doc_metadata["is_tabular"] = detected_format == "csv"
        doc_metadata["guardrails_enabled"] = apply_guardrails
        classification = doc_metadata.get("classification", "general")
        dt_step3 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=3,
                stage_name="Metadata & Entity Classification",
                status="completed",
                duration_ms=round(dt_step3, 2),
                summary=(
                    f"Classified as '{classification}'. "
                    f"Extracted {len(doc_metadata.get('entities', []))} entities "
                    f"and {len(doc_metadata.get('tags', []))} domain tags."
                ),
                details={
                    "classification": classification,
                    "entities_count": len(doc_metadata.get("entities", [])),
                    "tags": doc_metadata.get("tags", []),
                },
            )
        )

        # -------------------------------------------------------------------------
        # Step 4: Safety Guardrails & PII Masking (60% - 80%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        cleaned_chunks_text: list[str] = []
        total_redacted = 0
        for chunk_txt in raw_chunks:
            if not apply_guardrails:
                cleaned_chunks_text.append(chunk_txt)
            else:
                masked = self.guardrails.mask_pii(chunk_txt)
                if masked != chunk_txt:
                    total_redacted += 1
                cleaned_chunks_text.append(masked)
        dt_step4 = (time.perf_counter() - t0) * 1000.0

        guardrails_summary = (
            f"Evaluated {len(raw_chunks)} chunks through PII scrubbers "
            f"(Luhn credit cards, emails, SSNs). "
            f"Redacted items in {total_redacted} chunk(s)."
            if apply_guardrails
            else "Safety guardrails bypassed: preserving raw verbatim text without redaction."
        )

        traces.append(
            ProcessingStageTrace(
                step_number=4,
                stage_name="Safety Guardrails & PII Sanitization",
                status="completed",
                duration_ms=round(dt_step4, 2),
                summary=guardrails_summary,
                details={"guardrails_enabled": apply_guardrails, "chunks_with_pii": total_redacted},
            )
        )

        # -------------------------------------------------------------------------
        # Step 5: 3072-Dimensional Vector Projection (80% - 100%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        processed_chunks: list[ProcessedChunk] = []
        for idx, cleaned_chunk in enumerate(cleaned_chunks_text):
            chunk_meta = self.processing.extract_metadata(cleaned_chunk)
            chunk_meta["document_id"] = document_id
            chunk_meta["document_name"] = name
            chunk_meta["classification"] = classification
            chunk_meta["file_type"] = detected_format
            chunk_meta["source_format"] = detected_format
            chunk_meta["is_tabular"] = detected_format == "csv"
            chunk_meta["guardrails_enabled"] = apply_guardrails
            chunk_meta["content_hash"] = hashlib.md5(cleaned_chunk.encode("utf-8")).hexdigest()

            # Generate pure 3072D normalized float array (L2 = 1.0)
            embedding = self.retrieval.embed(cleaned_chunk)

            chunk_id = f"{document_id}:{idx}"
            processed_chunks.append(
                ProcessedChunk(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    chunk_index=idx,
                    text=cleaned_chunk,
                    metadata=chunk_meta,
                    embedding=embedding,
                )
            )
        dt_step5 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=5,
                stage_name="3072D Multi-Gram Vector Projection",
                status="completed",
                duration_ms=round(dt_step5, 2),
                summary=(
                    f"Projected {len(processed_chunks)} normalized 3072-dimensional "
                    f"vector embeddings (Unigrams, Bigrams, Trigrams, L2 Norm = 1.0)."
                ),
                details={"vector_dimensions": 3072, "total_vectors": len(processed_chunks)},
            )
        )

        total_ms = (time.perf_counter() - t_start_total) * 1000.0
        summary_msg = (
            f"Successfully processed '{name}' into {len(processed_chunks)} "
            f"vector(3072) chunks in {total_ms:.1f}ms."
        )

        return ProcessedDocumentPayload(
            document_id=document_id,
            name=name,
            file_type=detected_format,
            file_size_bytes=file_size_bytes,
            content_hash=content_hash,
            classification=classification,
            chunks=processed_chunks,
            metadata=doc_metadata,
            execution_trace=traces,
            summary=summary_msg,
        )

    def index_document(
        self,
        payload: ProcessedDocumentPayload,
        collection: str = "general",
    ) -> None:
        """Index a processed document payload into the thread-safe in-memory
        vector store, lexical index, and knowledge graph.
        """
        for chunk in payload.chunks:
            self.retrieval.add_entry(
                doc_id=chunk.chunk_id,
                text=chunk.text,
                collection=collection,
                metadata=chunk.metadata,
                embedding=chunk.embedding,
            )

    def ask(
        self,
        query: str,
        channel: str = "assistant",
        user_id: str = "default_user",
        tenant_id: str | None = None,
        session_id: str | None = None,
    ) -> AskResponse:
        """Runs grounded RAG with safety guardrails in-memory without subprocess latency."""
        active_tenant = tenant_id or self.tenant_id
        principal = Principal(
            user_id=user_id,
            tenant_id=active_tenant,
            role="analyst",
            permissions=["ask", "session"],
        )
        request = AskRequest(
            query=query,
            channel=channel,
            session_id=session_id,
        )
        return self.experience.ask(principal, request)

    def search(self, query: str, limit: int = 10):
        """Performs hybrid retrieval over indexed documents."""
        return self.retrieval.search(query, limit=limit)

    def embed(self, text: str) -> list[float]:
        """Generates a pure 3072-dimensional normalized embedding vector."""
        return self.retrieval.embed(text)
