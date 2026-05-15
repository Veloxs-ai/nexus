from __future__ import annotations

from pathlib import Path

from nexus_retrieval.config import RetrievalConfig
from nexus_retrieval.embeddings import HashingEmbedder, tokenize
from nexus_retrieval.graph import KnowledgeGraph
from nexus_retrieval.lexical import LexicalIndex
from nexus_retrieval.models import SearchResult
from nexus_retrieval.ranking import combine_scores
from nexus_retrieval.vector_store import LocalVectorStore


def search(config: RetrievalConfig, query: str, base_dir: Path, limit: int = 10) -> list[SearchResult]:
    embedder = HashingEmbedder(config.embedding.dimensions, config.embedding.normalize)
    vector_store = LocalVectorStore(config.stores.vector_index_uri, base_dir)
    lexical_index = LexicalIndex(config.stores.lexical_index_uri, base_dir)
    graph = KnowledgeGraph(config.stores.graph_index_uri, base_dir)
    vector_store.load()
    lexical_index.load()
    graph.load()

    semantic = vector_store.search(embedder.embed(query), limit=limit * 3)
    lexical = lexical_index.search(query, limit=limit * 3)
    candidate_ids = {result.id for result in semantic + lexical}
    query_terms = tokenize(query)
    graph_scores = {doc_id: graph.score(doc_id, query_terms) for doc_id in candidate_ids}
    return combine_scores(semantic, lexical, graph_scores, config.ranking, limit=limit)

