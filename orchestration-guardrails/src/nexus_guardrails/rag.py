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

import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .config import GuardrailsConfig
from .io import read_json
from .models import Citation
from .offtopic import tokenize


def retrieve_context(
    config: GuardrailsConfig,
    query: str,
    base_dir: Path | None = None,
    retrieval_engine: Any | None = None,
    search_provider: Callable[[str, int], list[Citation]] | None = None,
) -> list[Citation]:
    """Retrieves relevant contextual citations from in-memory engine, provider, or index files."""
    # 1. In-Memory Search Provider or Retrieval Engine (Zero-Latency Library Mode)
    if search_provider:
        return search_provider(query, config.rag.top_k)

    if retrieval_engine and hasattr(retrieval_engine, "search"):
        results = retrieval_engine.search(query, limit=config.rag.top_k)
        citations: list[Citation] = []
        for res in results:
            if res.score >= config.rag.min_context_score:
                citations.append(
                    Citation(
                        source_id=res.id,
                        collection=res.collection,
                        text=res.text,
                        score=res.score,
                    )
                )
        return citations

    # 2. File-Based Fallback (Graceful Degradation)
    base = base_dir or Path.cwd()
    try:
        vector_payload = read_json(config.integration.vector_index_uri, base)
        lexical_payload = read_json(config.integration.lexical_index_uri, base)
    except Exception:
        return []

    documents = lexical_payload.get("documents", {})
    query_terms = tokenize(query)
    citations = []

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
