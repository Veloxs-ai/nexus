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

"""Compressed-audio decoding and transcript-segment chunking.

``decode_audio`` decodes MP3, M4A/AAC, OGG/Opus, FLAC (anything FFmpeg reads) with
PyAV (optional extra ``[video]``) to 16 kHz mono float samples, so the duration is the
real one rather than an estimate from the file size.

``group_transcript`` turns timed transcript segments into chunks of whole segments
(at most ~60 s or ~180 words each): every transcribed word lands in exactly one chunk,
whatever the audio's length or the window size. ``split_transcript`` does the same
for an untimed transcript.
"""

from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass
from typing import Any

__all__ = [
    "DecodedAudio",
    "TranscriptGroup",
    "decode_audio",
    "group_transcript",
    "rms_zcr",
    "split_transcript",
]

TARGET_RATE = 16000
MAX_GROUP_SECONDS = 60.0
MAX_GROUP_WORDS = 180


@dataclass(frozen=True)
class DecodedAudio:
    format: str
    sample_rate: int
    channels: int
    samples: Any  # numpy float32 array, mono


@dataclass(frozen=True)
class TranscriptGroup:
    start: float
    end: float
    text: str


def _container_name(audio_bytes: bytes, fallback: str) -> str:
    if audio_bytes[:4] == b"OggS":
        return "ogg"
    if audio_bytes[:4] == b"fLaC":
        return "flac"
    if len(audio_bytes) >= 12 and audio_bytes[4:8] == b"ftyp":
        return "m4a"
    if audio_bytes[:3] == b"ID3" or audio_bytes[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "mp3"
    return fallback.split(",")[0] or "audio"


def decode_audio(audio_bytes: bytes, target_rate: int = TARGET_RATE) -> DecodedAudio | None:
    """Decode any FFmpeg-readable audio to mono ``target_rate`` samples (``None`` if PyAV
    is not installed or the bytes are not decodable audio)."""
    try:
        import av
        import numpy as np
    except ImportError:
        return None
    parts: list[Any] = []
    try:
        with av.open(io.BytesIO(audio_bytes), mode="r") as container:
            stream = next((s for s in container.streams if s.type == "audio"), None)
            if stream is None:
                return None
            channels = int(getattr(stream.codec_context, "channels", 0) or 1)
            name = _container_name(audio_bytes, container.format.name or "")
            resampler = av.AudioResampler(format="flt", layout="mono", rate=target_rate)
            for frame in container.decode(stream):
                for out in resampler.resample(frame):
                    parts.append(out.to_ndarray().reshape(-1))
            for out in resampler.resample(None):
                parts.append(out.to_ndarray().reshape(-1))
    except Exception:
        return None
    if not parts:
        return None
    samples = np.concatenate(parts).astype("float32", copy=False)
    return DecodedAudio(format=name, sample_rate=target_rate, channels=channels, samples=samples)


def rms_zcr(samples: Any) -> tuple[float, float]:
    """RMS energy and zero-crossing rate of a numpy array or a list of floats."""
    n = len(samples)
    if n == 0:
        return 0.0, 0.0
    if hasattr(samples, "dtype"):
        import numpy as np

        rms = float(np.sqrt(np.mean(np.square(samples, dtype="float64"))))
        signs = samples >= 0
        crossings = int(np.count_nonzero(signs[1:] != signs[:-1]))
    else:
        rms = math.sqrt(sum(s * s for s in samples) / n)
        crossings = sum(1 for j in range(1, n) if (samples[j] >= 0) != (samples[j - 1] >= 0))
    return rms, crossings / max(1, n - 1)


def group_transcript(
    segments: list[dict[str, Any]],
    max_seconds: float = MAX_GROUP_SECONDS,
    max_words: int = MAX_GROUP_WORDS,
) -> list[TranscriptGroup]:
    """Whole transcript segments packed into groups; no segment is split or dropped."""
    groups: list[TranscriptGroup] = []
    texts: list[str] = []
    start = end = 0.0
    words = 0
    ordered = sorted(
        (s for s in segments if str(s.get("text", "")).strip()),
        key=lambda s: float(s.get("start", 0.0) or 0.0),
    )
    for seg in ordered:
        text = str(seg.get("text", "")).strip()
        seg_start = float(seg.get("start", 0.0) or 0.0)
        seg_end = max(seg_start, float(seg.get("end", seg_start) or seg_start))
        seg_words = len(text.split())
        if texts and (seg_end - start > max_seconds or words + seg_words > max_words):
            groups.append(TranscriptGroup(start, end, " ".join(texts)))
            texts, words = [], 0
        if not texts:
            start = seg_start
        texts.append(text)
        words += seg_words
        end = max(end, seg_end) if len(texts) > 1 else seg_end
    if texts:
        groups.append(TranscriptGroup(start, end, " ".join(texts)))
    return groups


def split_transcript(
    transcript: str, duration: float, max_words: int = MAX_GROUP_WORDS
) -> list[TranscriptGroup]:
    """An untimed transcript as sentence-aligned groups of about ``max_words`` words.

    Each group gets a time span proportional to its position in the text.
    """
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", transcript.strip()) if s]
    pieces: list[str] = []
    current: list[str] = []
    words = 0
    for sentence in sentences:
        n = len(sentence.split())
        if current and words + n > max_words:
            pieces.append(" ".join(current))
            current, words = [], 0
        current.append(sentence)
        words += n
    if current:
        pieces.append(" ".join(current))
    total = sum(len(p.split()) for p in pieces) or 1
    groups: list[TranscriptGroup] = []
    seen = 0
    for piece in pieces:
        n = len(piece.split())
        start = duration * seen / total
        seen += n
        groups.append(TranscriptGroup(round(start, 2), round(duration * seen / total, 2), piece))
    return groups
