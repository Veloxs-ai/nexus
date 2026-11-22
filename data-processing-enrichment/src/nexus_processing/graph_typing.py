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

"""Entity typing for capitalised spans: lexicons, context cues and document-level voting.

Each span gets weighted type votes (3 strong, 2 medium, 1 weak):

* the span itself (``base_type``): honorific, ``Project X``, legal suffix or org head word,
  department ("Legal", "Customer Success"), unit word ("Vendor Management Office"), known
  organisation or product, model number ("Zephyr X2", "Atlas 300"), org industry word
  ("Tidewater Logistics"), place list, given name, product or document head word;
* its context (``context_votes``): the word before ("the customer X", "joined X", "in X",
  "at X") and the words after ("the X migration", "the X upgrade", "the X office",
  "X requested ...");
* coordination: "Soylent, Cyberdyne and Vandelay Industries" share the type of the typed one.

``finalise_document`` sums the votes of every mention of a name in a document (and gives a
lone "Olivia" or "Bluepeak" the type of "Olivia Chen" or "Bluepeak Energy" there), so all
mentions of a name in one document get one type. Names still untyped take the type the same
name got in other documents of the call (``_Acc.retype`` in ``graph_text``).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from itertools import pairwise
from typing import Any

from .graph_lexicon import (
    COMMON_WORDS,
    HEADING_WORDS,
    MONTHS,
    ORG_HEAD_WORDS,
    ORG_LEGAL_SUFFIXES,
    STOPWORDS,
    WEEKDAYS,
    ambiguous_names,
    ambiguous_places,
    given_names,
    places,
)
from .graph_resolve import key_from_base
from .graph_tokens import JOIN, Tokens

__all__ = [
    "Pending",
    "base_type",
    "context_votes",
    "finalise_document",
    "is_model_token",
    "lexicon",
    "span_votes",
]

_MODEL = re.compile(r"^(?:[A-Z]{1,3}-?\d{1,4}[a-z]{0,2}|\d{1,4}[A-Za-z]{0,2})$")
_NOT_MODEL = re.compile(r"^(?:(?:1[89]|20)\d\d|Q[1-4]|H[12]|FY\d*|\d{1,2}(?:am|pm|st|nd|rd|th))$")
_COORD = re.compile(r"^\s*(?:,|,?\s*(?:and|or|&|/))\s*$")
_DETERMINERS = frozenset(
    {
        "the",
        "a",
        "an",
        "our",
        "their",
        "its",
        "his",
        "her",
        "your",
        "this",
        "that",
        "these",
        "those",
    }
)
_PROJECT_FINALS = frozenset({"initiative", "programme", "program", "project"})
_OF_ORG = frozenset({"acquisition", "ceo", "cfo", "founder", "subsidiary", "employees"})
_PRIORITY = ("person", "org", "place", "product", "project", "concept", "record")
_CONF = {"org": 0.8, "person": 0.75, "place": 0.75, "product": 0.7, "project": 0.7}


class _Lexicon:
    """The org / product / cue word sets, built once on first use."""

    def __init__(self) -> None:
        from . import graph_orgs as g

        def pack(text: str) -> frozenset[str]:
            return frozenset(w.replace("_", " ") for w in text.split())

        self.org_finals = pack(g.ORG_FINALS)
        self.departments = pack(g.DEPARTMENTS)
        self.unit_finals = pack(g.UNIT_FINALS)
        self.known_orgs = pack(g.KNOWN_ORGS)
        self.known_products = pack(g.KNOWN_PRODUCTS)
        self.product_finals = pack(g.PRODUCT_FINALS)
        self.concept_finals = pack(g.CONCEPT_FINALS)
        self.org_verbs = pack(g.ORG_VERBS)
        self.subject_verbs = pack(g.SUBJECT_VERBS)
        self.model_stop = pack(g.MODEL_STOP) | COMMON_WORDS | MONTHS | WEEKDAYS | HEADING_WORDS
        self.next_cues = {w: t for t, text in g.NEXT_CUES.items() for w in pack(text)}
        self.prev_cues = {w: (t, n) for t, (n, text) in g.PREV_CUES.items() for w in pack(text)}
        self.weak_prev = dict(g.WEAK_PREV)
        self.known = self.known_orgs | self.known_products


_LEX: list[_Lexicon] = []


def lexicon() -> _Lexicon:
    if not _LEX:
        _LEX.append(_Lexicon())
    return _LEX[0]


def is_model_token(tok: str) -> bool:
    """A model or variant number after a name: ``X2``, ``R7``, ``300``, ``5G`` (not years)."""
    return bool(_MODEL.match(tok)) and not _NOT_MODEL.match(tok)


def base_type(folds: Sequence[str], honorific: bool = False) -> tuple[str, int]:
    """The type the span's own words suggest and its weight (0 for ``entity``)."""
    if honorific:
        return "person", 3
    lex = lexicon()
    core = list(folds)
    while len(core) > 1 and any(c.isdigit() for c in core[-1]):
        core.pop()
    model = len(core) < len(folds)
    last = core[-1].rstrip(".")
    multi = len(core) > 1
    if multi and core[0] in ("project", "operation", "programme", "program", "initiative"):
        return "project", 3
    if last in ORG_LEGAL_SUFFIXES or last in ORG_HEAD_WORDS:
        return "org", 3
    if any(core[k] in ORG_HEAD_WORDS and core[k + 1] == "of" for k in range(len(core) - 1)):
        return "org", 3
    joined = " ".join(core)
    if joined in lex.departments or (multi and last in lex.unit_finals):
        return "org", 3
    if joined in lex.known_orgs:
        return "org", 3
    if joined in lex.known_products:
        return "product", 3
    if model and core[0] not in lex.model_stop:
        return "product", 3  # a model number: "Zephyr X2", "Atlas 300"
    if joined in places() and joined not in ambiguous_places():
        return "place", 3  # an ambiguous place ("Reading", "Aurora") needs a cue
    if multi and last in lex.org_finals:
        return "org", 3
    if multi and last in _PROJECT_FINALS:
        return "project", 3  # "Orion Initiative", "Apollo Programme" (not a person "Orion ...")
    names = given_names()
    if 2 <= len(core) <= 3 and core[0] in names and not any(f in COMMON_WORDS for f in core[1:]):
        return "person", 3
    if multi and last in lex.product_finals:
        return "product", 2
    if multi and last in lex.concept_finals:
        return "concept", 2
    if not multi and core[0] in names and core[0] not in ambiguous_names():
        return "person", 2
    return "entity", 0


def context_votes(tk: Tokens, first: int, last: int) -> list[tuple[str, int]]:
    """Type votes from the words around tokens ``first..last`` of ``tk``."""
    lex = lexicon()
    toks, folds, flags = tk.toks, tk.folds, tk.flags
    votes: list[tuple[str, int]] = []
    p = first - 1
    if p >= 0:
        label = not flags[first] & JOIN and tk.gap_before(first).strip() == ":"
        if label or flags[first] & JOIN:
            if folds[p] in _DETERMINERS and p > 0 and flags[p] & JOIN:
                p -= 1
            fold = folds[p]
            if label or toks[p][0].islower():
                cue = lex.prev_cues.get(fold)
                if cue is not None:
                    votes.append(cue)
                elif p == first - 1 and fold in lex.weak_prev:
                    votes.append((lex.weak_prev[fold], 1))
                elif fold == "of" and p > 0 and folds[p - 1] in _OF_ORG:
                    votes.append(("org", 2))
    n = len(toks)
    k = last + 1
    for step in range(3):
        if k >= n or not flags[k] & JOIN or not toks[k][0].islower():
            break
        fold = folds[k]
        if step == 0 and fold in lex.org_verbs:
            votes.append(("org", 1))
            break
        cue = lex.next_cues.get(fold)
        if cue is None and k + 1 < n and flags[k + 1] & JOIN:
            cue = lex.next_cues.get(f"{fold} {folds[k + 1]}")
        if cue is not None:
            votes.append((cue, 2 if step == 0 else 1))
            break
        if fold in STOPWORDS or fold in lex.subject_verbs or fold.endswith("ed"):
            break
        k += 1
    return votes


_BASE_CACHE: dict[tuple[tuple[str, ...], bool], tuple[str, int]] = {}


def span_votes(
    tk: Tokens, seg: Sequence[int], folds: Sequence[str], honorific: bool
) -> tuple[dict[str, int], int]:
    """All votes for one span: its own words, then its context (weight 0 votes dropped)."""
    ck = (tuple(folds), honorific)
    base = _BASE_CACHE.get(ck)
    if base is None:
        base = base_type(folds, honorific)
        if len(_BASE_CACHE) < 65536:
            _BASE_CACHE[ck] = base
    etype, weight = base
    votes: dict[str, int] = {etype: weight} if weight else {}
    for t, w in context_votes(tk, seg[0], seg[-1]):
        votes[t] = votes.get(t, 0) + w
    return votes, weight


class Pending:
    """A capitalised span whose type is decided per document (``finalise_document``)."""

    __slots__ = ("conf_len", "e", "first", "generic", "s", "surface", "votes")

    def __init__(
        self, first: int, s: int, e: int, surface: str, votes: dict, n: int, generic: str
    ) -> None:
        self.first, self.s, self.e, self.surface, self.votes = first, s, e, surface, votes
        self.conf_len, self.generic = n, generic


def _best(votes: dict[str, int]) -> str:
    if not votes:
        return "entity"
    if len(votes) == 1:
        return next(iter(votes))
    top = max(votes.values())
    return next(t for t in _PRIORITY if votes.get(t) == top)


def _add(into: dict[str, int], votes: dict[str, int], times: int = 1) -> None:
    for t, w in votes.items():
        into[t] = into.get(t, 0) + w * times


def _coordinate(tk: Tokens, hits: list) -> None:
    """Untyped names coordinated with typed ones take their type (weight 1)."""
    ordered = sorted(hits, key=lambda h: h[3])
    groups: list[list] = [[ordered[0]]]
    for prev, cur in pairwise(ordered):
        if _COORD.match(tk.text[prev[4] : cur[3]]):
            groups[-1].append(cur)
        else:
            groups.append([cur])
    for group in groups:
        if len(group) < 2:
            continue
        typed = set()
        for h in group:
            if len(h) <= 7:
                if h[1] not in ("entity", "concept", "record"):
                    typed.add(h[1])
            elif h[7].votes and max(h[7].votes.values()) >= 2:
                typed.add(_best(h[7].votes))
        if len(typed) == 1:
            etype = typed.pop()
            for h in group:
                if len(h) > 7 and not h[7].votes:
                    h[7].votes[etype] = 1


def finalise_document(tokenised: Sequence[tuple[str, Tokens]], found: list[list], acc: Any) -> None:
    """Decide the type of every pending span of one document; rewrite its hits in place."""
    totals: dict[str, dict[str, int]] = {}
    for (_, tk), hits in zip(tokenised, found, strict=True):
        if len(hits) > 1 and any(len(h) > 7 and not h[7].votes for h in hits):
            _coordinate(tk, hits)
        for h in hits:
            if len(h) > 7:
                p = h[7]
                bucket = totals.get(p.generic)
                if bucket is None:
                    totals[p.generic] = dict(p.votes)
                else:
                    _add(bucket, p.votes)
    partial: dict[str, dict[str, int]] = {}
    for generic, votes in totals.items():
        if " " not in generic or not votes:
            continue
        etype = _best(votes)
        words = generic.split()
        for w in (words[0], words[-1]) if etype == "person" else (words[0],):
            _add(partial.setdefault(w, {}), {etype: 2})
    final: dict[str, tuple[str, str]] = {}
    for generic, votes in totals.items():
        extra = partial.get(generic)
        if extra:
            votes = dict(votes)
            _add(votes, extra)
        etype = _best(votes)
        final[generic] = (etype, key_from_base(generic, etype))
    type_votes = acc.type_votes
    for hits in found:
        out = []
        for h in hits:
            if len(h) <= 7:
                out.append(h)
                continue
            p: Pending = h[7]
            etype, key = final[p.generic]
            if not key:
                continue
            acc.entity(etype, key, p.surface)
            if etype != "entity":
                bucket = type_votes.setdefault(p.generic, {})
                bucket[etype] = bucket.get(etype, 0) + 1
            conf = _CONF.get(etype, 0.7 if p.conf_len > 1 else 0.6)
            out.append((p.first, etype, key, p.s, p.e, "caps", conf))
        hits[:] = out
