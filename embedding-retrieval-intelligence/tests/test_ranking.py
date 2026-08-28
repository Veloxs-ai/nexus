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
