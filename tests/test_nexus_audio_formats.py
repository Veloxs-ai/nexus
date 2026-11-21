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

"""Compressed audio (MP3, M4A, OGG, FLAC) decoded with PyAV: real duration, routing,
transcript chunks. Skipped when PyAV (extra ``[video]``) is not installed."""

from __future__ import annotations

import io
import math

import pytest

from nexus import NexusClient

av = pytest.importorskip("av")
np = pytest.importorskip("numpy")


def encode_tone(container: str, codec: str, seconds: float = 6.0, rate: int = 44100) -> bytes:
    buf = io.BytesIO()
    with av.open(buf, mode="w", format=container) as out:
        stream = out.add_stream(codec, rate=rate)
        stream.layout = "stereo"
        fmt = stream.codec_context.format.name
        frame_size = stream.codec_context.frame_size or 1024
        total = int(seconds * rate)
        t = np.arange(total) / rate
        wave = (0.3 * np.sin(2 * math.pi * 440 * t)).astype("float32")
        for start in range(0, total, frame_size):
            chunk = wave[start : start + frame_size]
            planar = np.vstack([chunk, chunk])
            if fmt in ("s16", "s16p"):
                planar = (planar * 32767).astype("int16")
            elif fmt in ("s32", "s32p"):
                planar = (planar * 2147483647).astype("int32")
            data = planar if fmt.endswith("p") else planar.T.reshape(1, -1)
            frame = av.AudioFrame.from_ndarray(
                np.ascontiguousarray(data), format=fmt, layout="stereo"
            )
            frame.sample_rate = rate
            for packet in stream.encode(frame):
                out.mux(packet)
        for packet in stream.encode(None):
            out.mux(packet)
    return buf.getvalue()


class _Transcriber:
    def transcribe(self, _audio: bytes) -> tuple[str, list[dict]]:
        segs = [
            {"start": 0.0, "end": 2.5, "text": "Renewals closed early."},
            {"start": 2.5, "end": 5.5, "text": "Churn fell in the north."},
        ]
        return " ".join(s["text"] for s in segs), segs


@pytest.mark.parametrize(
    ("ext", "container", "codec", "fmt"),
    [
        ("mp3", "mp3", "libmp3lame", "MP3"),
        ("m4a", "ipod", "aac", "M4A"),
        ("ogg", "ogg", "libopus", "OGG"),
        ("flac", "flac", "flac", "FLAC"),
    ],
)
def test_compressed_audio_is_decoded_routed_and_chunked_by_transcript(ext, container, codec, fmt):
    try:
        data = encode_tone(container, codec, rate=48000 if codec == "libopus" else 44100)
    except Exception as exc:  # encoder not built into this FFmpeg
        pytest.skip(f"{codec} encoder unavailable: {exc}")
    doc = NexusClient().process_document("a", f"clip.{ext}", data, transcriber=_Transcriber())
    assert doc.file_type == "audio"
    assert doc.metadata["format"] == fmt
    assert 5.5 <= doc.metadata["duration_seconds"] <= 6.6
    assert len(doc.chunks) == 1
    assert 'Transcript: "Renewals closed early. Churn fell in the north."' in doc.chunks[0].text


def test_untranscribed_compressed_audio_gets_real_acoustic_windows():
    try:
        data = encode_tone("flac", "flac", seconds=12.0)
    except Exception as exc:
        pytest.skip(f"flac encoder unavailable: {exc}")
    doc = NexusClient().process_audio("a", "tone.flac", audio_bytes=data, window_seconds=5.0)
    assert len(doc.chunks) == 3 and doc.chunks[0].metadata["activity_level"] != "Silent"
