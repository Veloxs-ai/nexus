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

"""Noun-phrase concepts for the text extractor (POS-free).

``np_runs(tokens, covered)`` finds maximal runs of lowercase content words (no stopword,
auxiliary or frequent verb) that end in a noun-like head; ``rank_concepts`` keeps, per run,
the head-anchored phrase of 2-4 words with the best C-value termhood in the document and at
most ``per_chunk`` phrases per chunk.
"""

from __future__ import annotations

import math
from collections import Counter

from .graph_lexicon import ADJ_SUFFIXES, STOPWORDS, VERBS
from .graph_tokens import JOIN, Tokens

__all__ = ["np_runs", "rank_concepts"]


def _noun_like(fold: str) -> bool:
    return not (fold.endswith("ed") or fold.endswith(ADJ_SUFFIXES) or fold in VERBS)


def np_runs(tk: Tokens, covered: bytearray) -> list[tuple[tuple[str, ...], int, int]]:
    """Maximal runs of lowercase content words (start token, end token) with their folds."""
    toks, folds, flags, blocked = tk.toks, tk.folds, tk.flags, tk.blocked
    content = [
        k
        for k, t in enumerate(toks)
        if t[0].islower()
        and len(t) >= 3
        and t.isalpha()
        and not covered[k]
        and folds[k] not in STOPWORDS
        and folds[k] not in VERBS
        and k not in blocked
    ]
    runs: list[tuple[tuple[str, ...], int, int]] = []
    if not content:
        return runs
    start = prev = content[0]
    for k in [*content[1:], -1]:
        if k == prev + 1 and flags[k] & JOIN:
            prev = k
            continue
        end = prev + 1
        while end - start >= 2 and not _noun_like(folds[end - 1]):
            end -= 1
        if end - start >= 2:
            runs.append((tuple(folds[start:end]), start, end))
        start = prev = k
    return runs


def rank_concepts(
    np_runs: list[list[tuple[tuple[str, ...], int, int]]], per_chunk: int
) -> list[list[tuple[tuple[str, ...], int, int]]]:
    """Best head-anchored phrase of each run by C-value in the document, top ``per_chunk``."""
    freq: Counter[tuple[str, ...]] = Counter()
    for runs in np_runs:
        for folds, _, _ in runs:
            for s in range(max(0, len(folds) - 4), len(folds) - 1):
                freq[folds[s:]] += 1
    nested: dict[tuple[str, ...], list[int]] = {}
    for phrase, f in freq.items():
        for s in range(1, len(phrase) - 1):
            nested.setdefault(phrase[s:], []).append(f)

    def cvalue(phrase: tuple[str, ...]) -> float:
        f = freq[phrase]
        longer = nested.get(phrase)
        if longer:
            f = f - sum(longer) / len(longer)
        return math.log2(len(phrase)) * f

    out = []
    for runs in np_runs:
        best: dict[tuple[str, ...], tuple[float, list[tuple[int, int]]]] = {}
        for folds, s, e in runs:
            scored = [
                (cvalue(folds[k:]), folds[k:], k)
                for k in range(max(0, len(folds) - 4), len(folds) - 1)
            ]
            score, phrase, k = max(scored)
            if score <= 0:
                continue
            entry = best.setdefault(phrase, (score, []))
            entry[1].append((s + k, e))
        ranked = sorted(best.items(), key=lambda kv: (-kv[1][0], kv[0]))[:per_chunk]
        out.append([(phrase, s, e) for phrase, (_, spans) in ranked for s, e in spans])
    return out
