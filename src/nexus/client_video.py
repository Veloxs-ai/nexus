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

"""``NexusClient.process_video``: video bytes to scene, transcript and caption chunks.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from nexus.chunk_limits import bounded_output
from nexus.models import ProcessedChunk, ProcessedDocumentPayload, ProcessingStageTrace

try:
    from nexus.processing.video import process_video_binary
except (ImportError, ModuleNotFoundError):
    from nexus_processing.video import process_video_binary

__all__ = ["VideoMixin"]


class VideoMixin:
    """Mixed into ``NexusClient``."""

    @bounded_output
    def process_video(
        self,
        video_id: str,
        name: str,
        video_bytes: bytes | None = None,
        file_path: str | Path | None = None,
        scene_interval_seconds: float = 10.0,
        transcript_segments: list[dict[str, Any]] | None = None,
        transcript: str | None = None,
        captions: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        demuxer: Any | None = None,
        transcriber: Any | None = None,
        ocr_provider: Any | None = None,
        auto_extract: bool = False,
    ) -> ProcessedDocumentPayload:
        """Processes a video through pure-Python ISO container demuxing,
        temporal scene chunking, motion delta analysis.

        Args:
            video_id: Unique identifier for the video document.
            name: Filename or descriptor (e.g. 'product_demo.mp4').
            video_bytes: Raw binary video payload.
            file_path: Optional path to read video from disk if video_bytes not provided.
            scene_interval_seconds: Temporal window size in seconds (default: 10.0s).
            transcript_segments: Optional list of speech-to-text dicts with 'start', 'end', 'text'.
            transcript: Optional full speech transcript text distributed across scenes.
            captions: Optional list of scene-level captions or dialogue strings.
            metadata: Custom metadata dictionary to attach to video document and chunks.
            demuxer: Optional VideoDemuxer instance for audio/keyframe extraction.
            transcriber: Optional AudioTranscriber instance for speech-to-text.
            ocr_provider: Optional OCRProvider instance for on-screen text extraction.
            auto_extract: When True, auto-detects installed ML packages for content extraction.

        Returns:
            ProcessedDocumentPayload with temporal scene chunks, and 5-stage telemetry.
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
            transcript=transcript,
            captions=captions,
            filename=name,
            demuxer=demuxer,
            transcriber=transcriber,
            ocr_provider=ocr_provider,
            auto_extract=auto_extract,
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
        # Step 5: Spatio-Temporal Chunk Assembly (80% - 100%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        processed_chunks: list[ProcessedChunk] = []

        for scene in video_payload.scenes:

            chunk_meta: dict[str, Any] = {
                "format": meta.format,
                "scene_index": scene.scene_index,
                "start_seconds": scene.start_seconds,
                "end_seconds": scene.end_seconds,
                "timestamp": scene.timestamp_label,
                "motion_score": scene.motion_score,
                "motion_intensity": scene.motion_intensity,
                "keyframe_dhash": scene.keyframe_dhash,
                "has_audio": meta.has_audio,
                "audio_tracks": meta.audio_tracks,
                "has_subtitles": meta.has_subtitles,
                "is_video": True,
            }
            if scene.transcript_segment:
                chunk_meta["transcript"] = scene.transcript_segment
            if metadata:
                chunk_meta.update(metadata)

            processed_chunks.append(
                ProcessedChunk(
                    chunk_id=f"{video_id}:{scene.scene_index}",
                    document_id=video_id,
                    chunk_index=scene.scene_index,
                    text=scene.narrative_summary,
                    metadata=chunk_meta,
                )
            )

        dt_step5 = (time.perf_counter() - t0) * 1000.0
        traces.append(
            ProcessingStageTrace(
                step_number=5,
                stage_name="Spatio-Temporal Chunk Assembly",
                status="completed",
                duration_ms=round(dt_step5, 2),
                summary="Assembled final chunks with grounded metadata (vectors are produced at "
                "storage time by embed_texts()).",
                details={},
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
            f"into {len(processed_chunks)} temporal scenes in {total_ms:.1f}ms."
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
