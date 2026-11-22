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

"""Relations between the text mentions of one chunk: co-mentions and typed patterns.

``chunk_relations(tk, hits, config, acc, chunk_key)``:

* ``co_mentioned`` (symmetric) between the active entities of a sentence and, with
  ``relation_window`` 1 (the default), of the next sentence too: "Sydney Park joined
  Customer Success. Sydney previously worked at Dell." and key/value lines ("Account: Acme
  Ltd" / "Contact: Anjali Nair") link names one line or sentence apart;
* ``co_mentioned`` between the names of one key/value record of 2-10 lines ("Account: ...",
  "Contact: ...", "Location: ..."): the fields describe one thing;
* typed, directed relations read from the words between two consecutive mentions of a
  sentence, for example ``works_for`` ("X, CEO of Y", "X works at Y", "X joined Y",
  "X from Y"), ``acquired`` ("Y acquired Z", "Z was acquired by Y"), ``located_in`` ("X,
  based in P", "X (P)"), ``part_of`` ("X, a subsidiary of Y"), ``leads`` ("X leads Y"),
  ``reports_to``, ``makes`` ("Y's Z", "Y makes Z") and ``uses`` ("X moves to Z").

Both are linear in the number of mentions (the gap between two mentions is at most 60
characters and matched by one compiled pattern per relation).
"""

from __future__ import annotations

import re
from bisect import bisect_left
from itertools import pairwise
from operator import itemgetter
from typing import Any

from .graph_tokens import Tokens

__all__ = ["RELATION_PATTERNS", "chunk_relations"]


def _set(text: str) -> frozenset[str]:
    return frozenset(text.split())


_ROLE = (
    r"(?:[a-z&/-]+ ){0,3}(?:ceo|cfo|cto|coo|cio|ciso|cmo|cpo|founder|co-founder|cofounder|owner"
    r"|president|chair|chairman|chairwoman|chairperson|director|head|vp|svp|evp|manager|lead"
    r"|engineer|architect|analyst|consultant|partner|officer|counsel|secretary|employee"
    r"|developer|designer|scientist|specialist|executive|representative|rep|member)"
)
_ORGISH = ("org", "entity")
_ANY = ("org", "entity", "person", "product", "project", "place")
# (relation, source types, destination types, gap pattern, reversed)
RELATION_PATTERNS: tuple[tuple[str, tuple[str, ...], tuple[str, ...], str, bool], ...] = (
    (
        "works_for",
        ("person",),
        _ORGISH,
        rf", (?:the |a |an )?{_ROLE} (?:of|at|for|with) (?:the )?"
        r"|,? (?:who )?(?:works|worked|working|is working|has worked) (?:at|for|with) (?:the )?"
        r"|,? (?:has |had |recently )?(?:joined|joins|rejoined) (?:the )?"
        r"|,? (?:is |was )?(?:employed|hired) (?:by|at) (?:the )?"
        r"| (?:from|of|at) (?:the )?"
        r"|'s (?:colleague|employer|manager) at ",
        False,
    ),
    (
        "acquired",
        _ORGISH,
        _ORGISH,
        r",? (?:has |have |had |recently |will |plans to |agreed to |is to )?"
        r"(?:acquired?|acquires|bought|buys|purchased|took over|takes over|completed (?:the|its) "
        r"acquisition of) (?:the |its )?",
        False,
    ),
    (
        "acquired",
        _ORGISH,
        _ORGISH,
        r",? (?:was|were|has been|is being|is|will be) (?:acquired|bought|purchased|taken over) by"
        r" (?:the )?",
        True,
    ),
    (
        "merged_with",
        _ORGISH,
        _ORGISH,
        r",? (?:has |have )?(?:merged|merges|will merge) with ",
        False,
    ),
    (
        "part_of",
        _ORGISH,
        _ORGISH,
        r",? (?:is |was )?(?:a |an |the )?(?:wholly[- ]owned )?(?:subsidiary|unit|division|arm|part"
        r"|affiliate|business unit) of (?:the )?",
        False,
    ),
    (
        "located_in",
        _ANY,
        ("place",),
        r",? (?:(?:which|who) (?:is|are) )?(?:is |are |was )?(?:based|headquartered|located|"
        r"situated|registered|incorporated) (?:in|at|out of) (?:the )?"
        r"|(?:'s)? (?:office|offices|plant|factory|warehouse|campus|site|hub|branch|headquarters)"
        r" (?:in|at) "
        r"| \(",
        False,
    ),
    (
        "leads",
        ("person",),
        ("org", "project", "entity"),
        r",? (?:who )?(?:leads|led|heads|headed|runs|ran|manages|managed|will lead|will head|"
        r"is leading|is heading|is the head of|is head of|heads up) (?:the |our |their )?",
        False,
    ),
    (
        "reports_to",
        ("person",),
        ("person",),
        r",? (?:who )?(?:reports|reported|reporting|will report) (?:directly )?to "
        r"(?:[a-z]+ ){0,4}",
        False,
    ),
    (
        "makes",
        _ORGISH,
        ("product",),
        r"'s |’s | (?:makes|made|develops|developed|builds|built|launched|launches|released|"
        r"releases|sells|ships|owns|offers) (?:the |its |a |an )?",
        False,
    ),
    (
        "uses",
        ("org", "entity", "person"),
        ("product",),
        r",? (?:uses|used|is using|are using|adopted|adopts|runs on|moved to|moves to|"
        r"is moving to|migrated to|migrates to|will move to|switched to|deployed|licensed) "
        r"(?:the |its |our |their |a |an )?(?:[a-z]+ ){0,3}(?:to )?",
        False,
    ),
)
_BY_TYPES: dict[tuple[str, str], list[tuple[str, re.Pattern[str], bool]]] = {}
for _rel, _src, _dst, _gap, _rev in RELATION_PATTERNS:
    _pattern = re.compile(rf"(?:{_gap})")
    for _s in _src:
        for _d in _dst:  # keyed by (left type, right type) in text order
            _BY_TYPES.setdefault((_d, _s) if _rev else (_s, _d), []).append((_rel, _pattern, _rev))
_PRONOUNS = _set("""
they he she it its their his her them this these both
""")
_KINDS = _set("""
company group team firm bank business unit vendor supplier customer client project programme
program platform product tool app service startup organisation organization agency
department
""")
_MAX_GAP = 60
_START = itemgetter(3)
_PLAIN_GAPS = frozenset({", ", " and ", " or ", " & ", "/", " / ", " - ", " ", ",", "; ", " vs "})
_SPACE = re.compile(r"\s+")
_RECORD = re.compile(
    r"(?:^[ \t]*(?:[-*•][ \t]*)?[A-Z][^\n:]{0,40}:[ \t]*[^\s:][^\n]*(?:\n|\Z)){2,10}", re.M
)


def chunk_relations(tk: Tokens, hits: list, config: Any, acc: Any, chunk_key: str) -> None:
    """Add the chunk's co-mention and typed relations to ``acc`` (module doc)."""
    sentence = tk.sentence
    by_sent: dict[int, dict[tuple[str, str], None]] = {}
    ordered = []
    for h in hits:
        if h[1] != "concept":
            by_sent.setdefault(sentence[h[0]], {})[(h[1], h[2])] = None
            ordered.append(h)
    if len(ordered) < 2:
        return
    cap = config.max_entities_per_sentence
    co = acc.relations
    ranked = {sent: sorted(refs)[:cap] for sent, refs in by_sent.items()}
    get = co.get
    for mine in ranked.values():  # one sentence: a count per sentence
        for a in range(len(mine) - 1):
            t1, k1 = mine[a]
            for t2, k2 in mine[a + 1 :]:
                key = (t1, k1, t2, k2, chunk_key)
                co[key] = get(key, 0) + 1
    near: list[tuple[str, str, str, str, str]] = []  # next sentences, records: once a chunk
    window = config.relation_window
    if window and len(ranked) > 1:
        for sent, mine in ranked.items():
            for nxt in range(sent + 1, sent + 1 + window):
                if nxt not in ranked or not _continues(tk, nxt, by_sent[sent]):
                    break
                for other in ranked[nxt]:
                    for ref in mine:
                        if ref < other:
                            near.append((*ref, *other, chunk_key))
                        elif other < ref:
                            near.append((*other, *ref, chunk_key))
    text = tk.text
    if ":" in text and "\n" in text:
        _record_pairs(text, ordered, cap, near, chunk_key)
    for key in near:
        if key not in co:
            co[key] = 1
    _typed(tk, ordered, acc.typed, chunk_key)


def _continues(tk: Tokens, sent: int, before: dict[tuple[str, str], None]) -> bool:
    """Sentence ``sent`` goes on about the previous one: it is short (a field or a follow-up,
    at most 8 tokens), opens with a label ("Contact: ..."), a pronoun or a definite
    description ("They ...", "The company ..."), or repeats a word of a name before it."""
    sentence = tk.sentence
    lo = bisect_left(sentence, sent)
    hi = bisect_left(sentence, sent + 1, lo)
    if hi - lo <= 8:
        return True
    folds = tk.folds
    first = folds[lo]
    if first in _PRONOUNS or (first == "the" and lo + 1 < hi and folds[lo + 1] in _KINDS):
        return True
    if lo + 1 < hi and ":" in tk.text[tk.ends[lo] : tk.starts[lo + 1]]:
        return True
    words = {w for _t, key in before for w in key.split()}
    return any(folds[k] in words for k in range(lo, min(hi, lo + 4)) if tk.toks[k][0].isupper())


def _typed(tk: Tokens, ordered: list, typed: Any, chunk_key: str) -> None:
    ordered.sort(key=_START)
    sentence, text = tk.sentence, tk.text
    for left, right in pairwise(ordered):
        candidates = _BY_TYPES.get((left[1], right[1]))
        if (
            candidates is None
            or right[3] - left[4] > _MAX_GAP
            or sentence[left[0]] != sentence[right[0]]
        ):
            continue
        gap = text[left[4] : right[3]]
        if gap in _PLAIN_GAPS or "\n" in gap or left[2] == right[2]:
            continue
        gap = gap.lower()
        if "  " in gap or "\t" in gap:
            gap = _SPACE.sub(" ", gap)
        for rel, pattern, rev in candidates:
            if pattern.fullmatch(gap):
                a, b = (right, left) if rev else (left, right)
                typed[(a[1], a[2], b[1], b[2], rel, chunk_key)] += 1
                break


def _record_pairs(text: str, hits: list, cap: int, near: list, chunk_key: str) -> None:
    """Pairs of names inside each key/value record block of the chunk."""
    for m in _RECORD.finditer(text):
        lo, hi = m.span()
        refs = sorted({(h[1], h[2]) for h in hits if lo <= h[3] < hi})[:cap]
        for a in range(len(refs) - 1):
            for b in refs[a + 1 :]:
                near.append((*refs[a], *b, chunk_key))
