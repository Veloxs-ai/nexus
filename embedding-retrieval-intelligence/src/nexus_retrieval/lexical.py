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

import threading
from collections import Counter, defaultdict
from pathlib import Path

from .embeddings import tokenize
from .io import read_json, write_json
from .models import IndexedDocument, SearchResult


class LexicalIndex:
    def __init__(
        self,
        uri: str = "data/indexes/lexical_index.json",
        base_dir: Path | None = None,
        in_memory_only: bool = True,
    ) -> None:
        self.uri = uri
        self.base_dir = base_dir or Path.cwd()
        self.in_memory_only = in_memory_only
        self.documents: dict[str, IndexedDocument] = {}
        self.postings: dict[str, dict[str, int]] = defaultdict(dict)
        self._lock = threading.Lock()

    def add(self, document: IndexedDocument) -> None:
        tokens_count = Counter(tokenize(document.text)).items()
        with self._lock:
            self.documents[document.id] = document
            for token, count in tokens_count:
                self.postings[token][document.id] = count

    def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        tokens = tokenize(query)
        scores: Counter[str] = Counter()
        with self._lock:
            for token in tokens:
                for doc_id, count in self.postings.get(token, {}).items():
                    scores[doc_id] += count
            docs_snapshot = dict(self.documents)

        max_score = max(scores.values(), default=1)
        results = [
            SearchResult(
                id=doc_id,
                collection=docs_snapshot[doc_id].collection,
                text=docs_snapshot[doc_id].text,
                score=score / max_score,
                lexical_score=score / max_score,
                metadata=docs_snapshot[doc_id].metadata,
            )
            for doc_id, score in scores.items()
            if doc_id in docs_snapshot
        ]
        return sorted(results, key=lambda result: result.score, reverse=True)[:limit]

    def save(self) -> None:
        if self.in_memory_only:
            return  # Pure in-memory bypass for serverless environments
        with self._lock:
            payload = {
                "documents": {
                    doc_id: document.model_dump(mode="json")
                    for doc_id, document in self.documents.items()
                },
                "postings": {token: dict(posting) for token, posting in self.postings.items()},
            }
        write_json(self.uri, self.base_dir, payload)

    def load(self) -> None:
        if self.in_memory_only:
            return
        try:
            payload = read_json(self.uri, self.base_dir)
            with self._lock:
                self.documents = {
                    doc_id: IndexedDocument.model_validate(document)
                    for doc_id, document in payload.get("documents", {}).items()
                }
                self.postings = defaultdict(dict, payload.get("postings", {}))
        except Exception:
            pass
