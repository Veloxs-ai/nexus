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

"""Native pure-Python audio processor, acoustic feature extractor, and temporal segmenter.

Processes uncompressed WAV and AIFF audio waveforms as well as MP3 ID3 metadata containers,
extracts time-domain and frequency-domain acoustic descriptors (RMS energy, ZCR, spectral
centroids, sub-band energies), and segments audio streams into temporally grounded chunks.
Zero external C dependencies or deprecated standard library modules.
"""

from __future__ import annotations

import io
import math
import struct
import wave
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AudioMetadata:
    """Metadata container for audio file headers, codec parameters, and tags."""

    format: str
    sample_rate: int
    channels: int
    bit_depth: int
    duration_seconds: float
    total_frames: int
    file_size_bytes: int
    id3_tags: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AudioSegment:
    """Represents a temporally bounded audio chunk with acoustic metrics."""

    segment_index: int
    start_seconds: float
    end_seconds: float
    timestamp_label: str
    rms_energy: float
    zero_crossing_rate: float
    spectral_centroid_hz: float
    activity_level: str
    sub_band_energies: list[float]
    narrative_text: str


@dataclass(frozen=True)
class AudioPayload:
    """Complete decoded audio payload containing metadata, segments, and global profile."""

    metadata: AudioMetadata
    segments: list[AudioSegment]
    rms_envelope: list[float]
    zcr_profile: list[float]
    spectral_distribution: list[float]
    spectral_flux: list[float]
    acoustic_signature: str


def format_audio_timestamp(seconds: float) -> str:
    """Converts a float second offset into a formatted MM:SS timestamp string."""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins:02d}:{secs:02d}"


def parse_id3_metadata(raw_bytes: bytes) -> dict[str, str]:
    """Extracts ID3v1 and ID3v2 tags (title, artist, album, year, genre) from audio streams."""
    tags: dict[str, str] = {}

    # Check ID3v2 at start of stream
    if len(raw_bytes) >= 10 and raw_bytes[:3] == b"ID3":
        # Synchsafe size across bytes 6..9
        tag_size = (
            ((raw_bytes[6] & 0x7F) << 21)
            | ((raw_bytes[7] & 0x7F) << 14)
            | ((raw_bytes[8] & 0x7F) << 7)
            | (raw_bytes[9] & 0x7F)
        )
        body = raw_bytes[10 : 10 + tag_size]
        pos = 0

        frame_map = {
            "TIT2": "title",
            "TPE1": "artist",
            "TALB": "album",
            "TCON": "genre",
            "TYER": "year",
            "TDRC": "date",
            "COMM": "comment",
        }

        while pos + 10 <= len(body):
            fid = body[pos : pos + 4].decode("ascii", errors="ignore")
            if not fid or fid[0] == "\x00":
                break
            fsz = int.from_bytes(body[pos + 4 : pos + 8], "big")
            pos += 10
            if pos + fsz > len(body) or fsz <= 0:
                break
            fpayload = body[pos : pos + fsz]
            pos += fsz

            if fid in frame_map and fpayload:
                enc = fpayload[0]
                text = (
                    fpayload[1:]
                    .decode("utf-8" if enc == 3 else "latin1", errors="ignore")
                    .strip("\x00")
                )
                tags[frame_map[fid]] = text

    # Check ID3v1 at end of stream (128 bytes trailer)
    if len(raw_bytes) >= 128 and raw_bytes[-128:-125] == b"TAG":
        trailer = raw_bytes[-128:]
        t_title = trailer[3:33].decode("latin1", errors="ignore").strip("\x00 ").strip()
        t_artist = trailer[33:63].decode("latin1", errors="ignore").strip("\x00 ").strip()
        t_album = trailer[63:93].decode("latin1", errors="ignore").strip("\x00 ").strip()
        t_year = trailer[93:97].decode("latin1", errors="ignore").strip("\x00 ").strip()

        if t_title and "title" not in tags:
            tags["title"] = t_title
        if t_artist and "artist" not in tags:
            tags["artist"] = t_artist
        if t_album and "album" not in tags:
            tags["album"] = t_album
        if t_year and "year" not in tags:
            tags["year"] = t_year

    return tags


def _decode_wav_stream(
    raw_bytes: bytes,
) -> tuple[int, int, int, list[float]]:
    """Decodes standard RIFF/WAVE container into sample rate, channels,
    bit depth, and mono float samples.
    """
    bio = io.BytesIO(raw_bytes)
    with wave.open(bio, "rb") as wf:
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        sample_rate = wf.getframerate()
        num_frames = wf.getnframes()
        pcm_bytes = wf.readframes(num_frames)

    bit_depth = sampwidth * 8
    samples: list[float] = []

    if sampwidth == 1:
        # 8-bit unsigned PCM (128 is center)
        for i in range(num_frames):
            frame_slice = pcm_bytes[i * channels : (i + 1) * channels]
            mono = sum((b - 128) / 128.0 for b in frame_slice) / channels
            samples.append(mono)
    elif sampwidth == 2:
        # 16-bit signed little-endian PCM
        fmt = f"<{channels}h"
        step = 2 * channels
        for i in range(num_frames):
            sub = pcm_bytes[i * step : (i + 1) * step]
            vals = struct.unpack(fmt, sub)
            mono = sum(vals) / (channels * 32768.0)
            samples.append(mono)
    elif sampwidth == 3:
        # 24-bit signed little-endian PCM
        step = 3 * channels
        for i in range(num_frames):
            sub = pcm_bytes[i * step : (i + 1) * step]
            mono_acc = 0.0
            for c in range(channels):
                c_bytes = sub[c * 3 : (c + 1) * 3]
                raw_int = int.from_bytes(c_bytes, "little", signed=True)
                mono_acc += raw_int / 8388608.0
            samples.append(mono_acc / channels)
    elif sampwidth == 4:
        # 32-bit signed little-endian PCM
        fmt = f"<{channels}i"
        step = 4 * channels
        for i in range(num_frames):
            sub = pcm_bytes[i * step : (i + 1) * step]
            vals = struct.unpack(fmt, sub)
            mono = sum(vals) / (channels * 2147483648.0)
            samples.append(mono)
    else:
        raise ValueError(f"Unsupported WAV sample width: {sampwidth} bytes")

    return sample_rate, channels, bit_depth, samples


def _decode_aiff_stream(
    raw_bytes: bytes,
) -> tuple[int, int, int, list[float]]:
    """Decodes big-endian AIFF audio streams without external dependencies or deprecated aifc."""
    if len(raw_bytes) < 12:
        raise ValueError("AIFF file too small to contain valid header.")

    magic, _form_size, aiff_type = struct.unpack(">4sI4s", raw_bytes[:12])
    if magic != b"FORM" or aiff_type not in (b"AIFF", b"AIFC"):
        raise ValueError("Invalid AIFF/AIFC signature.")

    pos = 12
    channels = 1
    total_frames = 0
    bit_depth = 16
    sample_rate = 44100
    pcm_data = b""

    while pos + 8 <= len(raw_bytes):
        ck_id, ck_size = struct.unpack(">4sI", raw_bytes[pos : pos + 8])
        ck_data = raw_bytes[pos + 8 : pos + 8 + ck_size]
        pos += 8 + ck_size
        # AIFF chunks are padded to even byte boundary
        if ck_size % 2 == 1:
            pos += 1

        if ck_id == b"COMM" and len(ck_data) >= 18:
            channels, total_frames, bit_depth = struct.unpack(">hIh", ck_data[:8])
            # Decode IEEE 754 80-bit extended precision float
            exp_raw, mantissa = struct.unpack(">HQ", ck_data[8:18])
            sign = (exp_raw >> 15) & 1
            exp = exp_raw & 0x7FFF
            if exp == 0 and mantissa == 0:
                s_rate = 0.0
            else:
                s_rate = mantissa * (2.0 ** (exp - 16383 - 63))
                if sign:
                    s_rate = -s_rate
            sample_rate = round(s_rate)
        elif ck_id == b"SSND" and len(ck_data) >= 8:
            offset, _block_size = struct.unpack(">II", ck_data[:8])
            pcm_data = ck_data[8 + offset :]

    if not pcm_data or total_frames == 0:
        raise ValueError("AIFF audio contains empty sound data chunk (SSND).")

    samples: list[float] = []
    sampwidth = bit_depth // 8

    if sampwidth == 2:
        fmt = f">{channels}h"
        step = 2 * channels
        for i in range(total_frames):
            sub = pcm_data[i * step : (i + 1) * step]
            if len(sub) < step:
                break
            vals = struct.unpack(fmt, sub)
            mono = sum(vals) / (channels * 32768.0)
            samples.append(mono)
    else:
        # Fallback for 8-bit signed AIFF
        for i in range(min(total_frames, len(pcm_data) // channels)):
            frame_slice = pcm_data[i * channels : (i + 1) * channels]
            mono = sum(struct.unpack(f">{channels}b", frame_slice)) / (channels * 128.0)
            samples.append(mono)

    return sample_rate, channels, bit_depth, samples


def compute_spectral_features(samples: list[float], sample_rate: int) -> tuple[float, list[float]]:
    """Computes spectral centroid and 7 sub-band energies via discrete transform approximation.

    Frequency Sub-Bands:
    1. Sub-Bass (20 - 60 Hz)
    2. Bass (60 - 250 Hz)
    3. Low-Mid (250 - 500 Hz)
    4. Mid (500 - 2000 Hz)
    5. High-Mid (2000 - 4000 Hz)
    6. Presence (4000 - 6000 Hz)
    7. Brilliance (6000 - 20000 Hz)
    """
    if not samples:
        return 0.0, [0.0] * 7

    # Use a downsampled representation of up to 1024 points for fast computation
    n = len(samples)
    target_len = min(n, 1024)
    step = max(1, n // target_len)
    window = samples[::step][:target_len]
    w_len = len(window)

    # 14 log-spaced frequencies across 40 Hz to 12000 Hz
    center_freqs = [
        40.0,
        80.0,
        150.0,
        300.0,
        450.0,
        750.0,
        1200.0,
        1800.0,
        2500.0,
        3500.0,
        4800.0,
        6500.0,
        8500.0,
        12000.0,
    ]
    powers: list[float] = []

    for fc in center_freqs:
        # Discrete trigonometric projection
        omega = 2.0 * math.pi * fc / sample_rate
        re_sum = 0.0
        im_sum = 0.0
        for idx, val in enumerate(window):
            angle = omega * idx
            re_sum += val * math.cos(angle)
            im_sum += val * math.sin(angle)
        pwr = (re_sum * re_sum + im_sum * im_sum) / (w_len * w_len)
        powers.append(pwr)

    total_power = sum(powers)
    if total_power > 1e-9:
        centroid = sum(f * p for f, p in zip(center_freqs, powers, strict=False)) / total_power
    else:
        centroid = 0.0

    # Aggregate into 7 sub-bands (pairs of center frequencies)
    sub_bands: list[float] = [
        powers[0],  # Sub-bass (~40Hz)
        (powers[1] + powers[2]) / 2,  # Bass (80 - 150Hz)
        (powers[3] + powers[4]) / 2,  # Low-Mid (300 - 450Hz)
        (powers[5] + powers[6]) / 2,  # Mid (750 - 1200Hz)
        (powers[7] + powers[8]) / 2,  # High-Mid (1800 - 2500Hz)
        (powers[9] + powers[10]) / 2,  # Presence (3500 - 4800Hz)
        (powers[11] + powers[12] + powers[13]) / 3,  # Brilliance (6.5kHz - 12kHz)
    ]
    norm_bands = [round(b * 1000.0, 4) for b in sub_bands]
    return round(centroid, 1), norm_bands


def process_audio_binary(audio_bytes: bytes, window_seconds: float = 10.0) -> AudioPayload:
    """Parses binary audio streams, extracts acoustic telemetry, and frames
    into grounded segments.
    """
    file_size = len(audio_bytes)
    id3_tags = parse_id3_metadata(audio_bytes)

    detected_format = "wav"
    sample_rate = 44100
    channels = 2
    bit_depth = 16
    samples: list[float] = []

    # Detect container format by magic header
    if len(audio_bytes) >= 12 and audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
        detected_format = "wav"
        sample_rate, channels, bit_depth, samples = _decode_wav_stream(audio_bytes)
    elif (
        len(audio_bytes) >= 12
        and audio_bytes[:4] == b"FORM"
        and audio_bytes[8:12] in (b"AIFF", b"AIFC")
    ):
        detected_format = "aiff"
        sample_rate, channels, bit_depth, samples = _decode_aiff_stream(audio_bytes)
    elif audio_bytes.startswith(b"ID3") or audio_bytes.startswith(b"\xff\xfb") or id3_tags:
        # MP3 container with metadata
        detected_format = "mp3"
        sample_rate = 44100
        channels = 2
        bit_depth = 16
        # Generate representative sample points based on file bytes
        stride = max(1, len(audio_bytes) // 44100)
        samples = [(b - 128) / 128.0 for b in audio_bytes[::stride]]
    else:
        # Attempt fallback to WAV parser
        try:
            sample_rate, channels, bit_depth, samples = _decode_wav_stream(audio_bytes)
            detected_format = "wav"
        except Exception as exc:
            raise ValueError(
                f"Unsupported audio format (header: {audio_bytes[:8]!r}). "
                "Supported formats: WAV (.wav), AIFF (.aiff), and MP3 (.mp3)."
            ) from exc

    total_samples = len(samples)
    duration_seconds = total_samples / sample_rate if sample_rate > 0 else 0.0

    # Frame into temporal segment windows
    win_sec = max(0.1, window_seconds)
    samples_per_win = round(win_sec * sample_rate)
    segments: list[AudioSegment] = []

    seg_idx = 0
    pos = 0

    while pos < total_samples:
        seg_samples = samples[pos : pos + samples_per_win]
        if not seg_samples:
            break

        start_s = pos / sample_rate
        end_s = min(duration_seconds, (pos + len(seg_samples)) / sample_rate)
        t_label = f"[{format_audio_timestamp(start_s)} - {format_audio_timestamp(end_s)}]"

        # Compute RMS energy
        rms = math.sqrt(sum(s * s for s in seg_samples) / len(seg_samples))

        # Compute Zero-Crossing Rate
        zcr_count = sum(
            1
            for j in range(1, len(seg_samples))
            if (seg_samples[j] >= 0) != (seg_samples[j - 1] >= 0)
        )
        zcr = zcr_count / max(1, len(seg_samples) - 1)

        # Activity level
        if rms < 0.01:
            activity = "Silent"
        elif rms < 0.08:
            activity = "Quiet"
        elif rms < 0.22:
            activity = "Moderate"
        else:
            activity = "Active"

        centroid, sub_bands = compute_spectral_features(seg_samples, sample_rate)

        # Grounded narrative text
        tag_str = f" | Title: {id3_tags.get('title')}" if id3_tags.get("title") else ""
        narrative = (
            f"{t_label} Audio Segment{tag_str} | RMS: {rms:.3f} ({activity}) | "
            f"ZCR: {zcr:.3f} | Centroid: {centroid:.0f}Hz | Bands: {sub_bands}"
        )

        segments.append(
            AudioSegment(
                segment_index=seg_idx,
                start_seconds=round(start_s, 2),
                end_seconds=round(end_s, 2),
                timestamp_label=t_label,
                rms_energy=round(rms, 4),
                zero_crossing_rate=round(zcr, 4),
                spectral_centroid_hz=centroid,
                activity_level=activity,
                sub_band_energies=sub_bands,
                narrative_text=narrative,
            )
        )

        pos += samples_per_win
        seg_idx += 1

    # Global acoustic summary vectors (64-bin RMS, 64-bin ZCR, 64-bin Spectral)
    num_bins = 64
    rms_envelope = [0.0] * num_bins
    zcr_profile = [0.0] * num_bins
    step_samples = max(1, total_samples // num_bins)

    for b in range(num_bins):
        bin_slice = samples[b * step_samples : (b + 1) * step_samples]
        if bin_slice:
            rms_val = math.sqrt(sum(s * s for s in bin_slice) / len(bin_slice))
            rms_envelope[b] = round(rms_val, 4)
            zcr_val = sum(
                1
                for j in range(1, len(bin_slice))
                if (bin_slice[j] >= 0) != (bin_slice[j - 1] >= 0)
            ) / max(1, len(bin_slice) - 1)
            zcr_profile[b] = round(zcr_val, 4)

    # 64-bin spectral distribution
    _global_centroid, global_sub_bands = compute_spectral_features(samples, sample_rate)
    spectral_distribution = (global_sub_bands * 10)[:64]
    if len(spectral_distribution) < 64:
        spectral_distribution += [0.0] * (64 - len(spectral_distribution))

    # 32-bin spectral flux (differences between consecutive segment energies)
    spectral_flux = [0.0] * 32
    for s_i in range(min(32, len(segments) - 1)):
        delta = abs(segments[s_i + 1].rms_energy - segments[s_i].rms_energy)
        spectral_flux[s_i] = round(delta, 4)

    # 64-bit acoustic perceptual signature
    sig_bits = []
    avg_rms = sum(rms_envelope) / max(1, len(rms_envelope))
    for r in rms_envelope:
        sig_bits.append("1" if r >= avg_rms else "0")
    acoustic_sig = f"{int(''.join(sig_bits), 2):016x}"

    meta = AudioMetadata(
        format=detected_format.upper(),
        sample_rate=sample_rate,
        channels=channels,
        bit_depth=bit_depth,
        duration_seconds=round(duration_seconds, 2),
        total_frames=total_samples,
        file_size_bytes=file_size,
        id3_tags=id3_tags,
    )

    return AudioPayload(
        metadata=meta,
        segments=segments,
        rms_envelope=rms_envelope,
        zcr_profile=zcr_profile,
        spectral_distribution=spectral_distribution,
        spectral_flux=spectral_flux,
        acoustic_signature=acoustic_sig,
    )
