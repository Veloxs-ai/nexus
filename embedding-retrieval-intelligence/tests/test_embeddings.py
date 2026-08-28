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

from nexus_retrieval.embeddings import HashingEmbedder, cosine_similarity, tokenize


def test_hashing_embedder_is_deterministic_and_normalized():
    embedder = HashingEmbedder(dimensions=16, normalize=True)

    first = embedder.embed("MFA access policy")
    second = embedder.embed("MFA access policy")

    assert first == second
    assert round(cosine_similarity(first, first), 6) == 1.0


def test_tokenize_lowercases_words():
    assert tokenize("MFA, Access!") == ["mfa", "access"]
