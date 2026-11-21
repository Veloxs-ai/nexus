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

Decodes uncompressed WAV and AIFF natively and, with PyAV (optional), compressed audio
(MP3, M4A/AAC, OGG/Opus, FLAC). Transcribed audio is chunked by transcript segments, so
every word is kept; audio without a transcript is framed into fixed windows with
time-domain and frequency-domain descriptors (RMS energy, ZCR, spectral centroid,
sub-band energies).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .audio_pcm import _decode_aiff_stream, _decode_wav_stream, compute_spectral_features
from .audio_transcript import decode_audio, group_transcript, rms_zcr, split_transcript


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
    speaker: str | None = None
    transcript: str | None = None
    voice_metadata: dict[str, str] = field(default_factory=dict)


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
    transcript: str | None = None
    speaker: str | None = None


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
    transcript: str | None = None
    speaker: str | None = None


def format_audio_timestamp(seconds: float) -> str:
    """Converts a float second offset into a formatted MM:SS timestamp string."""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins:02d}:{secs:02d}"


def parse_voice_filename(filename: str) -> dict[str, str]:
    """Parses voice synthesis metadata, persona, and generation parameters from audio filename."""
    meta: dict[str, str] = {}
    if not filename:
        return meta

    stem = Path(filename).stem
    el_pattern = re.compile(
        r"^ElevenLabs_([0-9]{4}-[0-9]{2}-[0-9]{2}[T_0-9]+)_([^_]+)(?:_(.+))?$",
        re.IGNORECASE,
    )
    match = el_pattern.match(stem)
    if match:
        meta["provider"] = "ElevenLabs"
        meta["timestamp"] = match.group(1).replace("_", ":")
        speaker_raw = match.group(2).strip()
        meta["speaker"] = speaker_raw
        if match.group(3):
            params_raw = match.group(3)
            meta["parameters"] = params_raw
            sp_match = re.search(r"sp(\d+)", params_raw)
            if sp_match:
                meta["stability"] = f"{sp_match.group(1)}%"
            s_match = re.search(r"(?:^|_)s(\d+)", params_raw)
            if s_match:
                meta["similarity"] = f"{s_match.group(1)}%"
            sb_match = re.search(r"sb(\d+)", params_raw)
            if sb_match:
                meta["style_boost"] = f"{sb_match.group(1)}%"
            se_match = re.search(r"se(\d+)", params_raw)
            if se_match:
                meta["speaker_boost"] = f"{se_match.group(1)}%"
    return meta


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
                if enc == 3:
                    charset = "utf-8"
                elif enc in (1, 2):
                    charset = "utf-16"
                else:
                    charset = "latin1"
                text = (
                    fpayload[1:]
                    .decode(charset, errors="ignore")
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


def process_audio_binary(
    audio_bytes: bytes,
    window_seconds: float = 10.0,
    transcript: str | None = None,
    speaker: str | None = None,
    filename: str | None = None,
    transcriber: Any | None = None,
    auto_extract: bool = False,
) -> AudioPayload:
    """Parses binary audio streams, extracts acoustic telemetry, and frames
    into grounded segments.
    """
    file_size = len(audio_bytes)
    id3_tags = parse_id3_metadata(audio_bytes)
    voice_info = parse_voice_filename(filename or "")
    if speaker is None and "speaker" in voice_info:
        speaker = voice_info["speaker"]

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
    elif (decoded := decode_audio(audio_bytes)) is not None:
        # MP3, M4A/AAC, OGG/Opus, FLAC, ... decoded with PyAV: real samples and duration.
        detected_format = decoded.format
        sample_rate, channels, samples = decoded.sample_rate, decoded.channels, decoded.samples
        bit_depth = 16
    elif audio_bytes.startswith((b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")) or id3_tags:
        # MP3 without a decoder (PyAV not installed): tags only; the duration comes from
        # the transcript when there is one.
        detected_format = "mp3"
        sample_rate = 16000
        channels = 2
        bit_depth = 16
        samples = []
    else:
        # Attempt fallback to WAV parser
        try:
            sample_rate, channels, bit_depth, samples = _decode_wav_stream(audio_bytes)
            detected_format = "wav"
        except Exception as exc:
            raise ValueError(
                f"Unsupported audio format (header: {audio_bytes[:8]!r}). "
                "Supported formats: WAV (.wav), AIFF (.aiff), and, with PyAV installed "
                "(extra [video]), MP3, M4A/AAC, OGG/Opus and FLAC."
            ) from exc

    total_samples = len(samples)
    duration_seconds = total_samples / sample_rate if sample_rate > 0 else 0.0

    # --- ML-Powered Transcription (Pluggable) ---
    # Priority: 1) Explicit pre-computed transcript  2) Pluggable provider  3) Auto-detect
    auto_transcript = ""
    auto_segments: list[dict] = []
    if not transcript:
        provider = transcriber
        if provider is None and auto_extract:
            from .ml_providers import auto_detect_transcriber
            provider = auto_detect_transcriber()
        if provider is not None:
            import contextlib

            with contextlib.suppress(Exception):
                auto_transcript, auto_segments = provider.transcribe(audio_bytes)
        if auto_transcript:
            transcript = auto_transcript

    # Grounded narrative prefix shared by every chunk
    tag_items: list[str] = []
    if filename:
        tag_items.append(f"Audio: {filename}")
    if speaker:
        tag_items.append(f"Speaker/Persona: {speaker}")
    if voice_info.get("parameters"):
        tag_items.append(f"Settings: {voice_info['parameters']}")
    if id3_tags.get("title"):
        tag_items.append(f"Title: {id3_tags['title']}")
    if id3_tags.get("artist"):
        tag_items.append(f"Artist: {id3_tags['artist']}")

    def _prefix(t_label: str) -> str:
        return f"[{' | '.join(tag_items)} | {t_label}]" if tag_items else f"{t_label} Audio Segment"

    # With a transcript, chunks are built from it (every word kept, acoustic numbers left
    # out of the text); without one, the audio is framed into fixed acoustic windows.
    if auto_segments:
        groups = group_transcript(auto_segments)
        duration_seconds = max(duration_seconds, max((g.end for g in groups), default=0.0))
    elif transcript:
        groups = split_transcript(transcript, duration_seconds)
    else:
        groups = []

    segments: list[AudioSegment] = []
    for seg_idx, group in enumerate(groups):
        lo = min(total_samples, int(group.start * sample_rate))
        hi = min(total_samples, max(lo, math.ceil(group.end * sample_rate)))
        seg_samples = samples[lo:hi]
        rms, zcr = rms_zcr(seg_samples)
        centroid, sub_bands = compute_spectral_features(seg_samples, sample_rate)
        t_label = f"[{format_audio_timestamp(group.start)} - {format_audio_timestamp(group.end)}]"
        segments.append(
            AudioSegment(
                segment_index=seg_idx,
                start_seconds=round(group.start, 2),
                end_seconds=round(group.end, 2),
                timestamp_label=t_label,
                rms_energy=round(rms, 4),
                zero_crossing_rate=round(zcr, 4),
                spectral_centroid_hz=centroid,
                activity_level="Speech",
                sub_band_energies=sub_bands,
                narrative_text=f'{_prefix(t_label)} Transcript: "{group.text}"',
                transcript=group.text,
                speaker=speaker,
            )
        )
    if not groups and total_samples == 0:
        # Undecodable container without a transcript: one tag-only chunk.
        t_label = f"[{format_audio_timestamp(0)} - {format_audio_timestamp(0)}]"
        segments.append(
            AudioSegment(
                segment_index=0, start_seconds=0.0, end_seconds=0.0, timestamp_label=t_label,
                rms_energy=0.0, zero_crossing_rate=0.0, spectral_centroid_hz=0.0,
                activity_level="Silent", sub_band_energies=[0.0] * 7,
                narrative_text=_prefix(t_label), transcript=None, speaker=speaker,
            )
        )

    # Frame into temporal segment windows (no transcript)
    win_sec = max(0.1, window_seconds)
    samples_per_win = round(win_sec * sample_rate)

    seg_idx = 0
    pos = 0 if not groups else total_samples

    while pos < total_samples:
        seg_samples = samples[pos : pos + samples_per_win]
        if not len(seg_samples):
            break

        start_s = pos / sample_rate
        end_s = min(duration_seconds, (pos + len(seg_samples)) / sample_rate)
        t_label = f"[{format_audio_timestamp(start_s)} - {format_audio_timestamp(end_s)}]"

        rms, zcr = rms_zcr(seg_samples)

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

        prefix = _prefix(t_label)
        narrative = (
            f"{prefix} | RMS: {rms:.3f} ({activity}) | "
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
                transcript=None,
                speaker=speaker,
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
        if len(bin_slice):
            rms_val, zcr_val = rms_zcr(bin_slice)
            rms_envelope[b] = round(rms_val, 4)
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
        speaker=speaker,
        transcript=transcript,
        voice_metadata=voice_info,
    )

    return AudioPayload(
        metadata=meta,
        segments=segments,
        rms_envelope=rms_envelope,
        zcr_profile=zcr_profile,
        spectral_distribution=spectral_distribution,
        spectral_flux=spectral_flux,
        acoustic_signature=acoustic_sig,
        transcript=transcript,
        speaker=speaker,
    )
