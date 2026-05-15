from __future__ import annotations

from nexus_retrieval.config import RankingConfig
from nexus_retrieval.models import SearchResult


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

