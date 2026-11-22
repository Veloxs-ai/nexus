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

"""Tokenising chunk text once for the graph extractors, and the gazetteer (token trie).

``tokenise(text)`` runs one compiled ``finditer`` and classifies the gap before each token
(cached per distinct gap string, so ``" "`` and ``", "`` cost one dict lookup):

  JOIN   the token continues a name started by the previous token (spaces, `` & ``)
  START  the token starts a clause (text start, newline, ``. ! ? : ; > |``): capitalisation
         carries no signal there
  BREAK  a new sentence starts (co-mention scope)

Mask tokens (``[EMAIL]``, ``[REDACTED_X]``, ``<PERSON>``, ``****``) and ALL-CAPS heading lines
are marked ``blocked``: no capitalised span or noun phrase is taken from them.
"""

from __future__ import annotations

import re
from bisect import bisect_left
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import accumulate

from .graph_lexicon import COMMON_WORDS, HONORIFICS, ORG_LEGAL_SUFFIXES

__all__ = ["BREAK", "JOIN", "START", "Gazetteer", "Tokens", "tokenise"]

TOKEN = re.compile(r"[^\W_]+(?:(?:[-'’.&]|/(?=\d))[^\W_]+)*")  # "S/4HANA", "AS/400"
_SPLIT = re.compile(f"({TOKEN.pattern})")
MASK = re.compile(r"\[[A-Z][A-Z0-9_]*(?::[0-9a-f]{4,})?\]|<[A-Z][A-Z0-9_]*>|\*{3,}|█+")
HEADING_LINE = re.compile(r"^[^a-z\n]*[A-Z][^a-z\n]*$", re.MULTILINE)
JOIN, START, BREAK = 1, 2, 4
_ABBREV_JOIN = frozenset({"st", "mt", "ft", "jr", "sr"})  # "St. Mary's Hospital"
# Abbreviated legal words: "Pvt. Ltd." stays one name; "Inc., the licensor" one sentence.
_LEGAL_ABBREV = frozenset({"pvt", "co", "corp", "inc", "ltd", "pte", "pty", "bros", "intl", "llc"})
_GAP_CACHE: dict[str, int] = {"": START | BREAK, " ": JOIN}


def _gap_flags(gap: str) -> int:
    flags = _GAP_CACHE.get(gap)
    if flags is not None:
        return flags
    if gap[:1] == "." and gap[1:2] in (",", ";", ")"):
        gap = gap[1:]  # an abbreviation's full stop before a comma ("Inc., ...")
    if "\n" in gap or any(c in gap for c in ".!?"):
        flags = START | BREAK
    elif any(c in gap for c in ":;>|•·–—"):
        flags = START
    elif gap.isspace() or gap.strip() == "&":
        flags = JOIN
    else:
        flags = 0
    if len(_GAP_CACHE) < 4096:
        _GAP_CACHE[gap] = flags
    return flags


@dataclass(slots=True)
class Tokens:
    text: str
    toks: list[str]
    folds: list[str]
    starts: list[int]
    ends: list[int]
    flags: list[int]  # gap flags before each token
    sentence: list[int]  # sentence number of each token
    blocked: set[int]

    def __len__(self) -> int:
        return len(self.toks)

    def gap_before(self, i: int) -> str:
        return self.text[self.ends[i - 1] if i else 0 : self.starts[i]]


def tokenise(text: str) -> Tokens:
    parts = _SPLIT.split(text)  # gap, token, gap, token, ..., gap
    toks = parts[1::2]
    gaps = parts[0:-1:2]  # the gap before each token
    offsets = list(accumulate(map(len, parts)))
    starts = offsets[0:-1:2]
    ends = offsets[1::2]
    cache = _GAP_CACHE
    flags = [cache.get(g) for g in gaps]
    if None in flags:
        for i in [i for i, f in enumerate(flags) if f is None]:
            flags[i] = _gap_flags(gaps[i])
    folds = [t.lower() for t in toks]
    step = [0] * len(toks)
    for i in [i for i, f in enumerate(flags) if f & BREAK and i]:
        gap, prev_fold = gaps[i], folds[i - 1]
        if gap == ". " and (prev_fold in HONORIFICS or prev_fold in _ABBREV_JOIN):
            flags[i] = JOIN
        elif (
            gap == ". "
            and prev_fold in _LEGAL_ABBREV
            and (toks[i][0].islower() or folds[i].rstrip(".") in ORG_LEGAL_SUFFIXES)
        ):
            flags[i] = JOIN if toks[i][0].isupper() else 0  # "Pvt. Ltd.", "Inc. grants ..."
        else:
            step[i] = 1
    sentence = list(accumulate(step))
    blocked: set[int] = set()
    if "[" in text or "<" in text or "**" in text or "█" in text:
        spans = [m.span() for m in MASK.finditer(text)]
        if spans:
            blocked.update(_tokens_in(spans, starts, ends))
    spans = [m.span() for m in HEADING_LINE.finditer(text) if len(m.group().split()) >= 2]
    if spans:
        blocked.update(_tokens_in(spans, starts, ends))
    return Tokens(text, toks, folds, starts, ends, flags, sentence, blocked)


def _tokens_in(spans: Sequence[tuple[int, int]], starts: list[int], ends: list[int]) -> list[int]:
    out = []
    for s, e in spans:
        i = bisect_left(ends, s + 1)
        while i < len(starts) and starts[i] < e:
            out.append(i)
            i += 1
    return out


@dataclass(frozen=True, slots=True)
class _Entry:
    folds: tuple[str, ...]
    orig: tuple[str, ...]
    key: str
    type: str
    mode: str  # "fold" (any case), "cap" (first letter upper), "exact"


class Gazetteer:
    """Known entity names matched longest-first on tokens: one ``dict.get`` per token.

    Multi-token names match in any case; single tokens must be capitalised (and match exactly
    when shorter than 4 characters or ALL-CAPS, so ``IT`` and ``it`` differ). An org name
    ending in a legal suffix also matches without it (``Northwind Logistics Ltd`` ->
    ``Northwind Logistics``). A name that points at two entities is dropped (ambiguous)."""

    __slots__ = ("_first", "_size")

    def __init__(self) -> None:
        self._first: dict[str, list[_Entry]] = {}
        self._size = 0

    @classmethod
    def build(cls, names: Iterable[Sequence[str]]) -> Gazetteer:
        """``names``: ``(surface, entity_key, type)`` triples (entities and their aliases)."""
        gaz = cls()
        for surface, key, entity_type in names:
            gaz.add(surface, key, entity_type)
        gaz.drop_ambiguous()
        return gaz

    def drop_ambiguous(self) -> int:
        """Remove names that point at two different entities ("Atlas Labs" for both "Atlas Labs
        GmbH" and "Atlas Labs Inc"): such a mention cannot be attributed. Returns the count."""
        dropped = 0
        for first, entries in list(self._first.items()):
            refs: dict[tuple[str, ...], set[tuple[str, str]]] = {}
            for e in entries:
                refs.setdefault(e.folds, set()).add((e.type, e.key))
            keep = [e for e in entries if len(refs[e.folds]) == 1]
            dropped += len(entries) - len(keep)
            if keep:
                keep.sort(key=lambda e: -len(e.folds))
                self._first[first] = keep
            else:
                del self._first[first]
        self._size -= dropped
        return dropped

    def add(self, surface: str, key: str, entity_type: str) -> None:
        orig = tuple(TOKEN.findall(surface))
        if not orig or not key or (len(orig) == 1 and len(orig[0]) < 2) or orig[0].isdigit():
            return
        self._add(orig, key, entity_type)
        if (
            entity_type == "org"
            and len(orig) > 1
            and orig[-1].lower().rstrip(".") in ORG_LEGAL_SUFFIXES
        ):
            short = orig[:-1]
            if len(short) > 1 or (len(short[0]) >= 4 and short[0].lower() not in COMMON_WORDS):
                self._add(short, key, entity_type)

    def _add(self, orig: tuple[str, ...], key: str, entity_type: str) -> None:
        if len(orig) > 1:
            mode = "fold"
        elif len(orig[0]) < 4 or orig[0].isupper():
            mode = "exact"
        else:
            mode = "cap"
        folds = tuple(t.lower() for t in orig)
        entries = self._first.setdefault(folds[0], [])
        entry = _Entry(folds, orig, key, entity_type, mode)
        if entry not in entries:
            entries.append(entry)
            entries.sort(key=lambda e: -len(e.folds))
            self._size += 1

    def __len__(self) -> int:
        return self._size

    def match(self, tk: Tokens, i: int) -> _Entry | None:
        """The longest entry starting at token ``i`` (``None`` when there is none)."""
        entries = self._first.get(tk.folds[i])
        if not entries:
            return None
        n_tok = len(tk.toks)
        for e in entries:
            n = len(e.folds)
            if i + n > n_tok:
                continue
            if e.mode == "exact":
                if tk.toks[i] != e.orig[0]:
                    continue
            elif e.mode == "cap" and not tk.toks[i][0].isupper():
                continue
            ok = True
            for j in range(1, n):
                if tk.folds[i + j] != e.folds[j] or not tk.flags[i + j] & JOIN:
                    ok = False
                    break
            if ok:
                return e
        return None
