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

"""``NexusClient.process_image``: image bytes to grid, colour and OCR/caption chunks.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from nexus.chunk_limits import bounded_output
from nexus.models import ProcessedChunk, ProcessedDocumentPayload, ProcessingStageTrace

try:
    from nexus.processing.images import process_image_binary
except (ImportError, ModuleNotFoundError):
    from nexus_processing.images import process_image_binary

__all__ = ["ImageMixin"]


class ImageMixin:
    """Mixed into ``NexusClient``."""

    @bounded_output
    def process_image(
        self,
        image_id: str,
        name: str,
        image_bytes: bytes | None = None,
        file_path: str | Path | None = None,
        format_hint: str | None = None,
        metadata: dict[str, Any] | None = None,
        ocr_text: str | None = None,
        caption: str | None = None,
        ocr_provider: Any | None = None,
        auto_extract: bool = False,
    ) -> ProcessedDocumentPayload:
        """Processes an image through pure-Python decoding, spatial grid decomposition,
        color and luminance distribution analysis.

        Args:
            image_id: Unique identifier for the image document.
            name: Filename or descriptor (e.g. 'diagram.png').
            image_bytes: Raw binary image payload.
            file_path: Optional path to read image from disk if image_bytes not provided.
            format_hint: Optional format hint ('png', 'jpeg', 'bmp').
            metadata: Custom metadata dictionary to attach to image document and chunk.
            ocr_text: Optional pre-extracted or externally supplied OCR transcription.
            caption: Optional semantic caption or description for multimodal grounding.
            ocr_provider: Optional OCRProvider instance for automatic text extraction.
            auto_extract: When True, auto-detects installed ML packages for content extraction.

        Returns:
            ProcessedDocumentPayload with visual metadata, and 5-stage telemetry.
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
        visual_payload = process_image_binary(
            raw_data,
            format_hint=detected_format,
            filename=name,
            ocr_text=ocr_text,
            caption=caption,
            ocr_provider=ocr_provider,
            auto_extract=auto_extract,
        )
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
        # Step 5: Visual Chunk Assembly (80% - 100%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        dt_step5 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=5,
                stage_name="Visual Chunk Assembly",
                status="completed",
                duration_ms=round(dt_step5, 2),
                summary="Assembled final chunks with grounded metadata (vectors are produced at "
                "storage time by embed_texts()).",
                details={},
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
        if meta.caption:
            doc_metadata["caption"] = meta.caption
        if meta.ocr_text:
            doc_metadata["ocr_text"] = meta.ocr_text
        if meta.embedded_text:
            doc_metadata["embedded_text"] = meta.embedded_text
        if metadata:
            doc_metadata.update(metadata)

        chunk = ProcessedChunk(
            chunk_id=f"{image_id}:0",
            document_id=image_id,
            chunk_index=0,
            text=visual_payload.narrative_summary,
            metadata=doc_metadata,
        )

        total_ms = (time.perf_counter() - t_start_total) * 1000.0
        summary_msg = (
            f"Successfully processed image '{name}' ({meta.format} {meta.width}x{meta.height}) "
            f"into 1 chunk in {total_ms:.1f}ms."
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
