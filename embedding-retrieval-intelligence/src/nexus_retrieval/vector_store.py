from __future__ import annotations

from pathlib import Path

from nexus_retrieval.embeddings import cosine_similarity
from nexus_retrieval.io import read_json, write_json
from nexus_retrieval.models import SearchResult, VectorEntry


class LocalVectorStore:
    def __init__(self, uri: str, base_dir: Path) -> None:
        self.uri = uri
        self.base_dir = base_dir
        self.entries: list[VectorEntry] = []

    def add(self, entry: VectorEntry) -> None:
        self.entries.append(entry)

    def search(self, embedding: list[float], limit: int = 10) -> list[SearchResult]:
        results = [
            SearchResult(
                id=entry.id,
                collection=entry.collection,
                text=entry.text,
                score=cosine_similarity(embedding, entry.embedding),
                semantic_score=cosine_similarity(embedding, entry.embedding),
                metadata=entry.metadata,
            )
            for entry in self.entries
        ]
        return sorted(results, key=lambda result: result.score, reverse=True)[:limit]

    def save(self) -> None:
        write_json(
            self.uri,
            self.base_dir,
            {"entries": [entry.model_dump(mode="json") for entry in self.entries]},
        )

    def load(self) -> None:
        payload = read_json(self.uri, self.base_dir)
        self.entries = [VectorEntry.model_validate(entry) for entry in payload.get("entries", [])]

