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
