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

import io
import math
import struct
import wave

from nexus_processing.audio import (
    compute_spectral_features,
    format_audio_timestamp,
    parse_id3_metadata,
    process_audio_binary,
)


def make_test_wav(
    duration: float = 1.0,
    sample_rate: int = 16000,
    channels: int = 1,
    freq: float = 440.0,
) -> bytes:
    """Generates a valid PCM 16-bit WAV audio payload in pure standard library."""
    num_samples = int(sample_rate * duration)
    bio = io.BytesIO()
    with wave.open(bio, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = bytearray()
        for i in range(num_samples):
            val = int(32767.0 * 0.6 * math.sin(2.0 * math.pi * freq * i / sample_rate))
            for _ in range(channels):
                frames.extend(struct.pack("<h", val))
        wf.writeframes(frames)
    return bio.getvalue()


def make_test_aiff(
    duration: float = 0.5,
    sample_rate: int = 22050,
    channels: int = 1,
    freq: float = 880.0,
) -> bytes:
    """Generates a valid big-endian 16-bit AIFF audio payload."""
    num_frames = int(sample_rate * duration)

    # 1. COMM chunk
    # IEEE 754 80-bit float for sample_rate (e.g. 22050 = 0x400D AD40 0000 0000 0000)
    # Generic encoder for integer sample rate to 80-bit extended
    exp = 16383 + 14  # for 22050 (between 2^14 and 2^15)
    mantissa = int(sample_rate * (2.0 ** (63 - 14)))
    rate_80 = struct.pack(">HQ", exp, mantissa)

    comm_payload = struct.pack(">hIh", channels, num_frames, 16) + rate_80
    comm_chunk = struct.pack(">4sI", b"COMM", len(comm_payload)) + comm_payload

    # 2. SSND chunk
    pcm_bytes = bytearray()
    for i in range(num_frames):
        val = int(32767.0 * 0.5 * math.sin(2.0 * math.pi * freq * i / sample_rate))
        for _ in range(channels):
            pcm_bytes.extend(struct.pack(">h", val))

    ssnd_payload = struct.pack(">II", 0, 0) + bytes(pcm_bytes)
    ssnd_chunk = struct.pack(">4sI", b"SSND", len(ssnd_payload)) + ssnd_payload

    form_payload = b"AIFF" + comm_chunk + ssnd_chunk
    header = struct.pack(">4sI", b"FORM", len(form_payload))
    return header + form_payload


def make_test_id3v2(title: str = "Quarterly Call", artist: str = "Finance Team") -> bytes:
    """Generates an ID3v2 header and frames prepended to simulated MP3 data."""
    frames = bytearray()
    for fid, txt in [("TIT2", title), ("TPE1", artist)]:
        enc_payload = b"\x03" + txt.encode("utf-8")
        frames.extend(fid.encode("ascii"))
        frames.extend(len(enc_payload).to_bytes(4, "big"))
        frames.extend(b"\x00\x00")
        frames.extend(enc_payload)

    sz = len(frames)
    s0 = (sz >> 21) & 0x7F
    s1 = (sz >> 14) & 0x7F
    s2 = (sz >> 7) & 0x7F
    s3 = sz & 0x7F
    hdr = b"ID3\x03\x00\x00" + bytes([s0, s1, s2, s3])
    # Append simulated MP3 audio frame header (0xFFFB)
    return hdr + frames + b"\xff\xfb\x90\x64" + b"\x00" * 2000


def test_format_audio_timestamp():
    assert format_audio_timestamp(0.0) == "00:00"
    assert format_audio_timestamp(65.4) == "01:05"
    assert format_audio_timestamp(3600.0) == "60:00"


def test_process_audio_wav_mono():
    wav_data = make_test_wav(duration=2.0, sample_rate=16000, channels=1, freq=440.0)
    payload = process_audio_binary(wav_data, window_seconds=1.0)

    meta = payload.metadata
    assert meta.format == "WAV"
    assert meta.sample_rate == 16000
    assert meta.channels == 1
    assert meta.bit_depth == 16
    assert abs(meta.duration_seconds - 2.0) < 0.05
    assert len(payload.segments) == 2

    seg0 = payload.segments[0]
    assert seg0.timestamp_label == "[00:00 - 00:01]"
    assert seg0.rms_energy > 0.3  # Expected ~0.42 for peak 0.6
    assert seg0.activity_level == "Active"
    assert len(seg0.sub_band_energies) == 7

    assert len(payload.rms_envelope) == 64
    assert len(payload.zcr_profile) == 64
    assert len(payload.spectral_distribution) == 64
    assert len(payload.acoustic_signature) == 16


def test_process_audio_wav_stereo_and_silence():
    # 1.5 seconds stereo
    wav_stereo = make_test_wav(duration=1.5, sample_rate=8000, channels=2, freq=220.0)
    payload = process_audio_binary(wav_stereo, window_seconds=0.5)

    assert payload.metadata.channels == 2
    assert payload.metadata.sample_rate == 8000
    assert len(payload.segments) == 3

    # Pure silence test
    bio = io.BytesIO()
    with wave.open(bio, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        wf.writeframes(b"\x00\x00" * 4000)
    silence_payload = process_audio_binary(bio.getvalue())
    assert silence_payload.segments[0].activity_level == "Silent"
    assert silence_payload.segments[0].rms_energy == 0.0


def test_process_audio_aiff():
    aiff_data = make_test_aiff(duration=0.4, sample_rate=22050, channels=1, freq=440.0)
    payload = process_audio_binary(aiff_data, window_seconds=0.5)

    meta = payload.metadata
    assert meta.format == "AIFF"
    assert meta.channels == 1
    assert meta.bit_depth == 16
    assert meta.duration_seconds > 0.3
    assert len(payload.segments) >= 1
    assert payload.segments[0].rms_energy > 0.2


def test_process_audio_id3_metadata():
    mp3_data = make_test_id3v2(title="Strategic Vision", artist="Aditya Executive")
    tags = parse_id3_metadata(mp3_data)
    assert tags.get("title") == "Strategic Vision"
    assert tags.get("artist") == "Aditya Executive"

    payload = process_audio_binary(mp3_data)
    assert payload.metadata.format == "MP3"
    assert payload.metadata.id3_tags["title"] == "Strategic Vision"
    assert "Strategic Vision" in payload.segments[0].narrative_text


def test_compute_spectral_features():
    sample_rate = 16000
    # High frequency tone (3000 Hz)
    high_tone = [math.sin(2.0 * math.pi * 3000.0 * i / sample_rate) for i in range(1000)]
    # Low frequency tone (100 Hz)
    low_tone = [math.sin(2.0 * math.pi * 100.0 * i / sample_rate) for i in range(1000)]

    c_high, bands_high = compute_spectral_features(high_tone, sample_rate)
    c_low, bands_low = compute_spectral_features(low_tone, sample_rate)

    assert c_high > c_low
    assert len(bands_high) == 7
    assert len(bands_low) == 7
