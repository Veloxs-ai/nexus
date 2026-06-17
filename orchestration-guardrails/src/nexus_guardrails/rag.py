# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

from __future__ import annotations

import math
from pathlib import Path

from nexus_guardrails.config import GuardrailsConfig
from nexus_guardrails.io import read_json
from nexus_guardrails.models import Citation
from nexus_guardrails.offtopic import tokenize


def retrieve_context(config: GuardrailsConfig, query: str, base_dir: Path) -> list[Citation]:
    vector_payload = read_json(config.integration.vector_index_uri, base_dir)
    lexical_payload = read_json(config.integration.lexical_index_uri, base_dir)
    documents = lexical_payload.get("documents", {})
    query_terms = tokenize(query)
    citations: list[Citation] = []

    for entry in vector_payload.get("entries", []):
        doc_id = entry["id"]
        text = entry.get("text", "")
        text_terms = tokenize(text)
        lexical_score = len(query_terms & text_terms) / max(len(query_terms), 1)
        semantic_score = simple_semantic_score(query_terms, text_terms)
        score = 0.65 * semantic_score + 0.35 * lexical_score
        if score >= config.rag.min_context_score:
            doc = documents.get(doc_id, {})
            citations.append(
                Citation(
                    source_id=doc_id,
                    collection=entry.get("collection", doc.get("collection", "unknown")),
                    text=text,
                    score=score,
                )
            )

    return sorted(citations, key=lambda citation: citation.score, reverse=True)[: config.rag.top_k]


def simple_semantic_score(query_terms: set[str], text_terms: set[str]) -> float:
    if not query_terms or not text_terms:
        return 0.0
    return len(query_terms & text_terms) / math.sqrt(len(query_terms) * len(text_terms))


def compose_grounded_answer(query: str, citations: list[Citation]) -> str:
    if not citations:
        return "I do not have enough trusted context to answer this request."
    source_lines = " ".join(citation.text for citation in citations)
    return f"Based on retrieved enterprise context: {source_lines}"

