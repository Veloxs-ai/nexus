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

"""Document-level routing: which documents a question is about, out of thousands.

  rank_documents     the catalog ordered by relevance to a question: BM25 over each document's
                     name (x3) and summary, fused (weighted Reciprocal Rank Fusion) with the
                     caller's summary-vector ranking, chunk-level keyword hits and named documents
  question_mentions  the entities a question names: quoted phrases, capitalised names
                     ("Orion Retail") and identifiers ("P1", "C-1014")
  candidate_documents
                     every document a "list every / how many / everything about X" question needs
                     read: the documents that mention its entities, else those whose keyword hits
                     carry most of the question's weight (IDF), plus the closest summary vectors
  knowledge_index    the knowledge-index text: counts by type and the documents most relevant to
                     the question, within a token budget

Standard library only. Indexes over a catalog are cached by its content, so a catalog of 5,000
documents is tokenised once, not on every question.
"""

from __future__ import annotations

import math
import re
import threading
from collections import Counter, OrderedDict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .text_terms import STOPWORDS, question_terms, stem, terms, words

__all__ = [
    "Candidates",
    "DocumentIndex",
    "RankedDocument",
    "candidate_documents",
    "knowledge_index",
    "question_mentions",
    "rank_documents",
]

SUMMARY_CHARS = 400  # summary text used for ranking (the digest's head names the content)
NAME_WEIGHT = 3.0
LIST_WEIGHTS = {"named": 4.0, "mentions": 2.0, "catalog": 1.0, "vector": 1.0, "chunks": 1.0}
RRF_K = 60
_INDEX_CACHE: OrderedDict[int, _CatalogIndex] = OrderedDict()
_INDEX_CACHE_MAX = 8
_PARTS_MAX = 4096  # terms whose per-document BM25 parts an index keeps
_LOCK = threading.Lock()


@dataclass
class RankedDocument:
    id: str
    score: float
    reasons: tuple[str, ...] = ()


class _CatalogIndex:
    """BM25 postings over the names and summaries of one catalog."""

    def __init__(self, docs: list[tuple[str, str, str]]) -> None:
        self.ids = [d[0] for d in docs]
        self.order = {doc_id: i for i, doc_id in enumerate(self.ids)}  # last position wins
        self.fields: list[tuple[Counter, Counter]] = []
        self.lengths: list[tuple[int, int]] = []  # terms in (name, summary), counted once
        self.postings: dict[str, list[int]] = {}
        self.parts: dict[tuple[str, float, float], list[float]] = {}  # per term, on first use
        name_len = sum_len = 0
        for i, (_id, name, summary) in enumerate(docs):
            name_terms = Counter(_terms_list(re.sub(r"[._/]+", " ", name)))
            summary_terms = Counter(_terms_list(summary[:SUMMARY_CHARS]))
            self.fields.append((name_terms, summary_terms))
            lengths = (sum(name_terms.values()), sum(summary_terms.values()))
            self.lengths.append(lengths)
            name_len += lengths[0]
            sum_len += lengths[1]
            for term in set(name_terms) | set(summary_terms):
                self.postings.setdefault(term, []).append(i)
        n = max(len(docs), 1)
        self.avg = (name_len / n or 1.0, sum_len / n or 1.0)

    def _term(self, term: str, hits: list[int], k1: float, b: float) -> list[float]:
        """The BM25 term-frequency part of ``term`` for each document of ``hits``."""
        key = (term, k1, b)
        parts = self.parts.get(key)
        if parts is not None:
            return parts
        fields, lengths = self.fields, self.lengths
        weights = ((0, NAME_WEIGHT, self.avg[0]), (1, 1.0, self.avg[1]))
        parts = []
        for i in hits:
            total = 0.0
            for field_at, weight, avg in weights:
                tf = fields[i][field_at].get(term, 0)
                if tf:
                    length = lengths[i][field_at]
                    total += weight * tf * (k1 + 1) / (tf + k1 * (1 - b + b * length / avg))
            parts.append(total)
        with _LOCK:
            if len(self.parts) < _PARTS_MAX:
                self.parts[key] = parts
        return parts

    def scores(self, query: list[str], k1: float = 1.2, b: float = 0.75) -> dict[int, float]:
        n = len(self.ids)
        out: dict[int, float] = {}
        for term in query:
            hits = self.postings.get(term)
            if not hits:
                continue
            idf = math.log(1.0 + (n - len(hits) + 0.5) / (len(hits) + 0.5))
            for i, total in zip(hits, self._term(term, hits, k1, b), strict=True):
                out[i] = out.get(i, 0.0) + idf * total
        return out


def _terms_list(text: str) -> list[str]:
    return [stem(w) for w in words(text) if w not in STOPWORDS]


def _index(docs: list[tuple[str, str, str]]) -> _CatalogIndex:
    key = hash(tuple(docs))
    with _LOCK:
        hit = _INDEX_CACHE.get(key)
        if hit is not None:
            _INDEX_CACHE.move_to_end(key)
            return hit
    built = _CatalogIndex(docs)
    with _LOCK:
        _INDEX_CACHE[key] = built
        while len(_INDEX_CACHE) > _INDEX_CACHE_MAX:
            _INDEX_CACHE.popitem(last=False)
    return built


def _documents(
    documents: Sequence[Mapping[str, Any]], id_key: str, name_key: str, summary_key: str
) -> list[tuple[str, str, str]]:
    return [
        (str(d.get(id_key) or ""), str(d.get(name_key) or ""), str(d.get(summary_key) or ""))
        for d in documents
    ]


def _rank(
    index: _CatalogIndex,
    question: str,
    vector: Sequence[str],
    chunks: Sequence[str],
    named: Iterable[str],
    mentions: Sequence[str],
    limit: int | None,
    include_unmatched: bool,
) -> list[RankedDocument]:
    query = question_terms(question)
    lexical = sorted(index.scores(query).items(), key=lambda kv: (-kv[1], kv[0]))
    lists: dict[str, list[str]] = {
        "named": list(dict.fromkeys(str(x) for x in named)),
        "mentions": list(dict.fromkeys(str(x) for x in mentions)),
        "catalog": [index.ids[i] for i, _ in lexical],
        "vector": list(dict.fromkeys(str(x) for x in vector)),
        "chunks": list(dict.fromkeys(str(x) for x in chunks)),
    }
    order = index.order
    scores: dict[str, float] = {}
    reasons: dict[str, list[str]] = {}
    for name, ranked in lists.items():
        weight = LIST_WEIGHTS[name]
        for rank, doc_id in enumerate(ranked):
            if doc_id in order:
                scores[doc_id] = scores.get(doc_id, 0.0) + weight / (RRF_K + rank + 1)
                reasons.setdefault(doc_id, []).append(name)
    ranked_ids = sorted(scores, key=lambda d: (-scores[d], order[d]))
    if limit is not None and limit >= 0:  # only the shown documents are built
        ranked_ids = ranked_ids[:limit]
    out = [RankedDocument(d, round(scores[d], 6), tuple(reasons[d])) for d in ranked_ids]
    if include_unmatched:
        out += [RankedDocument(d, 0.0) for d in index.ids if d not in scores]
    return out[:limit] if limit is not None else out


def rank_documents(
    question: str,
    documents: Sequence[Mapping[str, Any]],
    *,
    vector: Sequence[str] = (),
    chunks: Sequence[str] = (),
    named: Iterable[str] = (),
    mentions: Sequence[str] = (),
    limit: int | None = None,
    include_unmatched: bool = False,
    id_key: str = "document_id",
    name_key: str = "document_name",
    summary_key: str = "summary",
) -> list[RankedDocument]:
    """``documents`` ordered by relevance to ``question``.

    ``vector``: document ids by summary-vector similarity (best first); ``chunks``: document
    ids in the order of their best chunk-level keyword hit; ``named``: ids the question names;
    ``mentions``: ids of documents that mention the question's entities. The lists are fused
    with weighted RRF (named x4, mentions x2, the rest x1). Documents that no list ranks come
    last in catalog order when ``include_unmatched`` (else they are left out). For many
    questions over one catalog, ``DocumentIndex`` builds the index once."""
    index = _index(_documents(documents, id_key, name_key, summary_key))
    return _rank(index, question, vector, chunks, named, mentions, limit, include_unmatched)


class DocumentIndex:
    """A catalog's routing index, built once and reused for every question until the catalog
    changes (``rank`` gives exactly what ``rank_documents`` gives for the same catalog)."""

    def __init__(self, index: _CatalogIndex, version: Any = None) -> None:
        self._index = index
        self.version = version

    @classmethod
    def build(
        cls,
        documents: Sequence[Mapping[str, Any]],
        *,
        id_key: str = "document_id",
        name_key: str = "document_name",
        summary_key: str = "summary",
        version: Any = None,
    ) -> DocumentIndex:
        """The index of ``documents`` (``version``: the caller's catalog version, kept as is so
        the caller can tell when to rebuild)."""
        return cls(_CatalogIndex(_documents(documents, id_key, name_key, summary_key)), version)

    def __len__(self) -> int:
        return len(self._index.ids)

    @property
    def ids(self) -> list[str]:
        return list(self._index.ids)

    def rank(
        self,
        question: str,
        *,
        vector: Sequence[str] = (),
        chunks: Sequence[str] = (),
        named: Iterable[str] = (),
        mentions: Sequence[str] = (),
        limit: int | None = None,
        include_unmatched: bool = False,
    ) -> list[RankedDocument]:
        """``rank_documents`` over this index's catalog."""
        return _rank(
            self._index, question, vector, chunks, named, mentions, limit, include_unmatched
        )


_QUOTED = re.compile(r"[\"“”']([^\"“”']{2,80})[\"“”']")
_CAPITALISED = re.compile(r"\b[A-Z][\w&'.-]*(?:\s+(?:of|de|&|and|the)?\s*[A-Z][\w&'.-]*)+")
_SINGLE = re.compile(r"(?<![\w-])[A-Z][a-z][\w&'-]{1,}(?![\w-])")
_IDENT = re.compile(
    r"(?<![\w-])(?=[\w-]*\d)(?=[\w-]*[A-Za-z])[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*"
)
_ASK_TEXT = (
    "list show give tell which what who how when where is are does do did can could please name "
    "find count summarize summarise compare everything all every"
)
_ASK_WORDS = frozenset(_ASK_TEXT.split())


def question_mentions(question: str) -> list[str]:
    """Entities a question names, as written: quoted phrases, runs of capitalised words that are
    not just the question's first word ("Orion Retail", "Bank of Baroda") and identifiers with
    a digit ("P1", "C-1014"). Years and plain numbers are not entities."""
    text = question or ""
    found: list[str] = [m.group(1).strip() for m in _QUOTED.finditer(text)]
    for m in _CAPITALISED.finditer(text):
        parts = m.group(0).split()
        while parts and parts[0].lower() in _ASK_WORDS:
            parts = parts[1:]
        if len(parts) >= 2 or (parts and m.start() > 0 and len(parts[0]) > 2):
            found.append(" ".join(parts).rstrip(".,;:?!"))
    for m in _SINGLE.finditer(text):  # one capitalised word inside a sentence: "... for Globex"
        before = text[: m.start()].rstrip()
        if before and before[-1] not in ".?!:\n\"'" and m.group(0).lower() not in _ASK_WORDS:
            found.append(m.group(0))
    found += [m.group(0) for m in _IDENT.finditer(text)]
    out: list[str] = []
    for phrase in found:
        if phrase and phrase.lower() not in {p.lower() for p in out}:
            out.append(phrase)
    # "Orion" alone is part of "Orion Retail": keep the longer name only.
    return [p for p in out if not any(o != p and mentions_in(o, [p]) for o in out)]


def mentions_in(text: str, phrases: Sequence[str]) -> list[str]:
    """The ``phrases`` that occur in ``text`` as whole words (case-insensitive)."""
    out = []
    for phrase in phrases:
        if re.search(r"(?<![\w-])" + re.escape(phrase) + r"(?![\w-])", text or "", re.I):
            out.append(phrase)
    return out


@dataclass
class Candidates:
    """The documents a question needs read, best first, and why."""

    ids: list[str]
    reasons: dict[str, str] = field(default_factory=dict)
    route: str = "terms"  # "mentions" | "terms" | "vector"
    terms: list[str] = field(default_factory=list)


def candidate_documents(
    question: str,
    chunks: Iterable[Mapping[str, Any]],
    *,
    total_documents: int,
    mention_hits: Mapping[str, Sequence[str]] | None = None,
    vector: Sequence[str] = (),
    vector_extra: int = 10,
    min_share: float = 0.5,
    id_key: str = "document_id",
    text_key: str = "text",
) -> Candidates:
    """Every document a whole-knowledge question ("list every ...", "how many ...", "everything
    about X") needs read, best first.

    ``mention_hits``: {document id: entity phrases its text contains} (``question_mentions``
    looked up by the caller). When the question names entities and documents mention them,
    those documents are the candidates (most phrases first). Otherwise ``chunks`` (chunk rows
    with ``document_id`` and ``text``: the caller's keyword hits for the question) decide: a
    document is a candidate when the question terms its chunks contain carry at least
    ``min_share`` of the question's IDF weight (terms no document contains do not count). The
    ``vector_extra`` best summary-vector documents are added, for wording the keywords miss."""
    qterms = question_terms(question)
    if mention_hits:
        hits = {str(d): list(p) for d, p in mention_hits.items() if p}
        if hits:
            ordered = sorted(hits, key=lambda d: -len(hits[d]))
            return Candidates(
                ordered, {d: "mentions " + ", ".join(hits[d]) for d in ordered}, "mentions", qterms
            )
    matched: dict[str, set[str]] = {}
    first_seen: dict[str, int] = {}
    want = set(qterms)
    for n, row in enumerate(chunks):
        doc_id = str(row.get(id_key) or "")
        found = want & terms(str(row.get(text_key) or ""))
        if not doc_id or not found:
            continue
        matched.setdefault(doc_id, set()).update(found)
        first_seen.setdefault(doc_id, n)
    df = Counter(t for found in matched.values() for t in found)
    n_docs = max(total_documents, len(matched), 1)
    idf = {t: math.log(1.0 + n_docs / df[t]) for t in df}
    total = sum(idf.values()) or 1.0
    weights = {d: sum(idf[t] for t in found) / total for d, found in matched.items()}
    keep = [d for d, w in weights.items() if w >= min_share - 1e-9]
    keep.sort(key=lambda d: (-weights[d], first_seen[d]))
    reasons = {d: "terms " + ", ".join(sorted(matched[d])) for d in keep}
    for doc_id in list(dict.fromkeys(str(v) for v in vector))[:vector_extra]:
        if doc_id not in reasons:
            keep.append(doc_id)
            reasons[doc_id] = "summary vector"
    return Candidates(keep, reasons, "terms" if matched else "vector", qterms)


def knowledge_index(
    documents: Sequence[Mapping[str, Any]],
    *,
    total: int | None = None,
    counts: Mapping[str, int] | None = None,
    heading: str | None = None,
    max_tokens: int = 3000,
    summary_chars: int = 220,
    describe: Any = None,
) -> str:
    """The knowledge-index text: ``"N document(s) in this knowledge:"``, the counts by type when
    only part is listed, then one line per document (``- name (type, size): summary``) until
    ``max_tokens`` (estimated at 4 characters per token). ``describe(doc)`` gives the
    "(type, size)" part; ``documents`` are listed in the order given."""
    total = len(documents) if total is None else total
    lines = [f"{total} document(s) in this knowledge:"]
    if counts and total > len(documents):
        lines.append(
            "By type: "
            + ", ".join(
                f"{n:,} {kind}" for kind, n in sorted(counts.items(), key=lambda kv: -kv[1])
            )
            + "."
        )
    if heading and total > len(documents):
        lines.append(heading)
    budget = max_tokens * 4 - sum(len(x) + 1 for x in lines)
    shown = 0
    for doc in documents:
        name = str(doc.get("document_name") or "")
        summary = " ".join(str(doc.get("summary") or "").split())
        summary = summary.removeprefix(f"Document: {name}").strip(" .")
        kind = describe(doc) if describe else str(doc.get("file_type") or "document")
        line = f"- {name} ({kind})" + (f": {summary[:summary_chars]}" if summary else "")
        if len(line) + 1 > budget:
            line = f"- {name} ({kind})"
            if len(line) + 1 > budget:
                break
        lines.append(line)
        budget -= len(line) + 1
        shown += 1
    if total > shown:
        lines.append(f"- … and {total - shown:,} more")
    return "\n".join(lines)
