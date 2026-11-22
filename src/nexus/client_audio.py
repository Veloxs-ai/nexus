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

"""``NexusClient.process_audio``: audio bytes to time-windowed transcript chunks.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from nexus.chunk_limits import bounded_output
from nexus.models import ProcessedChunk, ProcessedDocumentPayload, ProcessingStageTrace

try:
    from nexus.processing.audio import process_audio_binary
except (ImportError, ModuleNotFoundError):
    from nexus_processing.audio import process_audio_binary

__all__ = ["AudioMixin"]


class AudioMixin:
    """Mixed into ``NexusClient``."""

    @bounded_output
    def process_audio(
        self,
        audio_id: str,
        name: str,
        audio_bytes: bytes | None = None,
        file_path: str | Path | None = None,
        window_seconds: float = 10.0,
        transcript: str | None = None,
        speaker: str | None = None,
        metadata: dict[str, Any] | None = None,
        enable_guardrails: bool = True,
        shallow_mode: bool = False,
        transcriber: Any | None = None,
        auto_extract: bool = False,
    ) -> ProcessedDocumentPayload:
        """Processes an audio file through native pure-Python container decoding,
        PCM extraction, VAD energy profiling, spectral decomposition, PII sanitization.

        Args:
            audio_id: Unique identifier for the audio resource.
            name: Filename or descriptor (e.g. 'call_recording.wav', 'track.mp3').
            audio_bytes: Raw binary audio payload.
            file_path: Optional path to read audio file from disk if audio_bytes not provided.
            window_seconds: Temporal framing interval in seconds (default: 10.0).
            transcript: Optional full speech transcript text.
            speaker: Optional speaker name or persona description.
            metadata: Custom metadata dictionary to attach to audio document and segment chunks.
            enable_guardrails: When True (default), scrubs sensitive PII in ID3 tags.
            shallow_mode: Alias for bypassing PII sanitization.
            transcriber: Optional AudioTranscriber instance for speech-to-text.
            auto_extract: When True, auto-detects installed ML packages for transcription.

        Returns:
            ProcessedDocumentPayload with temporal chunks, and traces.
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
        audio_payload = process_audio_binary(
            raw_data,
            window_seconds=window_seconds,
            transcript=transcript,
            speaker=speaker,
            filename=name,
            transcriber=transcriber,
            auto_extract=auto_extract,
        )
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
        # Step 5: Spatio-Acoustic Chunk Assembly (80% - 100%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        processed_chunks: list[ProcessedChunk] = []

        for seg in audio_payload.segments:
            seg_text = seg.narrative_text
            if apply_guardrails:
                seg_text = self.guardrails.mask_pii(seg_text)


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
            if meta.speaker:
                chunk_meta["speaker"] = meta.speaker
            if seg.transcript:
                chunk_meta["transcript"] = seg.transcript
            elif meta.transcript:
                chunk_meta["transcript"] = meta.transcript
            if meta.voice_metadata:
                chunk_meta["voice_metadata"] = meta.voice_metadata
            if metadata:
                chunk_meta.update(metadata)

            processed_chunks.append(
                ProcessedChunk(
                    chunk_id=f"{audio_id}:{seg.segment_index}",
                    document_id=audio_id,
                    chunk_index=seg.segment_index,
                    text=seg_text,
                    metadata=chunk_meta,
                )
            )

        dt_step5 = (time.perf_counter() - t0) * 1000.0
        traces.append(
            ProcessingStageTrace(
                step_number=5,
                stage_name="Spatio-Acoustic Chunk Assembly",
                status="completed",
                duration_ms=round(dt_step5, 2),
                summary="Assembled final chunks with grounded metadata (vectors are produced at "
                "storage time by embed_texts()).",
                details={},
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
        if meta.speaker:
            doc_meta["speaker"] = meta.speaker
        if meta.transcript:
            doc_meta["transcript"] = meta.transcript
        if meta.voice_metadata:
            doc_meta["voice_metadata"] = meta.voice_metadata
        if metadata:
            doc_meta.update(metadata)

        total_ms = (time.perf_counter() - t_start_total) * 1000.0
        summary_msg = (
            f"Processed {meta.format} audio '{name}' ({meta.duration_seconds}s) "
            f"into {len(processed_chunks)} chunks in {total_ms:.1f}ms."
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
