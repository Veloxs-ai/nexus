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

"""What a person reviews in a knowledge graph: merge proposals and concept promotion.

``merge_proposals(resolution, names=)`` turns ``Resolution.proposals`` into a stable list of
``MergeProposal`` rows (one per unordered pair, highest score kept, sorted by score then
keys) with the reason the pair was not merged: ``ambiguous`` (the name matches several
entities), ``both_structured`` (two table entities are never merged automatically),
``legal_suffix`` ("Acme Inc" / "Acme Ltd") or ``similar_name`` (score below ``auto_merge``).

``promote_concepts(extraction, texts, documents=)`` decides which noun-phrase concepts (status
``candidate``) become active entities: a concept is promoted when it is mentioned in at least
``min_documents`` documents and is not template boilerplate. Boilerplate is a phrase whose
mentions sit in identical surrounding text across documents ("Invoices are payable within
thirty days of receipt", "Please ask your manager first"): when one context (``window`` words
on each side) covers at least ``template_share`` of its documents (two or more), or
``template_share / 2`` when the phrase is in more than ``max_document_share`` of a corpus of
``min_corpus`` documents or more.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .graph_resolve import Resolution
from .graph_types import EntityRef, GraphExtraction

__all__ = ["ConceptPromotion", "MergeProposal", "merge_proposals", "promote_concepts"]

_WORD = re.compile(r"\w+")
_SENTENCE = re.compile(r"[.!?;]\s|\n")


@dataclass(frozen=True, slots=True)
class MergeProposal:
    """Two entities that may be one: ``source`` would be merged into ``target``."""

    source_type: str
    source_key: str
    target_type: str
    target_key: str
    score: float
    reason: str
    source_name: str = ""
    target_name: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "source": {"type": self.source_type, "key": self.source_key, "name": self.source_name},
            "target": {"type": self.target_type, "key": self.target_key, "name": self.target_name},
            "score": self.score,
            "reason": self.reason,
        }


def merge_proposals(
    resolution: Resolution,
    names: Mapping[tuple[str, str], str] | Iterable[EntityRef] | None = None,
) -> list[MergeProposal]:
    """The resolution's proposals as a stable, de-duplicated list (module doc)."""
    if names is None:
        lookup: Mapping[tuple[str, str], str] = {}
    elif isinstance(names, Mapping):
        lookup = names
    else:
        lookup = {e.ref: e.name for e in names}
    reasons = resolution.proposal_reasons
    best: dict[tuple[tuple[str, str], tuple[str, str]], MergeProposal] = {}
    for i, (child, into, score) in enumerate(resolution.proposals):
        reason = reasons[i] if i < len(reasons) else "similar_name"
        pair = (child, into) if child <= into else (into, child)
        old = best.get(pair)
        if old is not None and (old.score > score or (old.score == score and old.reason <= reason)):
            continue
        best[pair] = MergeProposal(
            child[0],
            child[1],
            into[0],
            into[1],
            round(float(score), 3),
            reason,
            lookup.get(child, child[1]),
            lookup.get(into, into[1]),
        )
    return sorted(
        best.values(),
        key=lambda p: (-p.score, p.source_type, p.source_key, p.target_type, p.target_key),
    )


@dataclass(frozen=True, slots=True)
class ConceptPromotion:
    promoted: frozenset[str]  # concept keys to make active
    boilerplate: frozenset[str]  # in enough documents, but in identical surrounding text
    rare: frozenset[str]  # in fewer than ``min_documents`` documents

    def apply(self, extraction: GraphExtraction) -> GraphExtraction:
        """``extraction`` with the promoted concepts active (other candidates unchanged)."""
        entities = tuple(
            EntityRef(e.key, e.name, e.type, e.origin, e.attributes, "active")
            if e.type == "concept" and e.status == "candidate" and e.key in self.promoted
            else e
            for e in extraction.entities
        )
        return GraphExtraction(
            entities, extraction.mentions, extraction.relations, extraction.aliases,
            dict(extraction.stats),
        )  # fmt: skip


def _context(text: str, start: int, end: int, window: int) -> tuple[str, str]:
    """``window`` words on each side of a mention, within its sentence."""
    left = _SENTENCE.split(text[max(0, start - 12 * window) : start])[-1]
    right = _SENTENCE.split(text[end : end + 12 * window], maxsplit=1)[0]
    words_left = _WORD.findall(left.casefold())[-window:]
    return " ".join(words_left), " ".join(_WORD.findall(right.casefold())[:window])


def promote_concepts(
    extraction: GraphExtraction,
    texts: Mapping[str, str],
    documents: Mapping[str, str] | None = None,
    *,
    min_documents: int = 2,
    window: int = 4,
    template_share: float = 0.6,
    max_document_share: float = 0.5,
    min_corpus: int = 10,
) -> ConceptPromotion:
    """Which candidate concepts to promote (module doc). ``texts`` maps chunk keys to the
    text the mentions' offsets refer to; ``documents`` maps chunk keys to document keys (a
    chunk is its own document when missing)."""
    documents = documents or {}
    candidates = {
        e.key for e in extraction.entities if e.type == "concept" and e.status == "candidate"
    }
    docs: dict[str, set[str]] = {}
    contexts: dict[str, dict[tuple[str, str], set[str]]] = {}
    corpus: set[str] = set()
    for m in extraction.mentions:
        doc = documents.get(m.chunk_key, m.chunk_key)
        corpus.add(doc)
        if m.entity_type != "concept" or m.entity_key not in candidates:
            continue
        docs.setdefault(m.entity_key, set()).add(doc)
        text = texts.get(m.chunk_key)
        if text is None or m.start < 0:
            continue
        sig = _context(text, m.start, m.end, window)
        contexts.setdefault(m.entity_key, {}).setdefault(sig, set()).add(doc)
    promoted, boilerplate, rare = set(), set(), set()
    n_corpus = len(corpus)
    for key in candidates:
        in_docs = docs.get(key, set())
        if len(in_docs) < min_documents:
            rare.add(key)
            continue
        share = template_share
        if n_corpus >= min_corpus and len(in_docs) / n_corpus > max_document_share:
            share = template_share / 2
        top = max((len(d) for d in contexts.get(key, {}).values()), default=0)
        if top >= 2 and top >= share * len(in_docs):
            boilerplate.add(key)
        else:
            promoted.add(key)
    return ConceptPromotion(frozenset(promoted), frozenset(boilerplate), frozenset(rare))
