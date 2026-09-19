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

from nexus_retrieval.embeddings import ImageEmbedder, cosine_similarity


def test_image_embedder_dimensions_and_norm():
    embedder = ImageEmbedder(dimensions=3072, normalize=True)
    spatial_grid = [0.1 * (i % 10) for i in range(64)]
    color_hist = [0.0] * 64
    color_hist[5] = 0.6
    color_hist[20] = 0.4

    vec = embedder.embed_features(
        spatial_grid=spatial_grid,
        color_histogram=color_hist,
        edge_signature="a1b2c3d4e5f60718",
        aspect_ratio=1.333,
    )

    assert len(vec) == 3072
    norm = math.sqrt(sum(x * x for x in vec))
    assert abs(norm - 1.0) < 1e-7


def test_image_embedder_cosine_similarity():
    embedder = ImageEmbedder(dimensions=3072, normalize=True)
    grid_a = [0.2] * 64
    grid_b = [0.8] * 64

    vec_a1 = embedder.embed_features(spatial_grid=grid_a, edge_signature="1234567890abcdef")
    vec_a2 = embedder.embed_features(spatial_grid=grid_a, edge_signature="1234567890abcdef")
    vec_b = embedder.embed_features(spatial_grid=grid_b, edge_signature="fedcba0987654321")

    sim_identical = cosine_similarity(vec_a1, vec_a2)
    assert abs(sim_identical - 1.0) < 1e-6

    sim_diff = cosine_similarity(vec_a1, vec_b)
    assert sim_diff < 0.95
