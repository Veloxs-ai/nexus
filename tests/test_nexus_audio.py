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

import io
import math
import struct
import wave

from nexus.client import NexusClient


def make_test_wav(
    duration: float = 2.0,
    sample_rate: int = 16000,
    channels: int = 1,
    freq: float = 440.0,
) -> bytes:
    """Generates a valid 16-bit PCM WAV audio payload in pure standard library."""
    num_samples = int(sample_rate * duration)
    bio = io.BytesIO()
    with wave.open(bio, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = bytearray()
        for i in range(num_samples):
            val = int(32767.0 * 0.5 * math.sin(2.0 * math.pi * freq * i / sample_rate))
            for _ in range(channels):
                frames.extend(struct.pack("<h", val))
        wf.writeframes(frames)
    return bio.getvalue()


def make_test_mp3(title: str = "Quarterly Business Review") -> bytes:
    """Generates a synthetic MP3 payload with an ID3v2 tag."""
    frames = bytearray()
    enc_payload = b"\x03" + title.encode("utf-8")
    frames.extend(b"TIT2")
    frames.extend(len(enc_payload).to_bytes(4, "big"))
    frames.extend(b"\x00\x00")
    frames.extend(enc_payload)

    sz = len(frames)
    s0 = (sz >> 21) & 0x7F
    s1 = (sz >> 14) & 0x7F
    s2 = (sz >> 7) & 0x7F
    s3 = sz & 0x7F
    hdr = b"ID3\x03\x00\x00" + bytes([s0, s1, s2, s3])
    return hdr + frames + b"\xff\xfb\x90\x64" + b"\x00" * 3000


def test_nexus_client_process_audio():
    client = NexusClient(in_memory_only=True)
    wav_bytes = make_test_wav(duration=2.5, sample_rate=16000, channels=1, freq=523.25)

    doc = client.process_audio(
        audio_id="audio_q3_briefing",
        name="briefing.wav",
        audio_bytes=wav_bytes,
        window_seconds=1.0,
        metadata={"department": "operations"},
    )

    assert doc.document_id == "audio_q3_briefing"
    assert doc.name == "briefing.wav"
    assert doc.file_type == "audio"
    assert doc.classification == "audio"
    assert len(doc.chunks) == 3  # 2.5 seconds sliced into 1.0s chunks -> 3 segments

    chunk_0 = doc.chunks[0]
    assert chunk_0.chunk_id == "audio_q3_briefing:0"
    assert "[00:00 - 00:01]" in chunk_0.text
    assert "RMS:" in chunk_0.text
    assert chunk_0.metadata["is_audio"] is True
    assert chunk_0.metadata["audio_format"] == "WAV"
    assert chunk_0.metadata["department"] == "operations"
    assert len(chunk_0.embedding) == 3072

    # Check IEEE 754 L2 unit normalization
    norm = math.sqrt(sum(x * x for x in chunk_0.embedding))
    assert abs(norm - 1.0) < 1e-7

    # Check 5-stage telemetry trace
    assert len(doc.execution_trace) == 5
    for idx, trace in enumerate(doc.execution_trace, start=1):
        assert trace.step_number == idx
        assert trace.status == "completed"
        assert trace.duration_ms >= 0.0

    assert doc.execution_trace[0].stage_name == "Audio Container & Codec Parsing"
    assert doc.execution_trace[1].stage_name == "PCM Signal Extraction & Channel Normalization"
    assert doc.execution_trace[2].stage_name == "Temporal Window Framing & VAD Energy Profiling"
    assert doc.execution_trace[3].stage_name == "Multi-Band Spectral & Rhythm Decomposition"
    assert doc.execution_trace[4].stage_name == "Spatio-Acoustic 3072D Vector Projection"

    # Verify indexing and retrieval
    client.index_document(doc, collection="voice_notes")
    results = client.search("operations briefing acoustic segment", limit=5)
    assert len(results) >= 1
    assert any("audio_q3_briefing" in r.id for r in results)


def test_nexus_client_embed_audio():
    client = NexusClient(in_memory_only=True)
    wav_bytes = make_test_wav(duration=1.0, sample_rate=8000, channels=1, freq=300.0)

    vec = client.embed_audio(wav_bytes, window_seconds=1.0)
    assert len(vec) == 3072
    norm = math.sqrt(sum(x * x for x in vec))
    assert abs(norm - 1.0) < 1e-7


def test_nexus_client_process_document_audio_routing():
    client = NexusClient(in_memory_only=True)

    # Test WAV routing
    wav_bytes = make_test_wav(duration=1.2, sample_rate=16000, channels=1, freq=440.0)
    wav_doc = client.process_document(
        document_id="doc_audio_wav",
        name="recording.wav",
        text=wav_bytes,
        file_type="wav",
    )
    assert wav_doc.document_id == "doc_audio_wav"
    assert wav_doc.file_type == "audio"
    assert len(wav_doc.chunks) >= 1
    assert "[00:00 -" in wav_doc.chunks[0].text
    assert len(wav_doc.chunks[0].embedding) == 3072

    # Test MP3 routing with ID3 tags
    mp3_bytes = make_test_mp3(title="All-Hands Keynote")
    mp3_doc = client.process_document(
        document_id="doc_audio_mp3",
        name="keynote.mp3",
        text=mp3_bytes,
        file_type="mp3",
    )
    assert mp3_doc.document_id == "doc_audio_mp3"
    assert mp3_doc.file_type == "audio"
    assert "All-Hands Keynote" in mp3_doc.chunks[0].text
    assert len(mp3_doc.chunks[0].embedding) == 3072
