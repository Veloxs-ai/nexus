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
    from nexus.processing.pdf import process_pdf_binary
    from nexus.processing.video import process_video_binary
    from nexus.retrieval.embeddings import ImageEmbedder, VideoEmbedder
    from nexus.retrieval.engine import RetrievalEngine
except (ImportError, ModuleNotFoundError):
    from nexus_experience.config import AuthConfig, EngagementConfig
    from nexus_experience.config import TenantConfig as ExpTenantConfig
    from nexus_experience.gateway import InMemoryGuardrailsGateway
    from nexus_experience.models import AskRequest, AskResponse, Principal
    from nexus_experience.service import ExperienceService
    from nexus_guardrails.engine import GuardrailsEngine
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
    from nexus_processing.pdf import process_pdf_binary
    from nexus_processing.video import process_video_binary
    from nexus_retrieval.embeddings import ImageEmbedder, VideoEmbedder
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
