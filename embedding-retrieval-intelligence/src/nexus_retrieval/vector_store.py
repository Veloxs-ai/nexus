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

import heapq
import math
import threading
from collections.abc import Iterator
from pathlib import Path

from .io import read_json, write_json
from .models import SearchResult, VectorEntry

# Dot product of two equal-length vectors: math.sumprod (3.12+, extended-precision
# accumulation) or the 3.11 fallback.
_dot = getattr(math, "sumprod", None) or (lambda a, b: sum(map(float.__mul__, a, b)))


def _unit(vector: list[float]) -> list[float]:
    """``vector`` scaled to unit length (zero vectors unchanged)."""
    norm = math.sqrt(_dot(vector, vector)) if vector else 0.0
    if norm > 0 and norm != 1.0:
        return [value / norm for value in vector]
    return vector


class LocalVectorStore:
    """Brute-force cosine search over unit-length vectors held in memory.

    Vectors are normalised once on insert, so a query scores each entry with one dot
    product, the top ``limit`` are picked with a heap (ties keep insertion order) and only
    those become :class:`SearchResult` objects.
    """

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
        self._positions: dict[str, int] = {}
        self._lock = threading.Lock()

    def _position_unlocked(self, entry_id: str) -> int | None:
        pos = self._positions.get(entry_id)
        if pos is not None and pos < len(self.entries) and self.entries[pos].id == entry_id:
            return pos
        # ``entries`` was changed directly: rebuild the id -> position map.
        self._positions = {e.id: i for i, e in enumerate(self.entries)}
        return self._positions.get(entry_id)

    def add(self, entry: VectorEntry) -> None:
        """Add ``entry``; an entry with the same id is replaced (a re-index never leaves
        the old vector behind to be found twice)."""
        entry.embedding = _unit([float(x) for x in entry.embedding])
        with self._lock:
            if len(self._positions) != len(self.entries):
                self._positions = {e.id: i for i, e in enumerate(self.entries)}
            pos = self._positions.get(entry.id)
            if pos is not None:
                pos = self._position_unlocked(entry.id)
            if pos is None:
                self._positions[entry.id] = len(self.entries)
                self.entries.append(entry)
            else:
                self.entries[pos] = entry

    def remove(self, entry_id: str) -> bool:
        """Remove the entry with ``entry_id``. Returns whether it was stored."""
        with self._lock:
            pos = self._position_unlocked(entry_id)
            if pos is None:
                return False
            del self.entries[pos]
            self._positions = {e.id: i for i, e in enumerate(self.entries)}
            return True

    def search(self, embedding: list[float], limit: int = 10) -> list[SearchResult]:
        if not embedding or limit <= 0:
            return []
        query = _unit([float(x) for x in embedding])
        query_ok = any(query)
        with self._lock:
            entries = list(self.entries)
        dims = len(query)

        def scored() -> Iterator[tuple[float, int]]:
            for i, entry in enumerate(entries):
                vec = entry.embedding
                if query_ok and len(vec) == dims:
                    yield _dot(query, vec), -i
                else:
                    yield 0.0, -i

        top = heapq.nlargest(limit, scored())
        return [
            SearchResult(
                id=entries[-i].id,
                collection=entries[-i].collection,
                text=entries[-i].text,
                score=score,
                semantic_score=score,
                metadata=entries[-i].metadata,
            )
            for score, i in top
        ]

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
                latest: dict[str, VectorEntry] = {}
                for raw in payload.get("entries", []):
                    entry = VectorEntry.model_validate(raw)
                    entry.embedding = _unit([float(x) for x in entry.embedding])
                    latest[entry.id] = entry  # an older index may hold an id twice
                self.entries = list(latest.values())
                self._positions = {e.id: i for i, e in enumerate(self.entries)}
        except Exception:
            pass
