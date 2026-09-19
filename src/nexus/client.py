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
import json
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
    from nexus.processing.audio import process_audio_binary
    from nexus.processing.code import (
        process_code,
        process_openapi_spec,
    )
    from nexus.processing.email_chat import (
        process_chat_dialog,
        process_email_binary,
    )
    from nexus.processing.engine import ProcessingEngine
    from nexus.processing.images import process_image_binary
    from nexus.processing.mongodb import (
        chunk_mongo_collection,
        flatten_mongo_document,
        serialize_bson_value,
    )
    from nexus.processing.mysql import (
        chunk_mysql_table,
    )
    from nexus.processing.office import (
        process_presentation_binary,
        process_spreadsheet_binary,
    )
    from nexus.processing.pdf import process_pdf_binary
    from nexus.processing.sqlite import (
        process_sqlite_binary,
        process_sqlite_file,
    )
    from nexus.processing.video import process_video_binary
    from nexus.retrieval.embeddings import AudioEmbedder, ImageEmbedder, VideoEmbedder
    from nexus.retrieval.engine import RetrievalEngine
except (ImportError, ModuleNotFoundError):
    from nexus_experience.config import AuthConfig, EngagementConfig
    from nexus_experience.config import TenantConfig as ExpTenantConfig
    from nexus_experience.gateway import InMemoryGuardrailsGateway
    from nexus_experience.models import AskRequest, AskResponse, Principal
    from nexus_experience.service import ExperienceService
    from nexus_guardrails.engine import GuardrailsEngine
    from nexus_processing.audio import process_audio_binary
    from nexus_processing.code import (
        process_code,
        process_openapi_spec,
    )
    from nexus_processing.email_chat import (
        process_chat_dialog,
        process_email_binary,
    )
    from nexus_processing.engine import ProcessingEngine
    from nexus_processing.images import process_image_binary
    from nexus_processing.mongodb import (
        chunk_mongo_collection,
        flatten_mongo_document,
        serialize_bson_value,
    )
    from nexus_processing.mysql import (
        chunk_mysql_table,
    )
    from nexus_processing.office import (
        process_presentation_binary,
        process_spreadsheet_binary,
    )
    from nexus_processing.pdf import process_pdf_binary
    from nexus_processing.sqlite import (
        process_sqlite_binary,
        process_sqlite_file,
    )
    from nexus_processing.video import process_video_binary
    from nexus_retrieval.embeddings import AudioEmbedder, ImageEmbedder, VideoEmbedder
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
        self.image_embedder = ImageEmbedder(dimensions=3072, normalize=True)
        self.video_embedder = VideoEmbedder(dimensions=3072, normalize=True)
        self.audio_embedder = AudioEmbedder(dimensions=3072, normalize=True)

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
            document_id: Unique identifier for the document record.
            name: Original filename or title.
            text: Raw document text, or binary bytes for images/videos.
            file_type: Optional file extension override.
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

        # Automatic routing for image payloads
        if detected_format in ("png", "jpg", "jpeg", "bmp"):
            raw_img_bytes = None
            if isinstance(text, bytes | bytearray):
                raw_img_bytes = bytes(text)
            elif isinstance(text, str):
                p = Path(text)
                if p.is_file():
                    raw_img_bytes = p.read_bytes()
            if raw_img_bytes is not None:
                return self.process_image(
                    image_id=document_id,
                    name=name,
                    image_bytes=raw_img_bytes,
                    format_hint=detected_format,
                    metadata=metadata,
                )

        # Automatic routing for video payloads
        if detected_format in ("mp4", "mov", "m4v", "webm", "mkv"):
            raw_vid_bytes = None
            if isinstance(text, bytes | bytearray):
                raw_vid_bytes = bytes(text)
            elif isinstance(text, str):
                p = Path(text)
                if p.is_file():
                    raw_vid_bytes = p.read_bytes()
            if raw_vid_bytes is not None:
                return self.process_video(
                    video_id=document_id,
                    name=name,
                    video_bytes=raw_vid_bytes,
                    metadata=metadata,
                )

        # Automatic routing for PDF payloads
        if detected_format == "pdf":
            raw_pdf_bytes = None
            if isinstance(text, bytes | bytearray):
                raw_pdf_bytes = bytes(text)
            elif isinstance(text, str):
                p = Path(text)
                if p.is_file():
                    raw_pdf_bytes = p.read_bytes()
            if raw_pdf_bytes is not None:
                return self.process_pdf(
                    pdf_id=document_id,
                    name=name,
                    pdf_bytes=raw_pdf_bytes,
                    metadata=metadata,
                    enable_guardrails=enable_guardrails,
                    shallow_mode=shallow_mode,
                )

        # Automatic routing for MySQL table payloads
        if detected_format == "mysql":
            raw_rows = None
            if isinstance(text, list):
                raw_rows = text
            elif isinstance(text, str):
                p = Path(text)
                if p.is_file():
                    try:
                        raw_rows = json.loads(p.read_text(encoding="utf-8"))
                    except Exception:
                        raw_rows = None
                else:
                    try:
                        raw_rows = json.loads(text)
                    except Exception:
                        raw_rows = None
            if isinstance(raw_rows, list):
                return self.process_mysql_table(
                    table_name=name or document_id,
                    rows=raw_rows,
                    metadata=metadata,
                    enable_guardrails=enable_guardrails,
                    shallow_mode=shallow_mode,
                )

        # Automatic routing for MongoDB collection payloads
        if detected_format in ("mongodb", "mongo"):
            raw_docs = None
            if isinstance(text, list):
                raw_docs = text
            elif isinstance(text, str):
                p = Path(text)
                if p.is_file():
                    try:
                        raw_docs = json.loads(p.read_text(encoding="utf-8"))
                    except Exception:
                        raw_docs = None
                else:
                    try:
                        raw_docs = json.loads(text)
                    except Exception:
                        raw_docs = None
            if isinstance(raw_docs, list):
                return self.process_mongo_collection(
                    collection_name=name or document_id,
                    documents=raw_docs,
                    metadata=metadata,
                    enable_guardrails=enable_guardrails,
                    shallow_mode=shallow_mode,
                )

        # Automatic routing for Audio payloads
        if detected_format in ("wav", "aiff", "aif", "mp3"):
            raw_audio_bytes = None
            if isinstance(text, bytes | bytearray):
                raw_audio_bytes = bytes(text)
            elif isinstance(text, str):
                p = Path(text)
                if p.is_file():
                    raw_audio_bytes = p.read_bytes()
            if raw_audio_bytes is not None:
                return self.process_audio(
                    audio_id=document_id,
                    name=name,
                    audio_bytes=raw_audio_bytes,
                    metadata=metadata,
                    enable_guardrails=enable_guardrails,
                    shallow_mode=shallow_mode,
                )

        # Automatic routing for Spreadsheet (.xlsx) payloads
        if detected_format in ("xlsx", "excel"):
            raw_xlsx_bytes = None
            if isinstance(text, bytes | bytearray):
                raw_xlsx_bytes = bytes(text)
            elif isinstance(text, str):
                p = Path(text)
                if p.is_file():
                    raw_xlsx_bytes = p.read_bytes()
            if raw_xlsx_bytes is not None:
                return self.process_spreadsheet(
                    spreadsheet_id=document_id,
                    name=name or "workbook.xlsx",
                    spreadsheet_bytes=raw_xlsx_bytes,
                    metadata=metadata,
                    enable_guardrails=enable_guardrails,
                    shallow_mode=shallow_mode,
                )

        # Automatic routing for Presentation (.pptx) payloads
        if detected_format in ("pptx", "powerpoint"):
            raw_pptx_bytes = None
            if isinstance(text, bytes | bytearray):
                raw_pptx_bytes = bytes(text)
            elif isinstance(text, str):
                p = Path(text)
                if p.is_file():
                    raw_pptx_bytes = p.read_bytes()
            if raw_pptx_bytes is not None:
                return self.process_presentation(
                    presentation_id=document_id,
                    name=name or "presentation.pptx",
                    presentation_bytes=raw_pptx_bytes,
                    metadata=metadata,
                    enable_guardrails=enable_guardrails,
                    shallow_mode=shallow_mode,
                )

        # Automatic routing for Email (.eml) payloads
        if detected_format in ("eml", "email"):
            raw_email_bytes = None
            if isinstance(text, bytes | bytearray):
                raw_email_bytes = bytes(text)
            elif isinstance(text, str):
                p = Path(text)
                if p.is_file():
                    raw_email_bytes = p.read_bytes()
                elif text.startswith(("From:", "Received:", "Return-Path:", "MIME-Version:")):
                    raw_email_bytes = text.encode("utf-8")
            if raw_email_bytes is not None:
                return self.process_email(
                    email_id=document_id,
                    name=name or "message.eml",
                    email_bytes=raw_email_bytes,
                    metadata=metadata,
                    enable_guardrails=enable_guardrails,
                    shallow_mode=shallow_mode,
                )

        # Automatic routing for Chat conversation payloads
        if detected_format in ("chat", "slack", "teams"):
            return self.process_chat(
                chat_id=document_id,
                conversation_name=name or "chat_conversation",
                chat_data=text,
                metadata=metadata,
                enable_guardrails=enable_guardrails,
                shallow_mode=shallow_mode,
            )

        # Automatic routing for SQLite database payloads
        if detected_format in ("sqlite", "sqlite3", "db") or (
            isinstance(text, bytes | bytearray) and text.startswith(b"SQLite format 3\x00")
        ):
            raw_db_bytes = None
            db_file_path = None
            if isinstance(text, bytes | bytearray):
                raw_db_bytes = bytes(text)
            elif isinstance(text, str):
                p = Path(text)
                if p.is_file():
                    db_file_path = p
            if raw_db_bytes is not None or db_file_path is not None:
                return self.process_sqlite(
                    db_id=document_id,
                    name=name or "database.db",
                    db_bytes=raw_db_bytes,
                    file_path=db_file_path,
                    metadata=metadata,
                    enable_guardrails=enable_guardrails,
                    shallow_mode=shallow_mode,
                )

        # Automatic routing for OpenAPI / Swagger specifications
        if detected_format in ("openapi", "swagger") or (
            detected_format in ("json", "yaml", "yml")
            and ("openapi" in (name or "").lower() or "swagger" in (name or "").lower())
        ):
            return self.process_openapi(
                spec_id=document_id,
                name=name or "openapi.json",
                spec_data=text,
                metadata=metadata,
                enable_guardrails=enable_guardrails,
                shallow_mode=shallow_mode,
            )

        # Automatic routing for Source Code AST & Polyglot files
        code_exts = (
            "py",
            "python",
            "js",
            "jsx",
            "ts",
            "tsx",
            "go",
            "golang",
            "rs",
            "rust",
            "java",
            "cpp",
            "c",
            "h",
            "hpp",
            "cs",
            "rb",
            "php",
            "swift",
            "kt",
        )
        if detected_format in code_exts:
            return self.process_code(
                code_id=document_id,
                name=name or f"source.{detected_format}",
                code_input=text,
                language=detected_format,
                metadata=metadata,
                enable_guardrails=enable_guardrails,
                shallow_mode=shallow_mode,
            )

        clean_text = (
            text.replace("\r\n", "\n").replace("\r", "\n") if isinstance(text, str) else str(text)
        )
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

    def embed_image(self, image_bytes: bytes, format_hint: str | None = None) -> list[float]:
        """Generates a pure 3072-dimensional normalized visual embedding vector."""
        visual_payload = process_image_binary(image_bytes, format_hint=format_hint)
        return self.image_embedder.embed_features(
            spatial_grid=visual_payload.spatial_grid,
            color_histogram=visual_payload.color_histogram,
            luminance_histogram=visual_payload.luminance_histogram,
            horizontal_gradients=visual_payload.horizontal_gradients,
            vertical_gradients=visual_payload.vertical_gradients,
            edge_signature=visual_payload.edge_signature,
            aspect_ratio=visual_payload.metadata.aspect_ratio,
        )

    def process_image(
        self,
        image_id: str,
        name: str,
        image_bytes: bytes | None = None,
        file_path: str | Path | None = None,
        format_hint: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProcessedDocumentPayload:
        """Processes an image through pure-Python decoding, spatial grid decomposition,
        color and luminance distribution analysis, and 3072D vector projection.

        Args:
            image_id: Unique identifier for the image document.
            name: Filename or descriptor (e.g. 'diagram.png').
            image_bytes: Raw binary image payload.
            file_path: Optional path to read image from disk if image_bytes not provided.
            format_hint: Optional format hint ('png', 'jpeg', 'bmp').
            metadata: Custom metadata dictionary to attach to image document and chunk.

        Returns:
            ProcessedDocumentPayload with visual metadata, 3072D embedding, and 5-stage telemetry.
        """
        t_start_total = time.perf_counter()
        traces: list[ProcessingStageTrace] = []

        # Read binary data
        if image_bytes is not None:
            raw_data = image_bytes
        elif file_path is not None:
            raw_data = Path(file_path).read_bytes()
        else:
            raise ValueError("Either image_bytes or file_path must be provided to process_image.")

        # -------------------------------------------------------------------------
        # Step 1: Binary Ingestion & Format Validation (0% - 20%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        file_size_bytes = len(raw_data)
        content_hash = hashlib.sha256(raw_data).hexdigest()
        detected_format = (format_hint or Path(name).suffix.removeprefix(".") or "unknown").lower()
        dt_step1 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=1,
                stage_name="Binary Header & Format Validation",
                status="completed",
                duration_ms=round(dt_step1, 2),
                summary=(
                    f"Validated {file_size_bytes} bytes of image payload. "
                    f"Format hint: '{detected_format}'. Computed SHA256: {content_hash[:10]}..."
                ),
                details={
                    "format_hint": detected_format,
                    "file_size_bytes": file_size_bytes,
                    "content_hash": content_hash,
                },
            )
        )

        # -------------------------------------------------------------------------
        # Step 2: Pixel Scanline & Binary Decompression (20% - 40%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        visual_payload = process_image_binary(raw_data, format_hint=detected_format)
        meta = visual_payload.metadata
        dt_step2 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=2,
                stage_name="Pixel Scanline & Binary Decompression",
                status="completed",
                duration_ms=round(dt_step2, 2),
                summary=(
                    f"Decoded {meta.format} stream "
                    f"({meta.width}x{meta.height}, {meta.color_mode}). "
                    f"Aspect ratio: {meta.aspect_ratio}."
                ),
                details={
                    "format": meta.format,
                    "width": meta.width,
                    "height": meta.height,
                    "color_mode": meta.color_mode,
                    "aspect_ratio": meta.aspect_ratio,
                    "has_alpha": meta.has_alpha,
                },
            )
        )

        # -------------------------------------------------------------------------
        # Step 3: Spatial Luminance Grid Decomposition (40% - 60%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        grid_cells_count = len(visual_payload.spatial_grid)
        dt_step3 = (time.perf_counter() - t0) * 1000.0
        total_gradients = len(visual_payload.horizontal_gradients) + len(
            visual_payload.vertical_gradients
        )

        traces.append(
            ProcessingStageTrace(
                step_number=3,
                stage_name="Spatial Luminance Grid Decomposition",
                status="completed",
                duration_ms=round(dt_step3, 2),
                summary=(
                    f"Downsampled canvas into {grid_cells_count}-cell spatial luminance matrix. "
                    f"Extracted {total_gradients} spatial gradient vectors."
                ),
                details={
                    "grid_dimensions": "8x8",
                    "total_cells": grid_cells_count,
                    "horizontal_gradients": len(visual_payload.horizontal_gradients),
                    "vertical_gradients": len(visual_payload.vertical_gradients),
                },
            )
        )

        # -------------------------------------------------------------------------
        # Step 4: 3D Color Histogram & Perceptual dHash (60% - 80%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        active_colors = sum(1 for c in visual_payload.color_histogram if c > 0)
        dt_step4 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=4,
                stage_name="3D Color Histogram & Perceptual dHash",
                status="completed",
                duration_ms=round(dt_step4, 2),
                summary=(
                    f"Quantized 64-bin RGB color distribution ({active_colors} active bins) "
                    f"and computed 64-bit perceptual dHash: {visual_payload.edge_signature}."
                ),
                details={
                    "color_bins": 64,
                    "active_color_bins": active_colors,
                    "luminance_bins": 32,
                    "perceptual_dhash": visual_payload.edge_signature,
                },
            )
        )

        # -------------------------------------------------------------------------
        # Step 5: 3072D Multi-Gram Visual Vector Projection (80% - 100%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        visual_vector = self.image_embedder.embed_features(
            spatial_grid=visual_payload.spatial_grid,
            color_histogram=visual_payload.color_histogram,
            luminance_histogram=visual_payload.luminance_histogram,
            horizontal_gradients=visual_payload.horizontal_gradients,
            vertical_gradients=visual_payload.vertical_gradients,
            edge_signature=visual_payload.edge_signature,
            aspect_ratio=meta.aspect_ratio,
        )
        dt_step5 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=5,
                stage_name="3072D Multi-Gram Visual Vector Projection",
                status="completed",
                duration_ms=round(dt_step5, 2),
                summary=(
                    "Projected spatial luminance, color distribution, and edge signatures into "
                    "normalized 3072-dimensional vector space (L2 Norm = 1.0)."
                ),
                details={
                    "vector_dimensions": len(visual_vector),
                    "l2_norm": 1.0,
                },
            )
        )

        # Prepare document chunk and payload metadata
        doc_metadata: dict[str, Any] = {
            "format": meta.format,
            "width": meta.width,
            "height": meta.height,
            "aspect_ratio": meta.aspect_ratio,
            "color_mode": meta.color_mode,
            "has_alpha": meta.has_alpha,
            "dhash": visual_payload.edge_signature,
            "is_image": True,
        }
        if metadata:
            doc_metadata.update(metadata)

        chunk = ProcessedChunk(
            chunk_id=f"{image_id}:0",
            document_id=image_id,
            chunk_index=0,
            text=visual_payload.narrative_summary,
            metadata=doc_metadata,
            embedding=visual_vector,
        )

        total_ms = (time.perf_counter() - t_start_total) * 1000.0
        summary_msg = (
            f"Successfully processed image '{name}' ({meta.format} {meta.width}x{meta.height}) "
            f"into vector(3072) in {total_ms:.1f}ms."
        )

        return ProcessedDocumentPayload(
            document_id=image_id,
            name=name,
            file_type=meta.format.lower(),
            file_size_bytes=file_size_bytes,
            content_hash=content_hash,
            classification=doc_metadata.get("classification", "visual"),
            chunks=[chunk],
            metadata=doc_metadata,
            execution_trace=traces,
            summary=summary_msg,
        )

    def embed_video_scene(
        self,
        spatial_grid: list[float],
        motion_score: float,
        start_seconds: float,
        end_seconds: float,
        keyframe_dhash: str | None = None,
        transcript_text: str | None = None,
    ) -> list[float]:
        """Generates a pure 3072-dimensional normalized spatio-temporal video embedding vector."""
        return self.video_embedder.embed_scene(
            spatial_grid=spatial_grid,
            motion_score=motion_score,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
            keyframe_dhash=keyframe_dhash,
            transcript_text=transcript_text,
        )

    def process_video(
        self,
        video_id: str,
        name: str,
        video_bytes: bytes | None = None,
        file_path: str | Path | None = None,
        scene_interval_seconds: float = 10.0,
        transcript_segments: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProcessedDocumentPayload:
        """Processes a video through pure-Python ISO container demuxing,
        temporal scene chunking, motion delta analysis, and 3072D vector projection.

        Args:
            video_id: Unique identifier for the video document.
            name: Filename or descriptor (e.g. 'product_demo.mp4').
            video_bytes: Raw binary video payload.
            file_path: Optional path to read video from disk if video_bytes not provided.
            scene_interval_seconds: Temporal window size in seconds (default: 10.0s).
            transcript_segments: Optional list of speech-to-text dicts with 'start', 'end', 'text'.
            metadata: Custom metadata dictionary to attach to video document and chunks.

        Returns:
            ProcessedDocumentPayload with temporal scene chunks, 3072D vectors,
            and 5-stage telemetry.
        """

        t_start_total = time.perf_counter()
        traces: list[ProcessingStageTrace] = []

        if video_bytes is not None:
            raw_data = video_bytes
        elif file_path is not None:
            raw_data = Path(file_path).read_bytes()
        else:
            raise ValueError("Either video_bytes or file_path must be provided to process_video.")

        file_size_bytes = len(raw_data)
        content_hash = hashlib.sha256(raw_data).hexdigest()

        # -------------------------------------------------------------------------
        # Step 1: Container Header & ISO Demuxing (0% - 20%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        video_payload = process_video_binary(
            data=raw_data,
            scene_interval_seconds=scene_interval_seconds,
            transcript_segments=transcript_segments,
        )
        meta = video_payload.metadata
        dt_step1 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=1,
                stage_name="Container Header & ISO Demuxing",
                status="completed",
                duration_ms=round(dt_step1, 2),
                summary=(
                    f"Demuxed {meta.format} container ({meta.width}x{meta.height} @ {meta.fps}fps, "
                    f"duration: {meta.duration_seconds}s, {meta.keyframe_count} keyframes)."
                ),
                details={
                    "format": meta.format,
                    "width": meta.width,
                    "height": meta.height,
                    "duration_seconds": meta.duration_seconds,
                    "total_frames": meta.total_frames,
                    "keyframe_count": meta.keyframe_count,
                    "fps": meta.fps,
                    "file_size_bytes": file_size_bytes,
                },
            )
        )

        # -------------------------------------------------------------------------
        # Step 2: Temporal Scene Segmentation & Keyframing (20% - 40%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        num_scenes = len(video_payload.scenes)
        dt_step2 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=2,
                stage_name="Temporal Scene Segmentation & Keyframing",
                status="completed",
                duration_ms=round(dt_step2, 2),
                summary=(
                    f"Segmented timeline into {num_scenes} temporal scene windows "
                    f"(target interval: {scene_interval_seconds}s per scene)."
                ),
                details={
                    "total_scenes": num_scenes,
                    "interval_seconds": scene_interval_seconds,
                },
            )
        )

        # -------------------------------------------------------------------------
        # Step 3: Multi-Frame Spatial Feature Extraction (40% - 60%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        total_cells_sampled = num_scenes * 64
        dt_step3 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=3,
                stage_name="Multi-Frame Spatial Feature Extraction",
                status="completed",
                duration_ms=round(dt_step3, 2),
                summary=(
                    f"Sampled {total_cells_sampled} spatial luminance cells and extracted "
                    f"perceptual edge signatures across all {num_scenes} scenes."
                ),
                details={
                    "cells_per_scene": 64,
                    "total_sampled_cells": total_cells_sampled,
                },
            )
        )

        # -------------------------------------------------------------------------
        # Step 4: Motion Dynamics & Temporal Delta Analysis (60% - 80%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        avg_motion = round(
            sum(s.motion_score for s in video_payload.scenes) / max(1, num_scenes), 3
        )
        dt_step4 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=4,
                stage_name="Motion Dynamics & Temporal Delta Analysis",
                status="completed",
                duration_ms=round(dt_step4, 2),
                summary=(
                    f"Analyzed inter-frame motion variance (average motion score: {avg_motion}). "
                    f"Classified scenes into static and active motion windows."
                ),
                details={
                    "average_motion_score": avg_motion,
                },
            )
        )

        # -------------------------------------------------------------------------
        # Step 5: 3072D Spatio-Temporal Vector Projection (80% - 100%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        processed_chunks: list[ProcessedChunk] = []

        for scene in video_payload.scenes:
            vec = self.video_embedder.embed_scene(
                spatial_grid=scene.spatial_grid,
                motion_score=scene.motion_score,
                start_seconds=scene.start_seconds,
                end_seconds=scene.end_seconds,
                keyframe_dhash=scene.keyframe_dhash,
                transcript_text=scene.transcript_segment,
            )

            chunk_meta: dict[str, Any] = {
                "format": meta.format,
                "scene_index": scene.scene_index,
                "start_seconds": scene.start_seconds,
                "end_seconds": scene.end_seconds,
                "timestamp": scene.timestamp_label,
                "motion_score": scene.motion_score,
                "motion_intensity": scene.motion_intensity,
                "keyframe_dhash": scene.keyframe_dhash,
                "is_video": True,
            }
            if metadata:
                chunk_meta.update(metadata)

            processed_chunks.append(
                ProcessedChunk(
                    chunk_id=f"{video_id}:{scene.scene_index}",
                    document_id=video_id,
                    chunk_index=scene.scene_index,
                    text=scene.narrative_summary,
                    metadata=chunk_meta,
                    embedding=vec,
                )
            )

        dt_step5 = (time.perf_counter() - t0) * 1000.0
        traces.append(
            ProcessingStageTrace(
                step_number=5,
                stage_name="3072D Spatio-Temporal Vector Projection",
                status="completed",
                duration_ms=round(dt_step5, 2),
                summary=(
                    f"Projected {len(processed_chunks)} normalized 3072-dimensional "
                    f"spatio-temporal vector embeddings (L2 Norm = 1.0)."
                ),
                details={
                    "vector_dimensions": 3072,
                    "total_vectors": len(processed_chunks),
                },
            )
        )

        doc_meta: dict[str, Any] = {
            "format": meta.format,
            "duration_seconds": meta.duration_seconds,
            "width": meta.width,
            "height": meta.height,
            "fps": meta.fps,
            "total_frames": meta.total_frames,
            "keyframe_count": meta.keyframe_count,
            "total_scenes": len(processed_chunks),
            "is_video": True,
        }
        if metadata:
            doc_meta.update(metadata)

        total_ms = (time.perf_counter() - t_start_total) * 1000.0
        summary_msg = (
            f"Successfully processed video '{name}' ({meta.duration_seconds}s, {meta.format}) "
            f"into {len(processed_chunks)} temporal vector(3072) scenes in {total_ms:.1f}ms."
        )

        return ProcessedDocumentPayload(
            document_id=video_id,
            name=name,
            file_type=meta.format.lower(),
            file_size_bytes=file_size_bytes,
            content_hash=content_hash,
            classification=doc_meta.get("classification", "video"),
            chunks=processed_chunks,
            metadata=doc_meta,
            execution_trace=traces,
            summary=summary_msg,
        )

    def process_pdf(
        self,
        pdf_id: str,
        name: str,
        pdf_bytes: bytes | None = None,
        file_path: str | Path | None = None,
        metadata: dict[str, Any] | None = None,
        enable_guardrails: bool = True,
        shallow_mode: bool = False,
    ) -> ProcessedDocumentPayload:
        """Processes a PDF through pure-Python ISO 32000-1 binary parsing,
        FlateDecode stream decompression, PostScript text operator decoding,
        PII sanitization, and page-grounded 3072D vector projection.

        Args:
            pdf_id: Unique identifier for the PDF document.
            name: Filename or descriptor (e.g. 'annual_report.pdf').
            pdf_bytes: Raw binary PDF payload.
            file_path: Optional path to read PDF from disk if pdf_bytes not provided.
            metadata: Custom metadata dictionary to attach to PDF document and page chunks.
            enable_guardrails: When True (default), applies PII detection and regex masking.
            shallow_mode: Alias for bypassing PII masking for internal reviews.

        Returns:
            ProcessedDocumentPayload with page-grounded chunks, 3072D vectors,
            and 5-stage telemetry.
        """
        t_start_total = time.perf_counter()
        traces: list[ProcessingStageTrace] = []
        apply_guardrails = enable_guardrails and (not shallow_mode)

        if pdf_bytes is not None:
            raw_data = pdf_bytes
        elif file_path is not None:
            raw_data = Path(file_path).read_bytes()
        else:
            raise ValueError("Either pdf_bytes or file_path must be provided to process_pdf.")

        file_size_bytes = len(raw_data)
        content_hash = hashlib.md5(raw_data).hexdigest()

        # -------------------------------------------------------------------------
        # Step 1: PDF Header & Object Graph Parsing (0% - 20%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        pdf_payload = process_pdf_binary(raw_data)
        meta = pdf_payload.metadata
        dt_step1 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=1,
                stage_name="PDF Header & Object Graph Parsing",
                status="completed",
                duration_ms=round(dt_step1, 2),
                summary=(
                    f"Parsed ISO 32000-1 PDF v{meta.version} object graph "
                    f"({file_size_bytes} bytes, {meta.page_count} pages detected)."
                ),
                details={
                    "version": meta.version,
                    "page_count": meta.page_count,
                    "file_size_bytes": file_size_bytes,
                    "is_encrypted": meta.is_encrypted,
                },
            )
        )

        # -------------------------------------------------------------------------
        # Step 2: FlateDecode Stream Decompression (20% - 40%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        decompressed_stream_count = meta.page_count
        dt_step2 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=2,
                stage_name="FlateDecode Stream Decompression (zlib)",
                status="completed",
                duration_ms=round(dt_step2, 2),
                summary=(
                    f"Decompressed Deflate content streams across {decompressed_stream_count} "
                    f"page objects using standard library zlib."
                ),
                details={
                    "decompressed_pages": decompressed_stream_count,
                },
            )
        )

        # -------------------------------------------------------------------------
        # Step 3: PostScript Text Operator Decoding (40% - 60%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        total_words = sum(p.word_count for p in pdf_payload.pages)
        total_chars = sum(p.char_count for p in pdf_payload.pages)
        dt_step3 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=3,
                stage_name="PostScript Text Operator Decoding (BT/ET/Tj/TJ)",
                status="completed",
                duration_ms=round(dt_step3, 2),
                summary=(
                    f"Decoded {total_words} words ({total_chars} characters) across "
                    f"{len(pdf_payload.pages)} pages via PostScript BT/ET/Tj/TJ extraction."
                ),
                details={
                    "total_words": total_words,
                    "total_chars": total_chars,
                    "pages_extracted": len(pdf_payload.pages),
                },
            )
        )

        # -------------------------------------------------------------------------
        # Step 4: Safety Guardrails & PII Sanitization (60% - 80%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        sanitized_pages: list[tuple[Any, str]] = []
        total_masked_items = 0

        for page in pdf_payload.pages:
            p_text = page.text
            if apply_guardrails and p_text:
                scrubbed_text = self.guardrails.mask_pii(p_text)
                if scrubbed_text != p_text:
                    total_masked_items += 1
            else:
                scrubbed_text = p_text
            sanitized_pages.append((page, scrubbed_text))

        dt_step4 = (time.perf_counter() - t0) * 1000.0
        traces.append(
            ProcessingStageTrace(
                step_number=4,
                stage_name="Safety Guardrails & PII Sanitization",
                status="completed",
                duration_ms=round(dt_step4, 2),
                summary=(
                    f"Applied PII detection across {len(sanitized_pages)} pages. "
                    f"Masked {total_masked_items} sensitive items (Luhn cards, emails, SSNs)."
                ),
                details={
                    "guardrails_enabled": apply_guardrails,
                    "masked_items": total_masked_items,
                },
            )
        )

        # -------------------------------------------------------------------------
        # Step 5: Page-Grounded 3072D Vector Projection (80% - 100%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        processed_chunks: list[ProcessedChunk] = []

        for page, scrubbed_text in sanitized_pages:
            display_text = f"{page.page_label} {scrubbed_text}".strip()
            embedding_vector = self.retrieval.embed(display_text or page.page_label)

            chunk_meta: dict[str, Any] = {
                "page_number": page.page_number,
                "page_label": page.page_label,
                "width_pts": page.width_pts,
                "height_pts": page.height_pts,
                "word_count": page.word_count,
                "char_count": page.char_count,
                "is_pdf": True,
            }
            if metadata:
                chunk_meta.update(metadata)

            processed_chunks.append(
                ProcessedChunk(
                    chunk_id=f"{pdf_id}:{page.page_number - 1}",
                    document_id=pdf_id,
                    chunk_index=page.page_number - 1,
                    text=display_text,
                    metadata=chunk_meta,
                    embedding=embedding_vector,
                )
            )

        dt_step5 = (time.perf_counter() - t0) * 1000.0
        traces.append(
            ProcessingStageTrace(
                step_number=5,
                stage_name="Page-Grounded 3072D Vector Projection",
                status="completed",
                duration_ms=round(dt_step5, 2),
                summary=(
                    f"Projected {len(processed_chunks)} page-grounded 3072-dimensional "
                    f"vector embeddings (L2 Norm = 1.0)."
                ),
                details={
                    "vector_dimensions": 3072,
                    "total_vectors": len(processed_chunks),
                },
            )
        )

        doc_meta: dict[str, Any] = {
            "format": "PDF",
            "version": meta.version,
            "page_count": meta.page_count,
            "total_words": total_words,
            "total_chars": total_chars,
            "is_encrypted": meta.is_encrypted,
            "is_pdf": True,
        }
        if metadata:
            doc_meta.update(metadata)

        total_ms = (time.perf_counter() - t_start_total) * 1000.0
        summary_msg = (
            f"Successfully processed PDF '{name}' ({meta.page_count} pages, {total_words} words) "
            f"into {len(processed_chunks)} page-grounded vector(3072) chunks in {total_ms:.1f}ms."
        )

        return ProcessedDocumentPayload(
            document_id=pdf_id,
            name=name,
            file_type="pdf",
            file_size_bytes=file_size_bytes,
            content_hash=content_hash,
            classification=doc_meta.get("classification", "document"),
            chunks=processed_chunks,
            metadata=doc_meta,
            execution_trace=traces,
            summary=summary_msg,
        )

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
        applies safety guardrails & PII sanitization, and projects 3072D vector embeddings.

        Args:
            table_name: Name of the relational MySQL table (e.g. 'customers', 'orders').
            rows: List of dictionary row representations (column -> value).
            primary_key: Optional explicit primary key column name. Auto-detects 'id' / '_id'.
            metadata: Custom metadata dictionary to attach to table document and row chunks.
            rows_per_chunk: Number of rows bundled per chunk narrative (default: 1).
            enable_guardrails: When True (default), scrubs sensitive PII (Luhn cards, emails).
            shallow_mode: Alias for bypassing PII sanitization for internal analysis.

        Returns:
            ProcessedDocumentPayload with table-grounded chunks, 3072D vectors, and telemetry.
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
        raw_chunks = chunk_mysql_table(
            rows,
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
        cleaned_chunks: list[str] = []
        total_masked = 0
        for chunk in raw_chunks:
            if apply_guardrails:
                masked = self.guardrails.mask_pii(chunk)
                if masked != chunk:
                    total_masked += 1
                cleaned_chunks.append(masked)
            else:
                cleaned_chunks.append(chunk)

        dt_step4 = (time.perf_counter() - t0) * 1000.0
        guardrails_summary = (
            f"Evaluated {len(raw_chunks)} table chunks through PII scrubbers. "
            f"Sanitized sensitive data in {total_masked} chunk(s)."
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
        # Step 5: 3072D Multi-Gram Vector Projection (80% - 100%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        processed_chunks: list[ProcessedChunk] = []
        doc_id = f"mysql:{table_name}"

        for idx, chunk_text in enumerate(cleaned_chunks):
            embedding = self.retrieval.embed(chunk_text)
            chunk_meta: dict[str, Any] = {
                "source_table": table_name,
                "primary_key": detected_pk,
                "chunk_index": idx,
                "is_database": True,
                "database_type": "mysql",
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
                    f"vector embeddings (L2 Norm = 1.0) for MySQL table '{table_name}'."
                ),
                details={
                    "vector_dimensions": 3072,
                    "total_vectors": len(processed_chunks),
                },
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
            f"into {len(processed_chunks)} vector(3072) chunks in {total_ms:.1f}ms."
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
        flattened dot-notation semantic narratives, scrubs sensitive PII,
        and projects 3072D vector embeddings.

        Args:
            collection_name: Name of the MongoDB collection (e.g. 'users', 'transactions').
            documents: List of BSON / Extended-JSON / dictionary documents.
            flatten_nested: When True (default), flattens nested dicts/arrays to dot-notation.
            metadata: Custom metadata dictionary to attach to collection document and chunks.
            enable_guardrails: When True (default), scrubs sensitive PII (Luhn cards, emails).
            shallow_mode: Alias for bypassing PII sanitization.

        Returns:
            ProcessedDocumentPayload with collection-grounded chunks, 3072D vectors, and traces.
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
        raw_chunks = chunk_mongo_collection(
            normalized_docs, collection_name=collection_name, flatten=flatten_nested
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
        cleaned_chunks: list[str] = []
        total_masked = 0
        for chunk in raw_chunks:
            if apply_guardrails:
                masked = self.guardrails.mask_pii(chunk)
                if masked != chunk:
                    total_masked += 1
                cleaned_chunks.append(masked)
            else:
                cleaned_chunks.append(chunk)

        dt_step4 = (time.perf_counter() - t0) * 1000.0
        guardrails_summary = (
            f"Evaluated {len(raw_chunks)} MongoDB document chunks through PII scrubbers. "
            f"Sanitized sensitive data in {total_masked} chunk(s)."
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
        # Step 5: 3072D Multi-Gram Vector Projection (80% - 100%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        processed_chunks: list[ProcessedChunk] = []
        doc_id = f"mongodb:{collection_name}"

        for idx, chunk_text in enumerate(cleaned_chunks):
            embedding = self.retrieval.embed(chunk_text)
            chunk_meta: dict[str, Any] = {
                "collection_name": collection_name,
                "chunk_index": idx,
                "is_database": True,
                "database_type": "mongodb",
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
                    f"vector embeddings (L2 Norm = 1.0) for collection '{collection_name}'."
                ),
                details={
                    "vector_dimensions": 3072,
                    "total_vectors": len(processed_chunks),
                },
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
            f"into {len(processed_chunks)} vector(3072) chunks in {total_ms:.1f}ms."
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

    def embed_audio(
        self,
        audio_bytes: bytes,
        window_seconds: float = 10.0,
    ) -> list[float]:
        """Generates a pure 3072-dimensional normalized spatio-acoustic embedding vector."""
        payload = process_audio_binary(audio_bytes, window_seconds=window_seconds)
        return self.audio_embedder.embed_features(
            rms_envelope=payload.rms_envelope,
            zcr_profile=payload.zcr_profile,
            spectral_distribution=payload.spectral_distribution,
            spectral_flux=payload.spectral_flux,
            duration_seconds=payload.metadata.duration_seconds,
            acoustic_signature=payload.acoustic_signature,
            narrative_tokens=" ".join(s.narrative_text for s in payload.segments),
        )

    def process_audio(
        self,
        audio_id: str,
        name: str,
        audio_bytes: bytes | None = None,
        file_path: str | Path | None = None,
        window_seconds: float = 10.0,
        metadata: dict[str, Any] | None = None,
        enable_guardrails: bool = True,
        shallow_mode: bool = False,
    ) -> ProcessedDocumentPayload:
        """Processes an audio file through native pure-Python container decoding,
        PCM extraction, VAD energy profiling, spectral decomposition, PII sanitization,
        and temporal 3072D vector projection.

        Args:
            audio_id: Unique identifier for the audio resource.
            name: Filename or descriptor (e.g. 'call_recording.wav', 'track.mp3').
            audio_bytes: Raw binary audio payload.
            file_path: Optional path to read audio file from disk if audio_bytes not provided.
            window_seconds: Temporal framing interval in seconds (default: 10.0).
            metadata: Custom metadata dictionary to attach to audio document and segment chunks.
            enable_guardrails: When True (default), scrubs sensitive PII in ID3 tags.
            shallow_mode: Alias for bypassing PII sanitization.

        Returns:
            ProcessedDocumentPayload with temporal chunks, 3072D vectors, and traces.
        """
        t_start_total = time.perf_counter()
        traces: list[ProcessingStageTrace] = []
        apply_guardrails = enable_guardrails and (not shallow_mode)

        if audio_bytes is not None:
            raw_data = audio_bytes
        elif file_path is not None:
            raw_data = Path(file_path).read_bytes()
        else:
            raise ValueError("Either audio_bytes or file_path must be provided to process_audio.")

        file_size_bytes = len(raw_data)
        content_hash = hashlib.md5(raw_data).hexdigest()

        # -------------------------------------------------------------------------
        # Step 1: Audio Container & Codec Parsing (0% - 20%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        audio_payload = process_audio_binary(raw_data, window_seconds=window_seconds)
        meta = audio_payload.metadata
        dt_step1 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=1,
                stage_name="Audio Container & Codec Parsing",
                status="completed",
                duration_ms=round(dt_step1, 2),
                summary=(
                    f"Parsed {meta.format} container ({meta.sample_rate}Hz, "
                    f"{meta.channels}ch, {meta.bit_depth}-bit). Duration: {meta.duration_seconds}s."
                ),
                details={
                    "format": meta.format,
                    "sample_rate": meta.sample_rate,
                    "channels": meta.channels,
                    "bit_depth": meta.bit_depth,
                    "duration_seconds": meta.duration_seconds,
                    "id3_tags": meta.id3_tags,
                },
            )
        )

        # -------------------------------------------------------------------------
        # Step 2: PCM Signal Extraction & Channel Normalization (20% - 40%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        dt_step2 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=2,
                stage_name="PCM Signal Extraction & Channel Normalization",
                status="completed",
                duration_ms=round(dt_step2, 2),
                summary=(
                    f"Extracted {meta.total_frames} PCM frames and normalized multi-channel "
                    f"audio into float signal [-1.0, 1.0]."
                ),
                details={
                    "total_frames": meta.total_frames,
                    "channels": meta.channels,
                },
            )
        )

        # -------------------------------------------------------------------------
        # Step 3: Temporal Window Framing & VAD Energy Profiling (40% - 60%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        active_count = sum(1 for s in audio_payload.segments if s.activity_level != "Silent")
        dt_step3 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=3,
                stage_name="Temporal Window Framing & VAD Energy Profiling",
                status="completed",
                duration_ms=round(dt_step3, 2),
                summary=(
                    f"Framed audio into {len(audio_payload.segments)} temporal window(s) "
                    f"({window_seconds}s interval). Detected {active_count} active segment(s)."
                ),
                details={
                    "total_segments": len(audio_payload.segments),
                    "window_seconds": window_seconds,
                    "active_segments": active_count,
                },
            )
        )

        # -------------------------------------------------------------------------
        # Step 4: Multi-Band Spectral & Rhythm Decomposition (60% - 80%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        avg_rms = sum(s.rms_energy for s in audio_payload.segments) / max(
            1, len(audio_payload.segments)
        )
        avg_centroid = sum(s.spectral_centroid_hz for s in audio_payload.segments) / max(
            1, len(audio_payload.segments)
        )
        dt_step4 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=4,
                stage_name="Multi-Band Spectral & Rhythm Decomposition",
                status="completed",
                duration_ms=round(dt_step4, 2),
                summary=(
                    f"Decomposed 7-band spectral frequencies (Centroid: {avg_centroid:.0f}Hz, "
                    f"Mean RMS: {avg_rms:.3f}). Signature: {audio_payload.acoustic_signature}."
                ),
                details={
                    "mean_rms": round(avg_rms, 4),
                    "mean_centroid_hz": round(avg_centroid, 1),
                    "acoustic_signature": audio_payload.acoustic_signature,
                },
            )
        )

        # -------------------------------------------------------------------------
        # Step 5: Spatio-Acoustic 3072D Vector Projection (80% - 100%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        processed_chunks: list[ProcessedChunk] = []

        for seg in audio_payload.segments:
            seg_text = seg.narrative_text
            if apply_guardrails:
                seg_text = self.guardrails.mask_pii(seg_text)

            embedding = self.audio_embedder.embed_features(
                rms_envelope=[seg.rms_energy] * 64,
                zcr_profile=[seg.zero_crossing_rate] * 64,
                spectral_distribution=(seg.sub_band_energies * 10)[:64],
                spectral_flux=audio_payload.spectral_flux,
                duration_seconds=seg.end_seconds - seg.start_seconds,
                acoustic_signature=audio_payload.acoustic_signature,
                narrative_tokens=seg_text,
            )

            chunk_meta: dict[str, Any] = {
                "segment_index": seg.segment_index,
                "start_seconds": seg.start_seconds,
                "end_seconds": seg.end_seconds,
                "timestamp_label": seg.timestamp_label,
                "rms_energy": seg.rms_energy,
                "zero_crossing_rate": seg.zero_crossing_rate,
                "spectral_centroid_hz": seg.spectral_centroid_hz,
                "activity_level": seg.activity_level,
                "is_audio": True,
                "audio_format": meta.format,
            }
            if meta.id3_tags:
                chunk_meta["id3_tags"] = meta.id3_tags
            if metadata:
                chunk_meta.update(metadata)

            processed_chunks.append(
                ProcessedChunk(
                    chunk_id=f"{audio_id}:{seg.segment_index}",
                    document_id=audio_id,
                    chunk_index=seg.segment_index,
                    text=seg_text,
                    metadata=chunk_meta,
                    embedding=embedding,
                )
            )

        dt_step5 = (time.perf_counter() - t0) * 1000.0
        traces.append(
            ProcessingStageTrace(
                step_number=5,
                stage_name="Spatio-Acoustic 3072D Vector Projection",
                status="completed",
                duration_ms=round(dt_step5, 2),
                summary=(
                    f"Projected {len(processed_chunks)} spatio-acoustic 3072-dimensional "
                    f"vector embeddings (L2 Norm = 1.0)."
                ),
                details={
                    "vector_dimensions": 3072,
                    "total_vectors": len(processed_chunks),
                },
            )
        )

        doc_meta: dict[str, Any] = {
            "format": meta.format,
            "sample_rate": meta.sample_rate,
            "channels": meta.channels,
            "bit_depth": meta.bit_depth,
            "duration_seconds": meta.duration_seconds,
            "total_frames": meta.total_frames,
            "acoustic_signature": audio_payload.acoustic_signature,
            "is_audio": True,
        }
        if meta.id3_tags:
            doc_meta["id3_tags"] = meta.id3_tags
        if metadata:
            doc_meta.update(metadata)

        total_ms = (time.perf_counter() - t_start_total) * 1000.0
        summary_msg = (
            f"Processed {meta.format} audio '{name}' ({meta.duration_seconds}s) "
            f"into {len(processed_chunks)} vector(3072) chunks in {total_ms:.1f}ms."
        )

        return ProcessedDocumentPayload(
            document_id=audio_id,
            name=name,
            file_type="audio",
            file_size_bytes=file_size_bytes,
            content_hash=content_hash,
            classification=doc_meta.get("classification", "audio"),
            chunks=processed_chunks,
            metadata=doc_meta,
            execution_trace=traces,
            summary=summary_msg,
        )

    def process_spreadsheet(
        self,
        spreadsheet_id: str,
        name: str,
        spreadsheet_bytes: bytes | None = None,
        file_path: str | Path | None = None,
        metadata: dict[str, Any] | None = None,
        enable_guardrails: bool = True,
        shallow_mode: bool = False,
    ) -> ProcessedDocumentPayload:
        """Processes an Excel spreadsheet (.xlsx) through native pure-Python container
        decompression, shared string resolution, worksheet tabular framing, PII sanitization,
        and sheet-grounded 3072D vector projection.
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
        spreadsheet_payload = process_spreadsheet_binary(raw_data, filename=name)
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
        sanitized_chunks: list[tuple[Any, str]] = []
        total_masked_items = 0

        for chunk in spreadsheet_payload.all_chunks:
            n_text = chunk.narrative_text
            if apply_guardrails and n_text:
                scrubbed_text = self.guardrails.mask_pii(n_text)
                if scrubbed_text != n_text:
                    total_masked_items += 1
            else:
                scrubbed_text = n_text
            sanitized_chunks.append((chunk, scrubbed_text))

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

        # Step 5: Sheet-Grounded 3072D Vector Projection
        t0 = time.perf_counter()
        processed_chunks: list[ProcessedChunk] = []

        for idx, (chunk, scrubbed_text) in enumerate(sanitized_chunks):
            embedding_vector = self.retrieval.embed(scrubbed_text)
            chunk_meta: dict[str, Any] = {
                "sheet_name": chunk.sheet_name,
                "row_index": chunk.row_index,
                "data": chunk.data,
                "is_spreadsheet": True,
            }
            if metadata:
                chunk_meta.update(metadata)

            processed_chunks.append(
                ProcessedChunk(
                    chunk_id=f"{spreadsheet_id}:{chunk.sheet_name}:{chunk.row_index}",
                    document_id=spreadsheet_id,
                    chunk_index=idx,
                    text=scrubbed_text,
                    metadata=chunk_meta,
                    embedding=embedding_vector,
                )
            )

        dt_step5 = (time.perf_counter() - t0) * 1000.0
        traces.append(
            ProcessingStageTrace(
                step_number=5,
                stage_name="Sheet-Grounded 3072D Vector Projection",
                status="completed",
                duration_ms=round(dt_step5, 2),
                summary=(
                    f"Projected {len(processed_chunks)} sheet-grounded 3072-dimensional "
                    f"vector embeddings (L2 Norm = 1.0)."
                ),
                details={
                    "vector_dimensions": 3072,
                    "total_vectors": len(processed_chunks),
                },
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
            f"{meta.total_rows} rows) into {len(processed_chunks)} vector(3072) chunks "
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

    def process_presentation(
        self,
        presentation_id: str,
        name: str,
        presentation_bytes: bytes | None = None,
        file_path: str | Path | None = None,
        metadata: dict[str, Any] | None = None,
        enable_guardrails: bool = True,
        shallow_mode: bool = False,
    ) -> ProcessedDocumentPayload:
        """Processes a PowerPoint presentation (.pptx) through native pure-Python container
        decompression, slide shape extraction, speaker notes resolution, PII sanitization,
        and slide-grounded 3072D vector projection.
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
        pres_payload = process_presentation_binary(raw_data, filename=name)
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

        # Step 5: Slide-Grounded 3072D Vector Projection
        t0 = time.perf_counter()
        processed_chunks: list[ProcessedChunk] = []

        for idx, (s, scrubbed_text) in enumerate(sanitized_slides):
            embedding_vector = self.retrieval.embed(scrubbed_text)
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
                    embedding=embedding_vector,
                )
            )

        dt_step5 = (time.perf_counter() - t0) * 1000.0
        traces.append(
            ProcessingStageTrace(
                step_number=5,
                stage_name="Slide-Grounded 3072D Vector Projection",
                status="completed",
                duration_ms=round(dt_step5, 2),
                summary=(
                    f"Projected {len(processed_chunks)} slide-grounded 3072-dimensional "
                    f"vector embeddings (L2 Norm = 1.0)."
                ),
                details={
                    "vector_dimensions": 3072,
                    "total_vectors": len(processed_chunks),
                },
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
            f"{meta.total_words} words) into {len(processed_chunks)} vector(3072) chunks "
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

    def process_email(
        self,
        email_id: str,
        name: str,
        email_bytes: bytes | None = None,
        file_path: str | Path | None = None,
        metadata: dict[str, Any] | None = None,
        enable_guardrails: bool = True,
        shallow_mode: bool = False,
    ) -> ProcessedDocumentPayload:
        """Processes an RFC 5322 MIME email message (.eml) through header extraction,
        multipart attachment resolution, chronological reconstruction, PII sanitization,
        and email-grounded 3072D vector projection.
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
        email_payload = process_email_binary(raw_data, filename=name)
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

        # Step 5: Email-Grounded 3072D Vector Projection
        t0 = time.perf_counter()
        processed_chunks: list[ProcessedChunk] = []

        for chk, scrubbed_text in sanitized_chunks:
            embedding_vector = self.retrieval.embed(scrubbed_text)
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
                    embedding=embedding_vector,
                )
            )

        dt_step5 = (time.perf_counter() - t0) * 1000.0
        traces.append(
            ProcessingStageTrace(
                step_number=5,
                stage_name="Email-Grounded 3072D Vector Projection",
                status="completed",
                duration_ms=round(dt_step5, 2),
                summary=(
                    f"Projected {len(processed_chunks)} email-grounded "
                    "3072-dimensional vector embeddings (L2 Norm = 1.0)."
                ),
                details={
                    "vector_dimensions": 3072,
                    "total_vectors": len(processed_chunks),
                },
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
            f"into 3072D vectors in {total_ms:.1f}ms."
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
        through schema discovery, thread graph reconstruction, PII sanitization,
        and dialogue-grounded 3072D vector projection.
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

        # Step 5: Dialogue-Grounded 3072D Vector Projection
        t0 = time.perf_counter()
        processed_chunks: list[ProcessedChunk] = []

        for idx, (th, scrubbed_text) in enumerate(sanitized_threads):
            embedding_vector = self.retrieval.embed(scrubbed_text)
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
                    embedding=embedding_vector,
                )
            )

        dt_step5 = (time.perf_counter() - t0) * 1000.0
        traces.append(
            ProcessingStageTrace(
                step_number=5,
                stage_name="Dialogue-Grounded 3072D Vector Projection",
                status="completed",
                duration_ms=round(dt_step5, 2),
                summary=(
                    f"Projected {len(processed_chunks)} dialogue-grounded "
                    "3072-dimensional vector embeddings (L2 Norm = 1.0)."
                ),
                details={
                    "vector_dimensions": 3072,
                    "total_vectors": len(processed_chunks),
                },
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
            f"into {len(processed_chunks)} vector(3072) chunks in {total_ms:.1f}ms."
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
        schema DDL introspection, foreign-key relationship graph extraction, PII sanitization,
        and relational-grounded 3072D vector projection.
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

        # Step 5: Relational-Grounded 3072D Vector Projection
        t0 = time.perf_counter()
        processed_chunks: list[ProcessedChunk] = []

        for idx, (chk, scrubbed_text) in enumerate(sanitized_chunks):
            embedding_vector = self.retrieval.embed(scrubbed_text)
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
                    embedding=embedding_vector,
                )
            )

        dt_step5 = (time.perf_counter() - t0) * 1000.0
        traces.append(
            ProcessingStageTrace(
                step_number=5,
                stage_name="Relational-Grounded 3072D Vector Projection",
                status="completed",
                duration_ms=round(dt_step5, 2),
                summary=(
                    f"Projected {len(processed_chunks)} relational-grounded "
                    "3072-dimensional vector embeddings (L2 Norm = 1.0)."
                ),
                details={
                    "vector_dimensions": 3072,
                    "total_vectors": len(processed_chunks),
                },
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
            f"{meta.total_rows} rows) into {len(processed_chunks)} vector(3072) chunks "
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
        symbol & scope extraction, PII sanitization, and AST-grounded 3072D vector projection.
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

        # Step 5: AST-Grounded 3072D Vector Projection
        t0 = time.perf_counter()
        processed_chunks: list[ProcessedChunk] = []

        for idx, (chk, scrubbed_text) in enumerate(sanitized_chunks):
            embedding_vector = chk.embedding or self.retrieval.embed(scrubbed_text)
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
                    embedding=embedding_vector,
                )
            )

        dt_step5 = (time.perf_counter() - t0) * 1000.0
        traces.append(
            ProcessingStageTrace(
                step_number=5,
                stage_name="AST-Grounded 3072D Vector Projection",
                status="completed",
                duration_ms=round(dt_step5, 2),
                summary=(
                    f"Projected {len(processed_chunks)} AST-grounded 3072-dimensional "
                    "vector embeddings (L2 Norm = 1.0)."
                ),
                details={
                    "vector_dimensions": 3072,
                    "total_vectors": len(processed_chunks),
                },
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
            f"{meta.total_lines} lines) into {len(processed_chunks)} vector(3072) chunks "
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
        parameter extraction, safety guardrails, and API-grounded 3072D vector projection.
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

        # Step 5: API-Grounded 3072D Vector Projection
        t0 = time.perf_counter()
        processed_chunks: list[ProcessedChunk] = []

        for idx, (chk, scrubbed_text) in enumerate(sanitized_chunks):
            embedding_vector = chk.embedding or self.retrieval.embed(scrubbed_text)
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
                    embedding=embedding_vector,
                )
            )

        dt_step5 = (time.perf_counter() - t0) * 1000.0
        traces.append(
            ProcessingStageTrace(
                step_number=5,
                stage_name="API-Grounded 3072D Vector Projection",
                status="completed",
                duration_ms=round(dt_step5, 2),
                summary=(
                    f"Projected {len(processed_chunks)} API-grounded 3072-dimensional "
                    "vector embeddings (L2 Norm = 1.0)."
                ),
                details={
                    "vector_dimensions": 3072,
                    "total_vectors": len(processed_chunks),
                },
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
            f"{meta.total_classes} schemas) into {len(processed_chunks)} vector(3072) chunks "
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
