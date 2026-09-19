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

import struct

from nexus_processing.video import (
    demux_mp4,
    format_timestamp,
    process_video_binary,
    segment_temporal_scenes,
)


def make_box(box_type: bytes, payload: bytes) -> bytes:
    size = 8 + len(payload)
    return struct.pack(">I", size) + box_type + payload


def make_test_mp4(
    duration_s: float = 30.0,
    timescale: int = 1000,
    width: int = 1920,
    height: int = 1080,
) -> bytes:
    ftyp_payload = b"mp42\x00\x00\x00\x00isommp42"
    ftyp = make_box(b"ftyp", ftyp_payload)

    duration_units = int(duration_s * timescale)
    mvhd_payload = struct.pack(">BBBBIIII", 0, 0, 0, 0, 0, 0, timescale, duration_units)
    mvhd_payload += b"\x00\x01\x00\x00\x01\x00" + b"\x00" * 70 + struct.pack(">I", 2)
    mvhd = make_box(b"mvhd", mvhd_payload)

    tkhd_payload = struct.pack(">BBBBIIIII", 0, 0, 0, 1, 0, 0, 1, 0, duration_units)
    tkhd_payload += b"\x00" * 52 + struct.pack(">II", width << 16, height << 16)
    tkhd = make_box(b"tkhd", tkhd_payload)

    stsz_payload = struct.pack(">BBBBII", 0, 0, 0, 0, 0, 900) + b"\x00\x00\x04\x00" * 900
    stsz = make_box(b"stsz", stsz_payload)

    stss_entries = [1 + i * 60 for i in range(15)]
    stss_payload = struct.pack(">BBBBI", 0, 0, 0, 0, len(stss_entries))
    for k in stss_entries:
        stss_payload += struct.pack(">I", k)
    stss = make_box(b"stss", stss_payload)

    stbl = make_box(b"stbl", stsz + stss)
    minf = make_box(b"minf", stbl)
    mdia = make_box(b"mdia", minf)
    trak = make_box(b"trak", tkhd + mdia)

    moov = make_box(b"moov", mvhd + trak)
    mdat = make_box(b"mdat", bytes([i % 256 for i in range(4096)]))

    return ftyp + moov + mdat


def test_format_timestamp():
    assert format_timestamp(0) == "00:00"
    assert format_timestamp(65) == "01:05"
    assert format_timestamp(3661) == "61:01"


def test_demux_mp4():
    mp4_data = make_test_mp4(duration_s=25.0, width=1280, height=720)
    meta = demux_mp4(mp4_data)

    assert meta.format == "MP4"
    assert meta.duration_seconds == 25.0
    assert meta.width == 1280
    assert meta.height == 720
    assert meta.aspect_ratio == 1.778
    assert meta.total_frames == 900
    assert meta.keyframe_count == 15


def test_segment_temporal_scenes():
    mp4_data = make_test_mp4(duration_s=30.0)
    meta = demux_mp4(mp4_data)

    transcripts = [
        {"start": 0.0, "end": 8.0, "text": "Welcome to Nexus enterprise intelligence."},
        {"start": 12.0, "end": 22.0, "text": "Here we demonstrate spatio-temporal video search."},
    ]

    scenes = segment_temporal_scenes(
        meta=meta,
        data=mp4_data,
        scene_interval_seconds=10.0,
        transcript_segments=transcripts,
    )

    # 30 seconds / 10s interval = 3 scenes
    assert len(scenes) == 3
    assert scenes[0].timestamp_label == "[00:00 - 00:10]"
    assert scenes[1].timestamp_label == "[00:10 - 00:20]"
    assert scenes[2].timestamp_label == "[00:20 - 00:30]"

    assert "Welcome to Nexus" in scenes[0].transcript_segment
    assert "spatio-temporal" in scenes[1].transcript_segment
    assert len(scenes[0].spatial_grid) == 64
    assert len(scenes[0].keyframe_dhash) == 16


def test_process_video_binary_end_to_end():
    mp4_data = make_test_mp4(duration_s=15.0)
    payload = process_video_binary(mp4_data, scene_interval_seconds=5.0)

    assert payload.metadata.duration_seconds == 15.0
    # 15s / 5s = 3 scenes
    assert len(payload.scenes) == 3
    assert payload.scenes[0].duration_seconds == 5.0
