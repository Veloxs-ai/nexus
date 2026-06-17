# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

from nexus_retrieval.hybrid import search
from nexus_retrieval.indexing import build_indexes


def test_hybrid_search_returns_contextually_relevant_result(sample_config, tmp_path):
    build_indexes(sample_config, tmp_path)

    results = search(sample_config, "MFA access security", tmp_path, limit=1)

    assert results[0].id == "doc-1:0"
    assert results[0].score > 0
    assert results[0].graph_score > 0

