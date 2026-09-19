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

from nexus_retrieval.embeddings import VideoEmbedder, cosine_similarity


def test_video_embedder_dimensions_and_norm():
    embedder = VideoEmbedder(dimensions=3072, normalize=True)
    spatial_grid = [0.2 + (i % 8) * 0.08 for i in range(64)]

    vec = embedder.embed_scene(
        spatial_grid=spatial_grid,
        motion_score=0.35,
        start_seconds=15.0,
        end_seconds=30.0,
        keyframe_dhash="abcd1234ef567890",
        transcript_text="quarterly financial metrics and projection",
    )

    assert len(vec) == 3072
    norm = math.sqrt(sum(x * x for x in vec))
    assert abs(norm - 1.0) < 1e-7


def test_video_embedder_similarity():
    embedder = VideoEmbedder(dimensions=3072, normalize=True)
    grid_a = [0.1] * 64
    grid_b = [0.9] * 64

    vec1 = embedder.embed_scene(
        spatial_grid=grid_a,
        motion_score=0.1,
        start_seconds=0.0,
        end_seconds=10.0,
        keyframe_dhash="1111222233334444",
        transcript_text="opening remarks",
    )

    vec1_clone = embedder.embed_scene(
        spatial_grid=grid_a,
        motion_score=0.1,
        start_seconds=0.0,
        end_seconds=10.0,
        keyframe_dhash="1111222233334444",
        transcript_text="opening remarks",
    )

    vec2 = embedder.embed_scene(
        spatial_grid=grid_b,
        motion_score=0.8,
        start_seconds=120.0,
        end_seconds=130.0,
        keyframe_dhash="ffff999988887777",
        transcript_text="closing remarks and conclusion",
    )

    assert abs(cosine_similarity(vec1, vec1_clone) - 1.0) < 1e-6
    assert cosine_similarity(vec1, vec2) < 0.90
