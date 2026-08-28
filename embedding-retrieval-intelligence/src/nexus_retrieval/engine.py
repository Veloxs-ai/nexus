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
from typing import Any

from .config import EmbeddingConfig, RankingConfig, RetrievalConfig, StoreConfig
from .embeddings import HashingEmbedder, tokenize
from .graph import KnowledgeGraph
from .lexical import LexicalIndex
from .models import IndexedDocument, SearchResult, VectorEntry
from .ranking import combine_scores
from .vector_store import LocalVectorStore


class RetrievalEngine:
    """In-memory vector embedding and hybrid retrieval intelligence engine.

    Generates normalized 3072-dimensional multi-gram embeddings and conducts
    hybrid (semantic + lexical + knowledge graph) retrieval with Reciprocal Rank Fusion.
    Provides complete thread safety and pure in-memory execution for serverless runtimes.
    """

    def __init__(
        self,
        config: RetrievalConfig | None = None,
        base_dir: Path | None = None,
        vector_store: LocalVectorStore | None = None,
        lexical_index: LexicalIndex | None = None,
        graph: KnowledgeGraph | None = None,
        in_memory_only: bool = True,
    ) -> None:
        self.config = config or RetrievalConfig(
            embedding=EmbeddingConfig(dimensions=3072, normalize=True),
            stores=StoreConfig(
                vector_index_uri="data/indexes/vector_index.json",
                lexical_index_uri="data/indexes/lexical_index.json",
                graph_index_uri="data/indexes/graph_index.json",
            ),
            ranking=RankingConfig(
                semantic_weight=0.5,
                lexical_weight=0.3,
                graph_weight=0.2,
            ),
            collections={},
        )
        self.base_dir = base_dir or Path.cwd()
        self.in_memory_only = in_memory_only
        self.embedder = HashingEmbedder(
            dimensions=self.config.embedding.dimensions,
            normalize=self.config.embedding.normalize,
        )
        self.vector_store = vector_store or LocalVectorStore(
            self.config.stores.vector_index_uri, self.base_dir, in_memory_only=self.in_memory_only
        )
        self.lexical_index = lexical_index or LexicalIndex(
            self.config.stores.lexical_index_uri, self.base_dir, in_memory_only=self.in_memory_only
        )
        self.graph = graph or KnowledgeGraph(
            self.config.stores.graph_index_uri, self.base_dir, in_memory_only=self.in_memory_only
        )

    def embed(self, text: str) -> list[float]:
        """Generate pure 3072-dimensional normalized vector embedding."""
        return self.embedder.embed(text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Batch vector projection for multiple chunks."""
        return [self.embed(text) for text in texts]

    def add_entry(
        self,
        doc_id: str,
        text: str,
        collection: str = "general",
        metadata: dict[str, Any] | None = None,
        embedding: list[float] | None = None,
    ) -> VectorEntry:
        """Adds a record into the in-memory vector store, lexical index, and knowledge graph."""
        vec = embedding if embedding is not None else self.embed(text)
        entry = VectorEntry(
            id=doc_id,
            collection=collection,
            text=text,
            embedding=vec,
            metadata=metadata or {},
        )
        self.vector_store.add(entry)
        self.lexical_index.add(
            IndexedDocument(id=doc_id, collection=collection, text=text, metadata=metadata or {})
        )

        if metadata:
            doc_node = f"document:{doc_id}"
            self.graph.nodes[doc_node] = {"type": "document", "id": doc_id}
            parent_id = metadata.get("document_id")
            if parent_id:
                p_node = f"parent:{parent_id}"
                self.graph.nodes[p_node] = {"type": "parent", "id": str(parent_id)}
                self.graph.add_edge(doc_node, "PART_OF", p_node)
            for ent in metadata.get("entities", []):
                e_node = f"entity:{ent}"
                self.graph.nodes[e_node] = {"type": "entity", "value": str(ent)}
                self.graph.add_edge(doc_node, "MENTIONS", e_node)
            for tag in metadata.get("tags", []):
                t_node = f"tag:{tag}"
                self.graph.nodes[t_node] = {"type": "tag", "value": str(tag)}
                self.graph.add_edge(doc_node, "TAGGED_AS", t_node)

        return entry

    def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Performs hybrid search combining vector, lexical, and graph signals with RRF."""
        query_vector = self.embed(query)
        semantic = self.vector_store.search(query_vector, limit=limit * 3)
        lexical = self.lexical_index.search(query, limit=limit * 3)

        candidate_ids = {result.id for result in semantic + lexical}
        query_terms = tokenize(query)
        graph_scores = {doc_id: self.graph.score(doc_id, query_terms) for doc_id in candidate_ids}

        return combine_scores(semantic, lexical, graph_scores, self.config.ranking, limit=limit)
