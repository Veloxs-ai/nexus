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

from pathlib import Path

from .config import RetrievalConfig
from .embeddings import HashingEmbedder, tokenize
from .graph import KnowledgeGraph
from .lexical import LexicalIndex
from .models import SearchResult
from .ranking import combine_scores
from .vector_store import LocalVectorStore


def search(
    config: RetrievalConfig, query: str, base_dir: Path, limit: int = 10
) -> list[SearchResult]:
    embedder = HashingEmbedder(config.embedding.dimensions, config.embedding.normalize)
    # Counterpart to build_indexes(): read the indexes back off disk, so opt
    # out of the in-memory default that makes load() a no-op.
    vector_store = LocalVectorStore(config.stores.vector_index_uri, base_dir, in_memory_only=False)
    lexical_index = LexicalIndex(config.stores.lexical_index_uri, base_dir, in_memory_only=False)
    graph = KnowledgeGraph(config.stores.graph_index_uri, base_dir, in_memory_only=False)
    vector_store.load()
    lexical_index.load()
    graph.load()

    semantic = vector_store.search(embedder.embed(query), limit=limit * 3)
    lexical = lexical_index.search(query, limit=limit * 3)
    candidate_ids = {result.id for result in semantic + lexical}
    query_terms = tokenize(query)
    graph_scores = {doc_id: graph.score(doc_id, query_terms) for doc_id in candidate_ids}
    return combine_scores(semantic, lexical, graph_scores, config.ranking, limit=limit)
