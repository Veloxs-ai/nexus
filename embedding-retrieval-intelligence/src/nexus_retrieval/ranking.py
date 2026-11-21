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

from collections.abc import Callable, Sequence
from typing import Any, TypeVar

from .config import RankingConfig
from .models import SearchResult

T = TypeVar("T")
RRF_K = 60


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[T]],
    key: Callable[[T], Any] = lambda item: item,
    k: int = RRF_K,
) -> list[T]:
    """Reciprocal Rank Fusion: items ordered by ``sum(1 / (k + rank))`` over the lists.

    Rank-based, so lists with incomparable score scales (cosine similarity, BM25,
    full-text rank) fuse fairly. ``key`` identifies the same item across lists; the first
    occurrence of an item is the one returned. Ties keep first-seen order.
    """
    scores: dict[Any, float] = {}
    items: dict[Any, T] = {}
    for ranked in ranked_lists:
        for rank, item in enumerate(ranked):
            ident = key(item)
            scores[ident] = scores.get(ident, 0.0) + 1.0 / (k + rank + 1)
            items.setdefault(ident, item)
    return [items[ident] for ident in sorted(scores, key=scores.__getitem__, reverse=True)]


def rerank_multi(
    queries: Sequence[str],
    passages: Sequence[str],
    score: Callable[[str, list[str]], list[float]],
    found_by: Sequence[set[int] | frozenset[int]] | None = None,
) -> list[float]:
    """Cross-encoder scores of ``passages`` for a question with sub-queries.

    Every passage is scored against ``queries[0]``; a passage that sub-query ``n`` found
    (``n in found_by[i]``) is also scored against ``queries[n]``, and keeps the best
    score. "Compare A and B" thereby keeps the B-side passages its sub-query found, at
    the cost of scoring only those extra pairs. ``score(query, passages)`` is the
    re-ranker (``NexusClient.rerank``).
    """
    if not passages or not queries:
        return []
    best = [float(s) for s in score(queries[0], list(passages))]
    for n in range(1, len(queries)):
        mine = [i for i in range(len(passages)) if found_by and n in found_by[i]]
        if mine:
            for i, s in zip(mine, score(queries[n], [passages[i] for i in mine]), strict=True):
                best[i] = max(best[i], float(s))
    return best


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

    if getattr(ranking, "fusion", "weighted") == "rrf":
        return _rrf_combine(semantic, lexical, graph_scores, merged, limit)

    total_weight = ranking.semantic_weight + ranking.lexical_weight + ranking.graph_weight
    for result in merged.values():
        result.graph_score = graph_scores.get(result.id, 0.0)
        result.score = (
            ranking.semantic_weight * result.semantic_score
            + ranking.lexical_weight * result.lexical_score
            + ranking.graph_weight * result.graph_score
        ) / total_weight

    return sorted(merged.values(), key=lambda result: result.score, reverse=True)[:limit]


def _rrf_combine(
    semantic: list[SearchResult],
    lexical: list[SearchResult],
    graph_scores: dict[str, float],
    merged: dict[str, SearchResult],
    limit: int,
) -> list[SearchResult]:
    graph_ranked = [
        rid for rid, _ in sorted(graph_scores.items(), key=lambda kv: kv[1], reverse=True)
    ]
    lists = [
        [r.id for r in semantic],
        [r.id for r in lexical],
        [g for g in graph_ranked if g in merged],
    ]
    fused = reciprocal_rank_fusion([lst for lst in lists if lst])
    ranked = []
    for position, rid in enumerate(fused):
        result = merged[rid]
        result.graph_score = graph_scores.get(rid, 0.0)
        result.score = sum(1.0 / (RRF_K + lst.index(rid) + 1) for lst in lists if rid in lst)
        ranked.append((position, result))
    return [result for _, result in ranked][:limit]
