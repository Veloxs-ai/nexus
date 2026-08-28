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

from .config import RankingConfig
from .models import SearchResult


def combine_scores(
    semantic: list[SearchResult],
    lexical: list[SearchResult],
    graph_scores: dict[str, float],
    ranking: RankingConfig,
    limit: int = 10,
) -> list[SearchResult]:
    merged: dict[str, SearchResult] = {}

    for result in semantic:
        merged[result.id] = result.model_copy(update={"semantic_score": result.semantic_score})

    for result in lexical:
        existing = merged.get(result.id)
        if existing:
            existing.lexical_score = result.lexical_score
        else:
            merged[result.id] = result.model_copy(update={"lexical_score": result.lexical_score})

    total_weight = ranking.semantic_weight + ranking.lexical_weight + ranking.graph_weight
    for result in merged.values():
        result.graph_score = graph_scores.get(result.id, 0.0)
        result.score = (
            ranking.semantic_weight * result.semantic_score
            + ranking.lexical_weight * result.lexical_score
            + ranking.graph_weight * result.graph_score
        ) / total_weight

    return sorted(merged.values(), key=lambda result: result.score, reverse=True)[:limit]
