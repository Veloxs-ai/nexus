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

"""Lexicon person/location detector (standard library only, no model download).

Capitalised spans and their first typing come from the knowledge-graph text extractor
(``nexus.processing.graph_text``: given-name and place lexicons, honorifics, organisation
suffixes and known organisations, context cues). This module re-reads those spans for PII:

* role labels in front of a name are trimmed ("Customer Ravi Shankar" -> "Ravi Shankar");
* a given name followed by a surname is a person even where the graph's context vote said
  place or organisation ("hosted by Ritesh Arora"), unless the span's own words name an
  organisation ("Morgan Stanley");
* an unknown capitalised word followed by a known surname or surname ending is a person
  ("Tanvir Ahmed", "Kateryna Bondarenko");
* a compass word plus a place is a location ("South India");
* an honorific ("Mr.", "Dr", "Smt.") or a person cue ("my name is", "this is", "reported by")
  followed by capitalised words marks a person.

Without the processing layer installed (the guardrails layer used on its own) only the
honorific, cue and surname rules run.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache
from typing import Any

from .ner_data import (
    COMPASS,
    PERSON_CUES,
    PERSON_VERBS,
    ROLE_LABELS,
    SURNAME_ENDINGS,
    SURNAMES,
)


def _words(text: str) -> frozenset[str]:
    return frozenset(w.replace("_", " ") for w in text.split())


_SURNAMES = _words(SURNAMES)
_ROLES = _words(ROLE_LABELS)
_COMPASS = _words(COMPASS)
_VERB_AFTER = re.compile(r"[ \t]+([a-z]+)\b")
_PERSON_VERBS = _words(PERSON_VERBS)
_HONORIFICS = _words("mr mrs ms miss mx dr prof professor sir madam shri shree sri smt kumari")
_TOKEN = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*\.?")
_CUE = re.compile(
    r"(?i)\b(?:" + "|".join(re.escape(c) for c in sorted(PERSON_CUES, key=len, reverse=True))
    + r")\b[ \t,:]*(?:\n[ \t]*)?$"
)
_GRAPH_TYPES = {"person": "person", "place": "location", "entity": "", "org": ""}


@lru_cache(maxsize=1)
def _graph() -> Any:
    """The processing layer's graph modules, or ``None`` when it is not installed."""
    try:
        from ..processing import graph_lexicon, graph_spans, graph_text  # type: ignore
    except ImportError:
        try:
            from nexus_processing import graph_lexicon, graph_spans, graph_text  # type: ignore
        except ImportError:
            return None
    config = graph_text.TextGraphConfig(
        gazetteer=False, ids=False, abbreviations=False, noun_phrases=False, relations=False
    )
    lex = graph_lexicon
    common = lex.COMMON_WORDS | lex.SPAN_STOP
    return (graph_text.extract_mentions, config, graph_spans.type_of_span, lex, common)


def _given(fold: str, lex: Any) -> bool:
    return lex is not None and fold in lex.given_names() and fold not in lex.ambiguous_names()


def _surname(fold: str) -> bool:
    return fold in _SURNAMES or (len(fold) > 5 and fold.endswith(SURNAME_ENDINGS))


def _place(folds: list[str], lex: Any, cued: bool = False) -> bool:
    if lex is None or not folds:
        return False
    name = " ".join(folds)
    if name in lex.places():
        return cued or name not in lex.ambiguous_places()
    return len(folds) > 1 and folds[0] in _COMPASS and _place(folds[1:], lex, cued)


def _person_strength(folds: list[str], g: Any) -> int:
    """2: given name + surname-like rest; 1: weaker evidence; 0: not a person by its words."""
    lex, common = (g[3], g[4]) if g else (None, frozenset())
    if not folds or len(folds) > 4 or any(f in _HONORIFICS for f in folds):
        return 0
    if g and g[2](folds) == "org":
        return 0
    rest = folds[1:]
    if _given(folds[0], lex):
        if not rest:
            return 1
        if len(rest) > 1 and not _surname(rest[-1]) and any(len(f) > 1 for f in rest[:-1]):
            return 0  # "Warren Buffett Letter Archive": a longer span needs a surname at its end
        if all(_surname(f) or (f not in common and not _place([f], lex)) for f in rest):
            return 2
        return 0
    if rest and _surname(folds[-1]):
        if any(f in common or f in _ROLES or _place([f], lex) for f in folds[:-1]):
            return 0
        return 2
    return 0


def _verb_person(text: str, end: int, folds: list[str], g: Any) -> bool:
    """A 2-3 word capitalised name followed by a person verb ("Mateus Rocha visited")."""
    if not 2 <= len(folds) <= 3 or g is None:
        return False
    match = _VERB_AFTER.match(text, end)
    if not match or match.group(1) not in _PERSON_VERBS:
        return False
    lex, common = g[3], g[4]
    if any(f in common or f in _ROLES for f in folds) or _place(folds, lex, True):
        return False
    return g[2](folds) in ("person", "entity")


def _tokens(text: str, start: int, end: int) -> list[tuple[int, int, str]]:
    out = []
    for m in _TOKEN.finditer(text, start, end):
        s, e = m.span()
        if text[e - 1] == "." and e - s > 2:  # keep the dot of an initial ("J.") only
            e -= 1
        out.append((s, e, text[s:e]))
    return out


def _runs(text: str) -> Iterable[list[tuple[int, int, str]]]:
    """Runs of capitalised tokens separated by spaces/tabs only (an initial may end in '.')."""
    run: list[tuple[int, int, str]] = []
    for s, e, tok in _tokens(text, 0, len(text)):
        if tok[0].isupper():
            gap = text[run[-1][1] : s] if run else ""
            if run and gap.strip(" \t.") == "" and "\n" not in gap:
                prev = run[-1][2].rstrip(".")
                if "." not in gap or len(prev) == 1 or prev.casefold() in _HONORIFICS:
                    run.append((s, e, tok))
                    continue
            if run:
                yield run
            run = [(s, e, tok)]
        elif run:
            yield run
            run = []
    if run:
        yield run


def _fold(tok: str) -> str:
    return tok.rstrip(".").casefold()


def _refine(text: str, s: int, e: int, gtype: str, g: Any) -> tuple[int, int, str] | None:
    """A graph mention re-read for PII (see module doc)."""
    toks = _tokens(text, s, e)
    while len(toks) > 1 and (_fold(toks[0][2]) in _ROLES or _fold(toks[0][2]) in _HONORIFICS):
        toks = toks[1:]
    if not toks:
        return None
    s = toks[0][0]
    folds = [_fold(t[2]) for t in toks]
    lex = g[3]
    strength = _person_strength(folds, g)
    if gtype == "person":
        return (s, e, "person")
    if gtype == "place":
        return (s, e, "person") if strength == 2 and not _place(folds, lex) else (s, e, "location")
    if gtype == "entity":
        if _place(folds, lex):
            return (s, e, "location")
        return (s, e, "person") if strength or _verb_person(text, e, folds, g) else None
    if g[2](text[s:e].casefold().split()) == "org":  # "Johnson & Johnson"
        return None
    return (s, e, "person") if strength == 2 else None  # org by context only


def _extra(text: str, g: Any, covered: list[tuple[int, int]]) -> list[tuple[int, int, str]]:
    """Honorific, cue and surname rules on capitalised runs the graph pass did not type."""
    out = []
    lex = g[3] if g else None
    common = g[4] if g else frozenset()
    for run in _runs(text):
        lead = 0
        while lead < len(run) - 1 and _fold(run[lead][2]) in _ROLES:
            lead += 1
        honorific = False
        while lead < len(run) and _fold(run[lead][2]) in _HONORIFICS:
            lead, honorific = lead + 1, True
        toks = run[lead:]
        if not toks:
            continue
        s, e = toks[0][0], toks[-1][1]
        if any(s < ce and cs < e for cs, ce in covered):
            continue
        folds = [_fold(t[2]) for t in toks]
        if honorific or (lead == 0 and _HONOR_BEFORE.search(text, max(0, s - 12), s)):
            while folds and folds[-1] in common:
                folds.pop()
                toks.pop()
            if folds and len(folds) <= 4:
                out.append((s, toks[-1][1], "person"))
            continue
        cued = bool(_CUE.search(text, max(0, s - 24), s))
        strength = _person_strength(folds, g)
        cue_person = (
            cued
            and len(folds) <= 3
            and not set(folds) & common
            and not _place(folds, lex)
            and (not g or g[2](folds) != "org")
        )
        if strength == 2 or cue_person or _verb_person(text, e, folds, g):
            out.append((s, e, "person"))
    return out


_HONOR_BEFORE = re.compile(
    r"(?i)\b(?:mr|mrs|ms|miss|mx|dr|prof|professor|sir|madam|shri|shree|sri|smt|kumari)\.?[ \t]+$"
)


def lexicon_entities(text: str) -> list[tuple[int, int, str]]:
    """(start, end, "person"|"location") spans found by the lexicon rules (may overlap)."""
    g = _graph()
    spans: list[tuple[int, int, str]] = []
    covered: list[tuple[int, int]] = []
    if g is not None:
        for m in g[0]([("t", text)], config=g[1]).mentions:
            if m.entity_type not in _GRAPH_TYPES:
                covered.append((m.start, m.end))
                continue
            refined = _refine(text, m.start, m.end, m.entity_type, g)
            if refined:
                spans.append(refined)
                covered.append((m.start, m.end))
            elif m.entity_type == "org":
                covered.append((m.start, m.end))
    spans.extend(_extra(text, g, covered))
    return spans
