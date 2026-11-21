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

"""PCM decoding (WAV, AIFF) and spectral descriptors for the audio processor.

Pure standard library: WAV through ``wave``, AIFF/AIFC chunks parsed directly, and a
small discrete-transform spectral summary (centroid and 7 sub-band energies).
"""

from __future__ import annotations

import io
import math
import struct
import wave

__all__ = ["_decode_aiff_stream", "_decode_wav_stream", "compute_spectral_features"]


def _decode_wav_stream(
    raw_bytes: bytes,
) -> tuple[int, int, int, list[float]]:
    """Decodes standard RIFF/WAVE container into sample rate, channels,
    bit depth, and mono float samples.
    """
    bio = io.BytesIO(raw_bytes)
    with wave.open(bio, "rb") as wf:
        channels = max(1, wf.getnchannels())
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
        # 32-bit audio: try IEEE float first, then signed integer
        fmt_float = f"<{channels}f"
        fmt_int = f"<{channels}i"
        step = 4 * channels
        # Detect format: if values as float are in [-1.0, 1.0] range, it's float
        is_float = False
        if num_frames > 0:
            test_sub = pcm_bytes[:step]
            if len(test_sub) == step:
                test_vals = struct.unpack(fmt_float, test_sub)
                if all(-1.0 <= v <= 1.0 for v in test_vals):
                    is_float = True
        if is_float:
            for i in range(num_frames):
                sub = pcm_bytes[i * step : (i + 1) * step]
                vals = struct.unpack(fmt_float, sub)
                mono = sum(vals) / channels
                samples.append(max(-1.0, min(1.0, mono)))
        else:
            for i in range(num_frames):
                sub = pcm_bytes[i * step : (i + 1) * step]
                vals = struct.unpack(fmt_int, sub)
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
    if len(samples) == 0:
        return 0.0, [0.0] * 7

    # Use a downsampled representation of up to 1024 points for fast computation
    n = len(samples)
    target_len = min(n, 1024)
    step = max(1, n // target_len)
    window = [float(v) for v in samples[::step][:target_len]]
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
