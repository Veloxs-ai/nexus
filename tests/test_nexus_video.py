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

import math
import struct

from nexus.client import NexusClient


def make_box(box_type: bytes, payload: bytes) -> bytes:
    size = 8 + len(payload)
    return struct.pack(">I", size) + box_type + payload


def make_test_mp4(
    duration_s: float = 30.0,
    timescale: int = 1000,
    width: int = 1920,
    height: int = 1080,
) -> bytes:
    ftyp = make_box(b"ftyp", b"mp42\x00\x00\x00\x00isommp42")

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


def test_nexus_client_process_video():
    client = NexusClient(in_memory_only=True)
    mp4_bytes = make_test_mp4(duration_s=30.0)

    transcripts = [
        {"start": 0.0, "end": 10.0, "text": "Nexus pure Python video demuxing overview."},
        {"start": 10.0, "end": 20.0, "text": "Spatio-temporal vector projection and benchmarks."},
    ]

    doc = client.process_video(
        video_id="vid_test_01",
        name="nexus_keynote.mp4",
        video_bytes=mp4_bytes,
        scene_interval_seconds=10.0,
        transcript_segments=transcripts,
        metadata={"category": "product_launch"},
    )

    assert doc.document_id == "vid_test_01"
    assert doc.file_type == "mp4"
    assert len(doc.chunks) == 3

    # Check first scene chunk
    scene_0 = doc.chunks[0]
    assert scene_0.chunk_id == "vid_test_01:0"
    assert scene_0.metadata["timestamp"] == "[00:00 - 00:10]"
    assert scene_0.metadata["is_video"] is True
    assert len(scene_0.embedding) == 3072

    # Verify IEEE 754 L2 unit normalization
    norm = math.sqrt(sum(x * x for x in scene_0.embedding))
    assert abs(norm - 1.0) < 1e-7

    # Verify 5-stage execution trace
    assert len(doc.execution_trace) == 5
    for idx, trace in enumerate(doc.execution_trace, start=1):
        assert trace.step_number == idx
        assert trace.status == "completed"
        assert trace.duration_ms >= 0.0

    assert doc.execution_trace[0].stage_name == "Container Header & ISO Demuxing"
    assert doc.execution_trace[1].stage_name == "Temporal Scene Segmentation & Keyframing"
    assert doc.execution_trace[2].stage_name == "Multi-Frame Spatial Feature Extraction"
    assert doc.execution_trace[3].stage_name == "Motion Dynamics & Temporal Delta Analysis"
    assert doc.execution_trace[4].stage_name == "3072D Spatio-Temporal Vector Projection"

    # Verify indexing and retrieval
    client.index_document(doc, collection="multimodal_videos")
    results = client.search("Spatio-temporal benchmarks", limit=5)
    assert len(results) >= 1
    assert any("vid_test_01" in r.id for r in results)


def test_nexus_client_embed_video_scene():
    client = NexusClient(in_memory_only=True)
    grid = [0.5] * 64
    vec = client.embed_video_scene(
        spatial_grid=grid,
        motion_score=0.2,
        start_seconds=5.0,
        end_seconds=15.0,
        keyframe_dhash="abcd1234ef567890",
        transcript_text="scene audio text",
    )
    assert len(vec) == 3072
    norm = math.sqrt(sum(x * x for x in vec))
    assert abs(norm - 1.0) < 1e-7


def test_nexus_client_process_document_video_routing():
    client = NexusClient(in_memory_only=True)
    mp4_bytes = make_test_mp4(duration_s=20.0)

    doc = client.process_document(
        document_id="vid_routed_01",
        name="demo.mp4",
        text=mp4_bytes,
        file_type="mp4",
    )
    assert doc.document_id == "vid_routed_01"
    assert doc.file_type == "mp4"
    assert len(doc.chunks) == 2  # 20s / 10s = 2 scenes
    assert len(doc.chunks[0].embedding) == 3072
    assert len(doc.execution_trace) == 5
