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

from collections import Counter, defaultdict
from pathlib import Path

from nexus_retrieval.embeddings import tokenize
from nexus_retrieval.io import read_json, write_json
from nexus_retrieval.models import IndexedDocument, SearchResult


class LexicalIndex:
    def __init__(self, uri: str, base_dir: Path) -> None:
        self.uri = uri
        self.base_dir = base_dir
        self.documents: dict[str, IndexedDocument] = {}
        self.postings: dict[str, dict[str, int]] = defaultdict(dict)

    def add(self, document: IndexedDocument) -> None:
        self.documents[document.id] = document
        for token, count in Counter(tokenize(document.text)).items():
            self.postings[token][document.id] = count

    def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        scores: Counter[str] = Counter()
        for token in tokenize(query):
            for doc_id, count in self.postings.get(token, {}).items():
                scores[doc_id] += count

        max_score = max(scores.values(), default=1)
        results = [
            SearchResult(
                id=doc_id,
                collection=self.documents[doc_id].collection,
                text=self.documents[doc_id].text,
                score=score / max_score,
                lexical_score=score / max_score,
                metadata=self.documents[doc_id].metadata,
            )
            for doc_id, score in scores.items()
        ]
        return sorted(results, key=lambda result: result.score, reverse=True)[:limit]

    def save(self) -> None:
        write_json(
            self.uri,
            self.base_dir,
            {
                "documents": {
                    doc_id: document.model_dump(mode="json")
                    for doc_id, document in self.documents.items()
                },
                "postings": {token: dict(posting) for token, posting in self.postings.items()},
            },
        )

    def load(self) -> None:
        payload = read_json(self.uri, self.base_dir)
        self.documents = {
            doc_id: IndexedDocument.model_validate(document)
            for doc_id, document in payload.get("documents", {}).items()
        }
        self.postings = defaultdict(dict, payload.get("postings", {}))

