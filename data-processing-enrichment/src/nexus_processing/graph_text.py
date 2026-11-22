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

"""Entity mentions in text, standard library only (no NER model).

``extract_mentions(chunks, gazetteer=, config=, extra_detector=)`` reads ``(chunk_key, text)``
or ``(chunk_key, text, document_key)`` items. Run it on masked text: mask tokens are skipped,
so names the PII policy removed never become entities. Chunks of one document should be
consecutive; document-level evidence (capitalisation seen mid-sentence, abbreviation
definitions, noun-phrase termhood) is shared by the chunks of a document. Without document
keys, one call is one document.

Passes per document, all on one tokenisation (``graph_tokens.tokenise``):

1. gazetteer (known entities and aliases, longest match; confidence 0.95);
2. ``extra_detector`` spans, e.g. a NER model the caller owns (0.85, method ``hook``);
3. ids such as ``C-1014``, ``INC0012345`` (type ``record``, 0.9);
4. abbreviations: ``Long Form Name (LFN)`` and ``LFN (Long Form Name)``; later bare ``LFN``
   tokens are mentions of the long form (0.9);
5. capitalised spans with ``of``/``and``/``&``/``de``... inside and the precision filters of
   the design (sentence-start single tokens need mid-sentence evidence; common words,
   months, weekdays, headings and spans of 6+ tokens dropped);
6. noun phrases (``concept``, status ``candidate``): runs of 2-4 lowercase content words
   ending in a noun-like head, ranked by C-value in the document, at most 8 per chunk;
7. typing: gazetteer type, org suffix/head word, honorific or given name, place list;
8. ``co_mentioned`` relations between the active entities of a sentence (one evidence row per
   pair and chunk, with a count).

Gazetteer hits refer to entities the caller already holds, so they produce mentions but no
``EntityRef``.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass

from .graph_phrases import np_runs, rank_concepts
from .graph_resolve import normalise_name
from .graph_spans import find_abbreviations, token_pass, type_of_span
from .graph_tokens import START, Gazetteer, Tokens, tokenise
from .graph_types import Alias, EntityRef, GraphExtraction, Mention, RelationRef

__all__ = ["TextGraphConfig", "extract_mentions", "type_of_span"]


@dataclass(frozen=True, slots=True)
class TextGraphConfig:
    gazetteer: bool = True
    ids: bool = True
    abbreviations: bool = True
    capitalised: bool = True
    noun_phrases: bool = True
    relations: bool = True
    max_span_tokens: int = 5
    max_concepts_per_chunk: int = 8
    max_entities_per_sentence: int = 12
    max_chunks_per_document: int = 2000


class _Acc:
    """Accumulates one call's output."""

    def __init__(self) -> None:
        self.surfaces: dict[tuple[str, str], Counter[str]] = {}
        self.status: dict[tuple[str, str], str] = {}
        self.mentions: list[Mention] = []
        self.relations: Counter[tuple[str, str, str, str, str]] = Counter()
        self.aliases: dict[tuple[str, str, str], Alias] = {}
        self.stats: Counter[str] = Counter()

    def entity(self, etype: str, key: str, surface: str, status: str = "active") -> None:
        ref = (etype, key)
        bucket = self.surfaces.get(ref)
        if bucket is None:
            bucket = self.surfaces[ref] = Counter()
            self.status[ref] = status
        elif status == "active":
            self.status[ref] = "active"
        bucket[surface] += 1

    def result(self) -> GraphExtraction:
        entities = tuple(
            EntityRef(
                ref[1],
                max(c.items(), key=lambda kv: (kv[1], kv[0]))[0],
                ref[0],
                "text",
                (),
                self.status[ref],
            )
            for ref, c in self.surfaces.items()
        )
        relations = tuple(
            RelationRef(sk, st, dk, dt, "co_mentioned", chunk, n, "text")
            for (st, sk, dt, dk, chunk), n in self.relations.items()
        )
        stats = dict(self.stats)
        stats["text_entities"] = len(entities)
        stats["text_mentions"] = len(self.mentions)
        stats["text_relations"] = len(relations)
        return GraphExtraction(
            entities, tuple(self.mentions), relations, tuple(self.aliases.values()), stats
        )


def _documents(chunks: Iterable[Sequence[str]], cap: int) -> Iterator[list[tuple[str, str]]]:
    current: list[tuple[str, str]] = []
    current_doc: object = None
    for item in chunks:
        doc = item[2] if len(item) > 2 else None
        if current and (doc != current_doc or len(current) >= cap):
            yield current
            current = []
        current_doc = doc
        current.append((str(item[0]), item[1] or ""))
    if current:
        yield current


def extract_mentions(
    chunks: Iterable[Sequence[str]],
    *,
    gazetteer: Gazetteer | None = None,
    config: TextGraphConfig | None = None,
    extra_detector: Callable[[str], Iterable[tuple[int, int, str]]] | None = None,
) -> GraphExtraction:
    """Mentions, text entities, co-mention relations and abbreviation aliases (module doc)."""
    config = config or TextGraphConfig()
    acc = _Acc()
    for doc in _documents(chunks, config.max_chunks_per_document):
        _document(doc, gazetteer if config.gazetteer else None, config, extra_detector, acc)
    return acc.result()


def _document(
    doc: list[tuple[str, str]],
    gazetteer: Gazetteer | None,
    config: TextGraphConfig,
    extra_detector: Callable[[str], Iterable[tuple[int, int, str]]] | None,
    acc: _Acc,
) -> None:
    tokenised = [(key, tokenise(text)) for key, text in doc]
    mid_caps: set[str] = set()
    lower_seen: set[str] = set()
    abbrs: dict[str, tuple[str, str, str]] = {}  # abbreviation -> (type, key, long form)
    for _, tk in tokenised:
        acc.stats["chars"] += len(tk.text)
        acc.stats["tokens"] += len(tk)
        toks, flags = tk.toks, tk.flags
        for i, tok in enumerate(toks):
            c = tok[0]
            if c.isupper():
                if not flags[i] & START:
                    mid_caps.add(tok)
            elif c.islower():
                lower_seen.add(tk.folds[i])
        if config.abbreviations and "(" in tk.text:
            find_abbreviations(tk, abbrs)
    for abbr, (etype, key, long_form) in abbrs.items():
        alias_key = normalise_name(abbr)
        acc.aliases[(alias_key, etype, key)] = Alias(alias_key, abbr, key, etype, "abbrev", 0.9)
        acc.entity(etype, key, long_form)
    acc.stats["chunks"] += len(tokenised)
    runs: list[list[tuple[tuple[str, ...], int, int]]] = []
    found: list[list[tuple[int, str, str, int, int, str, float]]] = []
    for _, tk in tokenised:
        covered = bytearray(len(tk))
        hits: list[
            tuple[int, str, str, int, int, str, float]
        ] = []  # (tok, type, key, s, e, method, conf)
        if gazetteer is not None and len(gazetteer):
            _gazetteer_pass(tk, gazetteer, covered, hits)
        if extra_detector is not None:
            _hook_pass(tk, extra_detector, covered, hits, acc)
        token_pass(tk, config, abbrs, mid_caps, lower_seen, covered, hits, acc)
        found.append(hits)
        runs.append(np_runs(tk, covered) if config.noun_phrases else [])
    concepts = rank_concepts(runs, config.max_concepts_per_chunk) if config.noun_phrases else None
    for idx, (chunk_key, tk) in enumerate(tokenised):
        hits = found[idx]
        if concepts is not None:
            for phrase, s, e in concepts[idx]:
                surface = tk.text[tk.starts[s] : tk.ends[e - 1]]
                key = normalise_name(" ".join(phrase))
                acc.entity("concept", key, surface, "candidate")
                hits.append((s, "concept", key, tk.starts[s], tk.ends[e - 1], "np", 0.5))
        sentences: dict[int, dict[tuple[str, str], None]] = {}
        for tok_i, etype, key, s, e, method, conf in hits:
            acc.mentions.append(Mention(key, etype, chunk_key, s, e, tk.text[s:e], method, conf))
            acc.stats[f"method_{method}"] += 1
            if config.relations and etype != "concept":
                sentences.setdefault(tk.sentence[tok_i], {})[(etype, key)] = None
        for refs in sentences.values():
            if len(refs) < 2:
                continue
            ordered = sorted(refs)[: config.max_entities_per_sentence]
            for a in range(len(ordered)):
                for b in range(a + 1, len(ordered)):
                    (t1, k1), (t2, k2) = ordered[a], ordered[b]
                    acc.relations[(t1, k1, t2, k2, chunk_key)] += 1


def _gazetteer_pass(tk: Tokens, gazetteer: Gazetteer, covered: bytearray, hits: list) -> None:
    i, n = 0, len(tk)
    starts, ends = tk.starts, tk.ends
    while i < n:
        entry = gazetteer.match(tk, i)
        if entry is None:
            i += 1
            continue
        j = i + len(entry.folds)
        hits.append((i, entry.type, entry.key, starts[i], ends[j - 1], "gazetteer", 0.95))
        for k in range(i, j):
            covered[k] = 1
        i = j


def _hook_pass(
    tk: Tokens,
    detector: Callable[[str], Iterable[tuple[int, int, str]]],
    covered: bytearray,
    hits: list,
    acc: _Acc,
) -> None:
    for s, e, etype in detector(tk.text):
        a, b = bisect_left(tk.ends, s + 1), bisect_right(tk.starts, e - 1)
        if a >= b or any(covered[a:b]) or any(k in tk.blocked for k in range(a, b)):
            continue
        surface = tk.text[s:e]
        key = normalise_name(surface, entity_type=etype)
        if not key:
            continue
        for k in range(a, b):
            covered[k] = 1
        acc.entity(etype, key, surface)
        hits.append((a, etype, key, s, e, "hook", 0.85))
