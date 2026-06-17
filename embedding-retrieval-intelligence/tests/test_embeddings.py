# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

from nexus_retrieval.embeddings import HashingEmbedder, cosine_similarity, tokenize


def test_hashing_embedder_is_deterministic_and_normalized():
    embedder = HashingEmbedder(dimensions=16, normalize=True)

    first = embedder.embed("MFA access policy")
    second = embedder.embed("MFA access policy")

    assert first == second
    assert round(cosine_similarity(first, first), 6) == 1.0


def test_tokenize_lowercases_words():
    assert tokenize("MFA, Access!") == ["mfa", "access"]

