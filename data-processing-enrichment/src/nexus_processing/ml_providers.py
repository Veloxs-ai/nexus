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

"""ML-powered content extraction providers for Nexus.

Defines Protocol interfaces and built-in adapters for OCR,
audio transcription, caption generation, and video demuxing.
All ML dependencies are lazy-loaded and optional.
"""

from __future__ import annotations

import gc
import importlib.util
import sys
import time as _time
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "AudioTranscriber",
    "CaptionProvider",
    "EasyOCRProvider",
    "FasterWhisperTranscriber",
    "OCRProvider",
    "PyAVDemuxer",
    "VideoDemuxer",
    "auto_detect_demuxer",
    "auto_detect_ocr_provider",
    "auto_detect_transcriber",
    "is_easyocr_available",
    "is_faster_whisper_available",
    "is_package_available",
    "is_pyav_available",
]


def is_package_available(package_name: str) -> bool:
    """Check if a given Python package is installed and importable."""
    return importlib.util.find_spec(package_name) is not None


def is_easyocr_available() -> bool:
    """Check if the 'easyocr' package is available."""
    return is_package_available("easyocr")


def is_faster_whisper_available() -> bool:
    """Check if the 'faster_whisper' package is available."""
    return is_package_available("faster_whisper")


def is_pyav_available() -> bool:
    """Check if the 'av' (PyAV) package is available."""
    return is_package_available("av")


@runtime_checkable
class OCRProvider(Protocol):
    """Protocol for Optical Character Recognition (OCR) providers."""

    def extract_text(self, image_bytes: bytes) -> str:
        """Extract text from image bytes."""
        ...


@runtime_checkable
class CaptionProvider(Protocol):
    """Protocol for image caption generation providers."""

    def generate_caption(self, image_bytes: bytes) -> str:
        """Generate a text caption for image bytes."""
        ...


@runtime_checkable
class AudioTranscriber(Protocol):
    """Protocol for audio transcription providers."""

    def transcribe(self, audio_bytes: bytes) -> tuple[str, list[dict]]:
        """
        Transcribe audio bytes.
        
        Returns:
            A tuple of (full_text, segments) where segments is a list of dictionaries
            containing 'start', 'end', and 'text' keys.
        """
        ...


@runtime_checkable
class VideoDemuxer(Protocol):
    """Protocol for video demuxing (extracting audio and keyframes)."""

    def extract_audio(self, video_bytes: bytes) -> bytes | None:
        """Extract audio track from video bytes."""
        ...

    def extract_keyframes(
        self, video_bytes: bytes, max_frames: int = 50
    ) -> list[tuple[float, bytes]]:
        """
        Extract keyframes from video bytes.
        
        Returns:
            A list of tuples (timestamp_seconds, jpeg_bytes).
        """
        ...


def best_torch_device() -> str:
    """cuda > mps (Apple Silicon) > cpu. Override with NEXUS_ML_DEVICE."""
    import os

    forced = os.environ.get("NEXUS_ML_DEVICE", "").strip().lower()
    if forced in ("cpu", "cuda", "mps"):
        return forced
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


OCR_MAX_SIDE = 2560  # EasyOCR's own canvas limit; larger images only cost decode time


class EasyOCRProvider:
    """OCR provider using EasyOCR (CRAFT text detector + CRNN recognizer, PyTorch).

    Requires: pip install 'veloxs-nexus[ocr]'. Runs on CUDA or Apple MPS when
    available (``gpu=None`` = auto), otherwise CPU.
    """

    def __init__(self, languages: list[str] | None = None, gpu: bool | None = None):
        # Store config but DON'T import easyocr yet
        self._languages = languages or ["en"]
        self._gpu = (best_torch_device() != "cpu") if gpu is None else gpu
        self._reader = None  # lazy init
        self._lock = __import__("threading").Lock()
        self._last_used = 0.0

    def release_if_idle(self, max_idle_seconds: float) -> bool:
        """Drop the loaded model when unused for ``max_idle_seconds`` (reloads on demand)."""
        with self._lock:
            if self._reader is None or _time.monotonic() - self._last_used < max_idle_seconds:
                return False
            self._reader = None
            return True

    def _get_reader(self):
        if self._reader is None:
            if not is_easyocr_available():
                raise ImportError(
                    "EasyOCR is required for OCR. "
                    "Install via: pip install 'veloxs-nexus[ocr]'"
                )
            import easyocr
            self._reader = easyocr.Reader(self._languages, gpu=self._gpu, verbose=False)
        return self._reader

    @staticmethod
    def _downscale(image_bytes: bytes) -> bytes:
        try:
            import io

            from PIL import Image

            img = Image.open(io.BytesIO(image_bytes))
            if max(img.size) <= OCR_MAX_SIDE:
                return image_bytes
            img.thumbnail((OCR_MAX_SIDE, OCR_MAX_SIDE))
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=90)
            return buf.getvalue()
        except Exception:
            return image_bytes

    def extract_text(self, image_bytes: bytes) -> str:
        """Extract text from image bytes using EasyOCR."""
        image_bytes = self._downscale(image_bytes)
        with self._lock:  # one inference at a time per shared model
            results = self._get_reader().readtext(image_bytes, detail=0)
            self._last_used = _time.monotonic()
        return " ".join(results).strip()


class FasterWhisperTranscriber:
    """Audio transcriber using faster-whisper. Requires: pip install 'veloxs-nexus[audio-ml]'"""

    def __init__(self, model_size: str = "base", device: str = "auto", compute_type: str = "auto"):
        # CTranslate2 (faster-whisper) supports CUDA or CPU (int8) — not Apple MPS.
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._model = None  # lazy init
        self._lock = __import__("threading").Lock()
        self._last_used = 0.0

    def release_if_idle(self, max_idle_seconds: float) -> bool:
        """Drop the loaded model when unused for ``max_idle_seconds`` (reloads on demand)."""
        with self._lock:
            if self._model is None or _time.monotonic() - self._last_used < max_idle_seconds:
                return False
            self._model = None
            return True

    def _get_model(self):
        if self._model is None:
            if not is_faster_whisper_available():
                raise ImportError(
                    "faster-whisper is required for audio transcription. "
                    "Install via: pip install 'veloxs-nexus[audio-ml]'"
                )
            from faster_whisper import WhisperModel
            device = self._device
            compute_type = self._compute_type
            if device == "auto":
                try:
                    import torch
                    device = "cuda" if torch.cuda.is_available() else "cpu"
                except ImportError:
                    device = "cpu"
            if compute_type == "auto":
                compute_type = "float16" if device == "cuda" else "int8"
            self._model = WhisperModel(self._model_size, device=device, compute_type=compute_type)
        return self._model

    def transcribe(self, audio_bytes: bytes) -> tuple[str, list[dict]]:
        """Transcribe audio bytes using Faster Whisper."""
        import io
        with self._lock:  # segments are generated lazily: keep the model pinned while iterating
            segments, _info = self._get_model().transcribe(
                io.BytesIO(audio_bytes),
                vad_filter=True,
                word_timestamps=True,
            )
            segments = list(segments)
            self._last_used = _time.monotonic()
        full_text_parts = []
        timed_segments = []
        for seg in segments:
            text = seg.text.strip()
            if text:
                full_text_parts.append(text)
                timed_segments.append({
                    "start": round(seg.start, 2),
                    "end": round(seg.end, 2),
                    "text": text,
                })
        return " ".join(full_text_parts), timed_segments


class PyAVDemuxer:
    """Video demuxer using PyAV (FFmpeg). Requires: pip install 'veloxs-nexus[video]'"""
    
    def extract_audio(self, video_bytes: bytes) -> bytes | None:
        """Extract audio stream from video bytes using PyAV."""
        if not is_pyav_available():
            raise ImportError(
                "PyAV is required for video demuxing. "
                "Install via: pip install 'veloxs-nexus[video]'"
            )
        import io

        import av

        container = av.open(io.BytesIO(video_bytes))
        if not container.streams.audio:
            container.close()
            return None
        audio_stream = container.streams.audio[0]
        out_buf = io.BytesIO()
        out_container = av.open(out_buf, mode="w", format="wav")
        out_stream = out_container.add_stream("pcm_s16le", rate=16000)
        out_stream.layout = "mono"
        for frame in container.decode(audio_stream):
            frame.pts = None  # let encoder set pts
            for packet in out_stream.encode(frame):
                out_container.mux(packet)
        for packet in out_stream.encode():
            out_container.mux(packet)
        out_container.close()
        container.close()
        return out_buf.getvalue()
    
    def extract_keyframes(
        self, video_bytes: bytes, max_frames: int = 50
    ) -> list[tuple[float, bytes]]:
        """Extract keyframes from video bytes using PyAV."""
        if not is_pyav_available():
            raise ImportError(
                "PyAV is required for video demuxing. "
                "Install via: pip install 'veloxs-nexus[video]'"
            )
        import io

        import av

        container = av.open(io.BytesIO(video_bytes))
        keyframes = []
        if not container.streams.video:
            container.close()
            return keyframes
        video_stream = container.streams.video[0]
        video_stream.codec_context.skip_frame = "NONKEY"
        for frame in container.decode(video_stream):
            if frame.key_frame:
                img = frame.to_image()  # PIL Image
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
                pts_sec = (
                    float(frame.pts * video_stream.time_base)
                    if frame.pts is not None
                    else 0.0
                )
                keyframes.append((pts_sec, buf.getvalue()))
                if len(keyframes) >= max_frames:
                    break
        container.close()
        return keyframes


_shared: dict[str, Any] = {}
_shared_lock = __import__("threading").Lock()


def _singleton(key: str, factory):
    with _shared_lock:
        if key not in _shared:
            _shared[key] = factory()
        return _shared[key]


def release_idle_models(max_idle_seconds: float = 600) -> list[str]:
    """Unload shared OCR / Whisper models idle for ``max_idle_seconds``; returns what was released.

    Long-running services call this periodically so memory is only held while media
    is being processed (a model reloads transparently on its next use).
    """
    with _shared_lock:
        items = list(_shared.items())
    released = [key for key, provider in items
                if getattr(provider, "release_if_idle", None) and provider.release_if_idle(max_idle_seconds)]
    if released:
        gc.collect()
        torch = sys.modules.get("torch")  # only if already imported: never load torch here
        try:
            if torch is not None and torch.cuda.is_available():
                torch.cuda.empty_cache()
            elif torch is not None and getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                torch.mps.empty_cache()
        except Exception:
            pass
    return released


def auto_detect_ocr_provider() -> OCRProvider | None:
    """Process-wide shared OCR provider (the model loads once, not per image)."""
    if is_easyocr_available():
        return _singleton("ocr", EasyOCRProvider)
    return None


def auto_detect_transcriber() -> AudioTranscriber | None:
    """Process-wide shared transcriber (the Whisper model loads once)."""
    if is_faster_whisper_available():
        return _singleton("whisper", FasterWhisperTranscriber)
    return None

def auto_detect_demuxer() -> VideoDemuxer | None:
    """Auto-detect and return an available VideoDemuxer if possible."""
    if is_pyav_available():
        return PyAVDemuxer()
    return None
