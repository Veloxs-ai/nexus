# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

from nexus_retrieval.config import RankingConfig
from nexus_retrieval.models import SearchResult
from nexus_retrieval.ranking import combine_scores


def test_combine_scores_merges_semantic_lexical_and_graph_scores():
    results = combine_scores(
        semantic=[
            SearchResult(
                id="a",
                collection="docs",
                text="security",
                score=0.8,
                semantic_score=0.8,
            )
        ],
        lexical=[
            SearchResult(
                id="a",
                collection="docs",
                text="security",
                score=1.0,
                lexical_score=1.0,
            )
        ],
        graph_scores={"a": 0.5},
        ranking=RankingConfig(semantic_weight=0.5, lexical_weight=0.3, graph_weight=0.2),
        limit=1,
    )

    assert results[0].id == "a"
    assert round(results[0].score, 2) == 0.8

