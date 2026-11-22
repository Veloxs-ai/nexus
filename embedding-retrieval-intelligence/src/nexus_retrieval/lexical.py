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
    """Inverted keyword index with ``share`` or BM25 scoring.

    Re-adding an id replaces its old words (no stale postings); queries touch only the
    postings of the query words and build results for the top ``limit`` only.
    """

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
        self._total_len = 0
        self._lock = threading.Lock()

    def _drop_unlocked(self, doc_id: str) -> None:
        # The stored text gives the document's words back: no per-document word list is
        # kept in memory just for updates.
        old = self.documents.get(doc_id)
        for token in set(tokenize(old.text)) if old is not None else ():
            posting = self.postings.get(token)
            if posting is not None:
                posting.pop(doc_id, None)
                if not posting:
                    del self.postings[token]
        self._total_len -= self.lengths.pop(doc_id, 0)
        self.documents.pop(doc_id, None)

    def add(self, document: IndexedDocument) -> None:
        tokens = tokenize(document.text)
        tokens_count = Counter(tokens)
        with self._lock:
            if document.id in self.documents:
                self._drop_unlocked(document.id)
            self.documents[document.id] = document
            self.lengths[document.id] = len(tokens)
            self._total_len += len(tokens)
            for token, count in tokens_count.items():
                self.postings[token][document.id] = count

    def remove(self, doc_id: str) -> bool:
        """Forget ``doc_id`` and all of its words. Returns whether it was indexed."""
        with self._lock:
            if doc_id not in self.documents:
                return False
            self._drop_unlocked(doc_id)
            return True

    def _results(self, ranked: list[tuple[str, float]]) -> list[SearchResult]:
        out = []
        for doc_id, score in ranked:
            document = self.documents.get(doc_id)
            if document is not None:
                out.append(
                    SearchResult(
                        id=doc_id,
                        collection=document.collection,
                        text=document.text,
                        score=score,
                        lexical_score=score,
                        metadata=document.metadata,
                    )
                )
        return out

    def _bm25(
        self, terms: list[str], limit: int, k1: float = 1.2, b: float = 0.75
    ) -> list[SearchResult]:
        with self._lock:
            total_docs = len(self.documents)
            if not total_docs:
                return []
            avg_len = (self._total_len / len(self.lengths)) if self.lengths else 1.0
            lengths = self.lengths
            scores: dict[str, float] = defaultdict(float)
            for term in terms:
                docs = self.postings.get(term)
                if not docs:
                    continue
                idf = math.log(1.0 + (total_docs - len(docs) + 0.5) / (len(docs) + 0.5))
                for doc_id, tf in docs.items():
                    norm = k1 * (1 - b + b * lengths.get(doc_id, avg_len) / (avg_len or 1.0))
                    scores[doc_id] += idf * tf * (k1 + 1) / (tf + norm)
            top = max(scores.values(), default=0.0) or 1.0
            # Highest score first; ties keep first-matched order (as a stable sort would).
            keyed = ((round(s / top, 6), -n, d) for n, (d, s) in enumerate(scores.items()))
            best = heapq.nlargest(limit, keyed)
            return self._results([(d, s) for s, _, d in best])

    def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Keyword search scored by how much of the query matched.

        ``lexical_score`` is the IDF-weighted share of the query's meaningful words found in the
        document (0..1): rare words count more than common ones, stopwords do not count, and
        query words that appear in no document lower every score. Ties go to the document that
        repeats the matched words more often.
        """
        terms = query_terms(query)
        if not terms or limit <= 0:
            return []
        if self.scoring == "bm25":
            return self._bm25(terms, limit)
        with self._lock:
            total_docs = len(self.documents)
            matched: dict[str, float] = defaultdict(float)
            counts: dict[str, int] = defaultdict(int)
            postings = [(term, self.postings.get(term) or {}) for term in terms]
            idf = {
                term: math.log(1.0 + (total_docs - len(docs) + 0.5) / (len(docs) + 0.5))
                for term, docs in postings
            }
            query_weight = sum(idf.values()) or 1.0
            for term, docs in postings:
                weight = idf[term]
                for doc_id, count in docs.items():
                    matched[doc_id] += weight
                    counts[doc_id] += count
            # Score, then repeat count, then first-matched order (HEAD's stable sort).
            keyed = (
                (round(w / query_weight, 6), counts[d], -n, d)
                for n, (d, w) in enumerate(matched.items())
            )
            best = heapq.nlargest(limit, keyed)
            return self._results([(d, s) for s, _, _, d in best])

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
                "lengths": dict(self.lengths),
            }
        write_json(self.uri, self.base_dir, payload)

    def load(self) -> None:
        if self.in_memory_only:
            return
        try:
            payload = read_json(self.uri, self.base_dir)
            documents = {
                doc_id: IndexedDocument.model_validate(document)
                for doc_id, document in payload.get("documents", {}).items()
            }
            postings: dict[str, dict[str, int]] = defaultdict(dict)
            sums: dict[str, int] = defaultdict(int)
            for token, posting in payload.get("postings", {}).items():
                postings[token] = dict(posting)
                for doc_id, count in posting.items():
                    sums[doc_id] += count
            saved = payload.get("lengths") or {}
            # A document's length is the sum of its word counts: no re-tokenising on load.
            lengths = {doc_id: int(saved.get(doc_id, sums.get(doc_id, 0))) for doc_id in documents}
            with self._lock:
                self.documents = documents
                self.postings = postings
                self.lengths = lengths
                self._total_len = sum(lengths.values())
        except Exception:
            pass
