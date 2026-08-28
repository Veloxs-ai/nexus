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
import threading
from pathlib import Path

from .embeddings import cosine_similarity, normalize_vector
from .io import read_json, write_json
from .models import SearchResult, VectorEntry


class LocalVectorStore:
    def __init__(
        self,
        uri: str = "data/indexes/vector_index.json",
        base_dir: Path | None = None,
        in_memory_only: bool = True,
    ) -> None:
        self.uri = uri
        self.base_dir = base_dir or Path.cwd()
        self.in_memory_only = in_memory_only
        self.entries: list[VectorEntry] = []
        self._lock = threading.Lock()

    def add(self, entry: VectorEntry) -> None:
        # Defensive vector normalization check on insertion
        norm = math.sqrt(sum(x * x for x in entry.embedding))
        if norm > 0 and abs(norm - 1.0) > 1e-7:
            entry.embedding = normalize_vector(entry.embedding)

        with self._lock:
            self.entries.append(entry)

    def search(self, embedding: list[float], limit: int = 10) -> list[SearchResult]:
        if not embedding:
            return []

        # Defensive vector normalization check on incoming query
        norm = math.sqrt(sum(x * x for x in embedding))
        query_vec = (
            normalize_vector(embedding) if (norm > 0 and abs(norm - 1.0) > 1e-7) else embedding
        )

        with self._lock:
            entries_snapshot = list(self.entries)

        results = [
            SearchResult(
                id=entry.id,
                collection=entry.collection,
                text=entry.text,
                score=cosine_similarity(query_vec, entry.embedding),
                semantic_score=cosine_similarity(query_vec, entry.embedding),
                metadata=entry.metadata,
            )
            for entry in entries_snapshot
        ]
        return sorted(results, key=lambda result: result.score, reverse=True)[:limit]

    def save(self) -> None:
        if self.in_memory_only:
            return  # Pure in-memory bypass for serverless / read-only environments
        with self._lock:
            payload = {"entries": [entry.model_dump(mode="json") for entry in self.entries]}
        write_json(self.uri, self.base_dir, payload)

    def load(self) -> None:
        if self.in_memory_only:
            return
        try:
            payload = read_json(self.uri, self.base_dir)
            with self._lock:
                self.entries = [
                    VectorEntry.model_validate(entry) for entry in payload.get("entries", [])
                ]
        except Exception:
            pass
