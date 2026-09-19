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

import hashlib
import math
import re

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_\-]+")


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


class HashingEmbedder:
    """High-dimensional multi-gram vector projection embedder.

    Projects unigrams, bigrams (for phrase preservation), and trigrams (for entity matching)
    into a high-dimensional vector space (default: 3072 dimensions) with L2 unit normalization.
    """

    def __init__(self, dimensions: int = 3072, normalize: bool = True) -> None:
        self.dimensions = dimensions
        self.normalize = normalize

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        words = [w for w in tokenize(text) if len(w) >= 2]
        if not words:
            words = tokenize(text) or ["empty"]

        # 1. Unigram projection (Base vocabulary tokens)
        for w in words:
            h1 = int(hashlib.md5(w.encode("utf-8")).hexdigest(), 16) % self.dimensions
            h2 = int(hashlib.sha1(w.encode("utf-8")).hexdigest(), 16) % self.dimensions
            sign1 = 1.0 if (h1 % 2 == 0) else -1.0
            sign2 = 1.0 if (h2 % 2 == 0) else -1.0
            vector[h1] += 1.5 * sign1
            vector[h2] += 1.0 * sign2

        # 2. Bigram projection (Preserves multi-word phrases)
        for i in range(len(words) - 1):
            bigram = f"{words[i]}_{words[i + 1]}"
            hb = int(hashlib.sha256(bigram.encode("utf-8")).hexdigest(), 16) % self.dimensions
            sign_b = 1.0 if (hb % 2 == 0) else -1.0
            vector[hb] += 2.0 * sign_b

        # 3. Trigram projection (Preserves entities and named compounds)
        for i in range(len(words) - 2):
            trigram = f"{words[i]}_{words[i + 1]}_{words[i + 2]}"
            ht = int(hashlib.md5(trigram.encode("utf-8")).hexdigest(), 16) % self.dimensions
            sign_t = 1.0 if (ht % 2 == 0) else -1.0
            vector[ht] += 2.5 * sign_t

        return normalize_vector(vector) if self.normalize else vector


class ImageEmbedder:
    """High-dimensional visual feature projection embedder.

    Projects spatial luminance grids, gradient transitions, 3D color histograms,
    and perceptual edge signatures into a 3072-dimensional vector space with
    exact IEEE 754 L2 unit normalization.
    """

    def __init__(self, dimensions: int = 3072, normalize: bool = True) -> None:
        self.dimensions = dimensions
        self.normalize = normalize

    def embed_features(
        self,
        spatial_grid: list[float],
        color_histogram: list[float] | None = None,
        luminance_histogram: list[float] | None = None,
        horizontal_gradients: list[float] | None = None,
        vertical_gradients: list[float] | None = None,
        edge_signature: str | None = None,
        aspect_ratio: float = 1.0,
    ) -> list[float]:
        vector = [0.0] * self.dimensions

        # 1. Spatial Grid Projection (8x8 = 64 spatial cells)
        grid_dim = math.isqrt(len(spatial_grid)) or 8
        for idx, val in enumerate(spatial_grid):
            r = idx // grid_dim
            c = idx % grid_dim
            quantized_val = min(19, int(val * 20))
            token = f"pos_{r}_{c}_val_{quantized_val}"
            h1 = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % self.dimensions
            h2 = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16) % self.dimensions
            sign1 = 1.0 if (h1 % 2 == 0) else -1.0
            sign2 = 1.0 if (h2 % 2 == 0) else -1.0
            weight = 1.0 + val * 2.0
            vector[h1] += weight * sign1
            vector[h2] += (weight * 0.75) * sign2

        # 2. Spatial Gradient Transitions (Horizontal & Vertical Edges)
        if horizontal_gradients:
            for idx, g in enumerate(horizontal_gradients):
                g_bin = max(-5, min(5, int(g * 10)))
                token = f"grad_h_{idx}_{g_bin}"
                h = int(hashlib.sha1(token.encode("utf-8")).hexdigest(), 16) % self.dimensions
                sign = 1.0 if (h % 2 == 0) else -1.0
                vector[h] += 1.8 * abs(g) * sign

        if vertical_gradients:
            for idx, g in enumerate(vertical_gradients):
                g_bin = max(-5, min(5, int(g * 10)))
                token = f"grad_v_{idx}_{g_bin}"
                h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % self.dimensions
                sign = 1.0 if (h % 2 == 0) else -1.0
                vector[h] += 1.8 * abs(g) * sign

        # 3. 3D Color Histogram Projection (64 RGB-cube bins)
        if color_histogram:
            for bin_idx, freq in enumerate(color_histogram):
                if freq > 0.001:
                    token = f"color_bin_{bin_idx}"
                    h = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16) % self.dimensions
                    sign = 1.0 if (h % 2 == 0) else -1.0
                    vector[h] += (freq * 5.0) * sign

        # 4. Luminance Intensity Distribution (32 bins)
        if luminance_histogram:
            for bin_idx, freq in enumerate(luminance_histogram):
                if freq > 0.001:
                    token = f"lum_bin_{bin_idx}"
                    h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % self.dimensions
                    sign = 1.0 if (h % 2 == 0) else -1.0
                    vector[h] += (freq * 4.0) * sign

        # 5. Perceptual dHash Signature & Aspect Ratio
        if edge_signature:
            # Hash 4-character sub-windows of the 16-hex dHash
            for i in range(0, len(edge_signature) - 3, 2):
                chunk = edge_signature[i : i + 4]
                h = int(hashlib.sha1(f"dhash_{chunk}".encode()).hexdigest(), 16) % self.dimensions
                sign = 1.0 if (h % 2 == 0) else -1.0
                vector[h] += 2.2 * sign

        ar_token = f"ar_{int(aspect_ratio * 10)}"
        h_ar = int(hashlib.md5(ar_token.encode("utf-8")).hexdigest(), 16) % self.dimensions
        vector[h_ar] += 1.2

        return normalize_vector(vector) if self.normalize else vector


def normalize_vector(vector: list[float]) -> list[float]:
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        return vector
    return [value / magnitude for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)
