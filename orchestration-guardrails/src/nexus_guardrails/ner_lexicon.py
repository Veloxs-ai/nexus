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
(``nexus.processing.graph_text``: honorifics, organisation suffixes and known organisations,
context cues). This module re-reads those spans for PII with the larger PII lexicons of
``ner_words`` (about 10,000 given names, 7,000 places, 4,000 surnames across cultures):

* role labels in front of a name are trimmed ("Customer Ravi Shankar" -> "Ravi Shankar");
* a given name followed by a surname is a person even where the graph's context vote said
  place or organisation ("hosted by Ritesh Arora"), unless the span's own words name an
  organisation ("Morgan Stanley");
* an unknown capitalised word followed by a known surname or surname ending is a person
  ("Tanvir Ahmed", "Jagdeep Singh Bains");
* a lone given name is a person mid-sentence, after a cue ("Ask Kriti") or before a person
  verb ("Riya said"); a lone surname before a person verb ("Sharma will call");
* a compass word plus a place is a location ("South India"); a capitalised name ending in a
  place head is a location ("Kempegowda International Airport", "Lajpat Nagar", "Marina
  Beach") and a street is not ("Baker Street"); a place before "Office"/"Branch" is one
  ("Dublin Office");
* an honorific ("Mr.", "Dr", "Smt.") or a person cue ("my name is", "this is", "reported by")
  followed by capitalised words marks a person;
* lowercase chat, key/value fields and signature blocks (``ner_rules``);
* vetoes: organisation tails ("Reddy's Laboratories"), person-named brands ("Jack Daniel's"),
  "&" inside a person, short all-caps words ("EMI"), nationalities and languages ("Spanish").

Without the processing layer installed (the guardrails layer used on its own) the graph pass
is skipped and the rules run on the PII lexicons alone.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache
from typing import Any

from . import ner_rules
from . import ner_words as W
from .ner_data import COMPASS, PERSON_CUES, PERSON_VERBS, ROLE_LABELS, SURNAME_ENDINGS

_words = W._words
_ROLES = _words(ROLE_LABELS)
_COMPASS = _words(COMPASS)
_VERB_AFTER = re.compile(r"[ \t]+([a-z]+)\b")
_PERSON_VERBS = _words(PERSON_VERBS)
_SOLO_AFTER = _PERSON_VERBS | _words("will would can could is was has had should")
_HONORIFICS = _words("mr mrs ms miss mx dr prof professor sir madam shri shree sri smt kumari")
_TOKEN = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*\.?")
_CUE = re.compile(
    r"(?i)\b(?:" + "|".join(re.escape(c) for c in sorted(PERSON_CUES, key=len, reverse=True))
    + r")\b[ \t,:]*(?:\n[ \t]*)?$"
)
_GRAPH_TYPES = {"person": "person", "place": "location", "entity": "", "org": ""}
_FACILITY = _words("office branch campus plant warehouse centre center hub depot factory clinic")
_PLACE_FIRST = _words("mount mt lake fort cape isle port")
_PLACE_SUFFIX = ("nagar", "abad", "puram", "halli", "palli", "garh", "ganj", "gaon", "wadi")
_PLACE_SUFFIX_CUED = ("pur", "pura", "kot", "pet", "peth", "patnam")
_PLACE_CUE = re.compile(r"(?i)\b(?:in|from|to|at|near|via|visiting|towards)[ \t]+$")
_WORD_BEFORE = re.compile(r"\b([A-Za-z]+)[ \t]+$")
_STRONG = _words("ask call email ping thank thanks hi hello hey dear cc attn tell kindly please")
_LEAD = _words("the a an visit visited at in near from to via our my your his her their")
_LEX = W


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
    return (graph_text.extract_mentions, config, graph_spans.type_of_span, lex, common, lex.VERBS)


def _given(fold: str, lex: Any = _LEX) -> bool:
    return fold in lex.given_names()


def _surname(fold: str) -> bool:
    return fold in W.surnames() or (len(fold) > 5 and fold.endswith(SURNAME_ENDINGS))


def _place(folds: list[str], lex: Any = _LEX, cued: bool = False) -> bool:
    if not folds:
        return False
    name = " ".join(folds)
    if name in lex.places():
        return cued or name not in lex.ambiguous_places()
    return len(folds) > 1 and folds[0] in _COMPASS and _place(folds[1:], lex, cued)


def _is_org(folds: list[str], g: Any) -> bool:
    return bool(folds) and (folds[-1] in W.ORG_TAILS or (g is not None and g[2](folds) == "org"))


def _person_strength(folds: list[str], g: Any) -> int:
    """2: given name + surname-like rest; 1: weaker evidence; 0: not a person by its words."""
    common = g[4] if g else frozenset()
    if not folds or len(folds) > 4 or any(f in _HONORIFICS for f in folds):
        return 0
    if g and g[2](folds) == "org":
        return 0
    rest = folds[1:]
    if _given(folds[0]):
        if not rest:
            return 1
        if len(rest) > 1 and not _surname(rest[-1]) and any(len(f) > 1 for f in rest[:-1]):
            return 0  # "Warren Buffett Letter Archive": a longer span needs a surname at its end
        weak = W.weak_surnames()
        if all(_surname(f) or f in weak or (f not in common and not _place([f])) for f in rest):
            return 2
        return 0
    if rest and folds[0] in W.surnames() and all(
        _given(f) or f in W.ambiguous_names() for f in rest
    ):  # surname first: "Nguyen Van An", "Park Min-jun"
        return 2 if not any(f in common or _place([f]) for f in rest) else 0
    if rest and (_surname(folds[-1]) or (len(rest) > 1 and any(_surname(f) for f in rest))):
        if any(f in common or f in _ROLES or _place([f]) for f in folds):
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
    common = g[4]
    if any(f in common or f in _ROLES for f in folds) or _place(folds, cued=True):
        return False
    return g[2](folds) in ("person", "entity")


def _solo_person(text: str, s: int, e: int, fold: str, cued: bool, g: Any) -> bool:
    """A lone given name (or surname before a verb) that reads as a person (module doc)."""
    common = g[4] if g else frozenset()
    if fold in common or fold in _ROLES or _place([fold], cued=True) or fold in W.NATIONALITIES:
        return False
    if text[max(0, s - 2) : s] == "& " or text[e : e + 2] == " &":
        return False  # half of a firm name ("Marks & Spencer")
    match = _VERB_AFTER.match(text, e)
    verb = bool(match and match.group(1) in _SOLO_AFTER)
    if not _given(fold):
        if cued and fold in W.ambiguous_names() and len(fold) > 2:
            return True  # "Ask Mark", "Thanks Grace": an ambiguous name right after a cue
        return fold in W.surnames() and (verb or cued) and len(fold) > 3
    if cued or verb or text[e : e + 1] == "," or text[e : e + 2] in ("'s", "’s"):
        return True
    before = text[max(0, s - 3) : s].rstrip(" \t\"'(")
    return bool(before) and before[-1] not in ".!?:\n"  # mid-sentence


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


def _place_heads(text: str, g: Any) -> tuple[list[tuple[int, int, str]], list[tuple[int, int]]]:
    """Location spans from place heads and the street runs that block every type."""
    common = g[4] if g else frozenset()
    spans, blocked = [], []
    for run in _runs(text):
        folds = [_fold(t[2]) for t in run]
        lead = 0
        while lead < len(run) - 1 and (folds[lead] in _LEAD or folds[lead] in _ROLES):
            lead += 1
        run, folds = run[lead:], folds[lead:]
        if len(run) < 2:
            continue
        last = folds[-1]
        if last in W.STREET_HEADS:
            blocked.append((run[0][0], run[-1][1]))
        elif last in _FACILITY:
            for k in range(len(run) - 1, 0, -1):
                if _place(folds[:k], cued=True):
                    spans.append((run[0][0], run[k - 1][1], "location"))
                    break
        elif (last in W.PLACE_HEADS or folds[0] in _PLACE_FIRST) and not any(
            f in W.ORG_TAILS or f in W.PLACE_HEAD_VETO or f in _HONORIFICS for f in folds
        ):
            core = folds[1:] if folds[0] in _PLACE_FIRST else folds[:-1]
            surname_head = last in W.surnames() or last in W.weak_surnames()
            if surname_head and _given(folds[-2]):
                continue  # "Min-jun Park", "Shirley Temple": a name, not a place
            if core and not all(f in common for f in core):
                spans.append((run[0][0], run[-1][1], "location"))
    return spans, blocked


def _refine(text: str, s: int, e: int, gtype: str, g: Any) -> tuple[int, int, str] | None:
    """A graph mention re-read for PII (see module doc)."""
    toks = _tokens(text, s, e)
    while len(toks) > 1 and (_fold(toks[0][2]) in _ROLES or _fold(toks[0][2]) in _HONORIFICS):
        toks = toks[1:]
    if not toks:
        return None
    s = toks[0][0]
    folds = [_fold(t[2]) for t in toks]
    strength = _person_strength(folds, g)
    if gtype == "person":
        return (s, e, "person")
    if gtype == "place":
        if strength and not _place(folds, cued=True) and folds[0] not in W.NATIONALITIES:
            return (s, e, "person")
        return (s, e, "location")
    if gtype == "entity":
        if _place(folds):
            return (s, e, "location")
        return (s, e, "person") if strength or _verb_person(text, e, folds, g) else None
    if g[2](text[s:e].casefold().split()) == "org":  # "Johnson & Johnson"
        return None
    if strength == 2:  # org by context only
        return (s, e, "person")
    return (s, e, "location") if _place(folds) else None  # "the Hosur account"


def _extra(text: str, g: Any, covered: bytearray) -> list[tuple[int, int, str]]:
    """Honorific, cue, lone-name, surname and place rules on runs the graph pass left."""
    out = []
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
        if any(covered[s:e]):
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
        place_cued = bool(_PLACE_CUE.search(text, max(0, s - 12), s))
        if _place(folds, cued=place_cued) and not (lead and len(folds) == 1 and _given(folds[0])):
            out.append((s, e, "location"))
            continue
        strength = _person_strength(folds, g)
        before = _WORD_BEFORE.search(text, max(0, s - 16), s)
        lead_word = _fold(run[lead - 1][2]) if lead else ""
        if not lead and before:
            lead_word = before.group(1).casefold()
        strong = cued or lead_word in _STRONG
        cue_person = (
            strong
            and len(folds) <= 3
            and not set(folds) & common
            and not _place(folds)
            and (not g or g[2](folds) != "org")
        )
        solo = len(folds) == 1
        if (
            strength == 2
            or cue_person
            or _verb_person(text, e, folds, g)
            or (solo and _solo_person(text, s, e, folds[0], strong, g))
        ):
            out.append((s, e, "person"))
        elif solo and _suffix_place(folds[0], place_cued, common):
            out.append((s, e, "location"))
    return out


def _suffix_place(f: str, cued: bool, common: frozenset[str]) -> bool:
    """An unknown word with a place-name ending ("Rajendranagar", "Secunderabad")."""
    if len(f) <= 6 or f in common or _given(f) or _surname(f):
        return False
    return f.endswith(_PLACE_SUFFIX) or (cued and f.endswith(_PLACE_SUFFIX_CUED))


_HONOR_BEFORE = re.compile(
    r"(?i)\b(?:mr|mrs|ms|miss|mx|dr|prof|professor|sir|madam|shri|shree|sri|smt|kumari)\.?[ \t]+$"
)
_ORG_NEXT = re.compile(r"(?:['’]s)?[ \t]+([A-Z][\w&]*)")


def _vetoed(text: str, s: int, e: int, entity: str) -> bool:
    """Spans that name an organisation, brand, nationality or acronym (module doc)."""
    surface = text[s:e]
    folds = [_fold(w) for w in surface.replace("’", "'").split()]
    if not folds:
        return True
    nxt = _ORG_NEXT.match(text, e)
    if nxt and nxt.group(1).casefold() in W.ORG_TAILS:
        return True
    if entity == "location":
        return " ".join(folds) in W.NATIONALITIES or folds[-1] in W.STREET_HEADS
    if folds[-1] in W.ORG_TAILS or "&" in surface or " and " in surface:
        return True
    if any(f in W.FESTIVALS for f in folds) or " ".join(folds) in W.FESTIVALS:
        return True
    key = "_".join(f.removesuffix("'s") for f in folds if f != "&")
    if key.replace("_", " ") in W.PERSON_BRANDS or key in W.PERSON_BRANDS:
        return True
    if len(folds) == 1 and surface.isupper() and len(surface) <= 4:
        return not _HONOR_BEFORE.search(text, max(0, s - 12), s)
    return len(folds) == 1 and (folds[0] in W.NATIONALITIES or folds[0] in W.GROUP_WORDS)


def lexicon_entities(text: str) -> list[tuple[int, int, str]]:
    """(start, end, "person"|"location") spans found by the lexicon rules (may overlap)."""
    g = _graph()
    common = g[4] if g else frozenset()
    heads, blocked = _place_heads(text, g)
    spans: list[tuple[int, int, str]] = list(heads)
    covered = bytearray(len(text))  # 1 where a span is already decided (linear checks)
    stop = bytearray(len(text))  # 1 inside a street name: no span may touch it
    for s, e in blocked:
        stop[s:e] = covered[s:e] = b"\1" * (e - s)
    for s, e, _ in heads:
        covered[s:e] = b"\1" * (e - s)
    if g is not None:
        for m in g[0]([("t", text)], config=g[1]).mentions:
            if any(covered[m.start : m.end]):
                continue
            refined = None
            if m.entity_type in _GRAPH_TYPES:
                refined = _refine(text, m.start, m.end, m.entity_type, g)
                if refined:
                    spans.append(refined)
            if refined or m.entity_type not in _GRAPH_TYPES or m.entity_type == "org":
                covered[m.start : m.end] = b"\1" * (m.end - m.start)
    spans.extend(_extra(text, g, covered))

    def is_org(folds: list[str]) -> bool:
        return _is_org(folds, g)

    low_common = common | (g[5] if g else frozenset())
    spans.extend(ner_rules.field_spans(text, common, is_org))
    spans.extend(ner_rules.signature_spans(text, common, is_org))
    spans.extend(ner_rules.lowercase_spans(text, low_common))
    return [
        (s, e, t)
        for s, e, t in spans
        if not any(stop[s:e]) and not _vetoed(text, s, e, t)
    ]
