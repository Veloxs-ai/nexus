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
from collections import Counter, defaultdict
from pathlib import Path

from .embeddings import tokenize
from .io import read_json, write_json
from .models import IndexedDocument, SearchResult

# Words that carry no meaning on their own: matching only these must not make a document relevant.
_STOPWORD_TEXT = """
a about above after again all also am an and any are as at be because been before being below
between both but by can could did do does doing down during each few for from further had has
have having he her here hers him his how i if in into is it its itself just me more most my no nor
not now of off on once only or other our ours out over own same she should so some such than that
the their theirs them then there these they this those through to too under until up very was we
were what when where which while who whom why will with would you your yours
"""
STOPWORDS = frozenset(_STOPWORD_TEXT.split())


def query_terms(text: str) -> list[str]:
    """Distinct meaningful words of a query, in order (stopwords removed)."""
    return list(dict.fromkeys(t for t in tokenize(text) if t not in STOPWORDS))


class LexicalIndex:
    def __init__(
        self,
        uri: str = "data/indexes/lexical_index.json",
        base_dir: Path | None = None,
        in_memory_only: bool = True,
        scoring: str = "share",
    ) -> None:
        """``scoring``: ``"share"`` (default) scores the IDF-weighted share of the query
        matched (0..1); ``"bm25"`` is Okapi BM25 (``k1=1.2``, ``b=0.75``: term-frequency
        saturation and document-length normalisation), normalised to 0..1 by the best hit."""
        if scoring not in ("share", "bm25"):
            raise ValueError("scoring must be 'share' or 'bm25'")
        self.uri = uri
        self.base_dir = base_dir or Path.cwd()
        self.in_memory_only = in_memory_only
        self.scoring = scoring
        self.documents: dict[str, IndexedDocument] = {}
        self.postings: dict[str, dict[str, int]] = defaultdict(dict)
        self.lengths: dict[str, int] = {}
        self._lock = threading.Lock()

    def add(self, document: IndexedDocument) -> None:
        tokens = tokenize(document.text)
        tokens_count = Counter(tokens).items()
        with self._lock:
            self.documents[document.id] = document
            self.lengths[document.id] = len(tokens)
            for token, count in tokens_count:
                self.postings[token][document.id] = count

    def _bm25(
        self, terms: list[str], limit: int, k1: float = 1.2, b: float = 0.75
    ) -> list[SearchResult]:
        with self._lock:
            total_docs = len(self.documents)
            postings = {term: dict(self.postings.get(term, {})) for term in terms}
            docs_snapshot = dict(self.documents)
            lengths = dict(self.lengths)
        if not total_docs:
            return []
        avg_len = (sum(lengths.values()) / len(lengths)) if lengths else 1.0
        scores: dict[str, float] = defaultdict(float)
        for docs in postings.values():
            idf = math.log(1.0 + (total_docs - len(docs) + 0.5) / (len(docs) + 0.5))
            for doc_id, tf in docs.items():
                norm = k1 * (1 - b + b * lengths.get(doc_id, avg_len) / (avg_len or 1.0))
                scores[doc_id] += idf * tf * (k1 + 1) / (tf + norm)
        top = max(scores.values(), default=0.0) or 1.0
        results = [
            SearchResult(
                id=doc_id,
                collection=docs_snapshot[doc_id].collection,
                text=docs_snapshot[doc_id].text,
                score=round(score / top, 6),
                lexical_score=round(score / top, 6),
                metadata=docs_snapshot[doc_id].metadata,
            )
            for doc_id, score in scores.items()
            if doc_id in docs_snapshot
        ]
        results.sort(key=lambda result: result.score, reverse=True)
        return results[:limit]

    def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Keyword search scored by how much of the query matched.

        ``lexical_score`` is the IDF-weighted share of the query's meaningful words found in the
        document (0..1): rare words count more than common ones, stopwords do not count, and
        query words that appear in no document lower every score. Ties go to the document that
        repeats the matched words more often.
        """
        terms = query_terms(query)
        if not terms:
            return []
        if self.scoring == "bm25":
            return self._bm25(terms, limit)
        with self._lock:
            total_docs = len(self.documents)
            postings = {term: dict(self.postings.get(term, {})) for term in terms}
            docs_snapshot = dict(self.documents)
        idf = {
            term: math.log(1.0 + (total_docs - len(docs) + 0.5) / (len(docs) + 0.5))
            for term, docs in postings.items()
        }
        query_weight = sum(idf.values()) or 1.0
        matched: dict[str, float] = defaultdict(float)
        counts: Counter[str] = Counter()
        for term, docs in postings.items():
            for doc_id, count in docs.items():
                matched[doc_id] += idf[term]
                counts[doc_id] += count
        results = [
            SearchResult(
                id=doc_id,
                collection=docs_snapshot[doc_id].collection,
                text=docs_snapshot[doc_id].text,
                score=round(weight / query_weight, 6),
                lexical_score=round(weight / query_weight, 6),
                metadata=docs_snapshot[doc_id].metadata,
            )
            for doc_id, weight in matched.items()
            if doc_id in docs_snapshot
        ]
        results.sort(key=lambda result: (result.score, counts[result.id]), reverse=True)
        return results[:limit]

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
                self.lengths = {
                    doc_id: len(tokenize(document.text))
                    for doc_id, document in self.documents.items()
                }
        except Exception:
            pass
