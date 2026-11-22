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

"""Capitalised spans, ids and abbreviations for the text extractor, and span typing.

``token_pass`` walks one chunk's tokens once: ids (``C-1014``), bare abbreviations defined in
the document, and capitalised runs with the precision filters of ``graph_text``; ``_span``
trims, splits ("Boston and Chicago", "Ravi Kumar of Acme Corp"), filters (common words,
roles, sentence-start tokens without evidence) and types a run. ``find_abbreviations`` reads
``Long Form (LF)`` and ``LF (Long Form)`` definitions.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .graph_lexicon import (
    ACRONYM_STOP,
    COMMON_WORDS,
    CONNECTORS,
    DEMONYMS,
    GENERIC_WORDS,
    HEADING_WORDS,
    HONORIFICS,
    MONTHS,
    OF_HEADS,
    ORG_HEAD_WORDS,
    ORG_LEGAL_SUFFIXES,
    ROLE_FIRST,
    ROLE_HEADS,
    SENTENCE_LEAD,
    SPAN_STOP,
    STOPWORDS,
    VERBS,
    WEEKDAYS,
    ambiguous_names,
    ambiguous_places,
    given_names,
    places,
    plain,
)
from .graph_resolve import normalise_name
from .graph_shapes import (
    HAS_DIGIT,
    NAME_DIGIT,
    NOT_RECORD_ID,
    POSSESSIVE,
    RECORD_ID,
    and_inside,
    camel_brand,
    numbered,
    of_head,
    owner_before_name,
    place_pair,
    place_parts,
    record_label,
    shaped,
)
from .graph_tokens import JOIN, START, Tokens
from .graph_typing import Pending, base_type, is_model_token, lexicon, span_votes

# Words a possessive may still run into ("St. Mary's Hospital", "Moody's Investors Service").
_OWNED_HEADS = (
    ORG_HEAD_WORDS
    | ORG_LEGAL_SUFFIXES
    | frozenset(
        {"hospital", "college", "church", "cathedral", "school", "investors", "corporation"}
    )
)

__all__ = ["find_abbreviations", "token_pass", "type_of_span"]

_LEAD_TRIM = STOPWORDS | HEADING_WORDS | SPAN_STOP | HONORIFICS
# Full month and weekday names split a capitalised run ("Acme on Monday"); short forms and
# months that are also given names ("May", "June") do not ("Blue Sun").
_SPLIT = frozenset(w for w in MONTHS | WEEKDAYS if len(w) > 3) - {"may", "june", "april", "august"}
_ROLE_WORDS = ROLE_HEADS | ROLE_FIRST | frozenset({"vp", "svp", "evp", "avp", "director"})
_ABBR_SKIP = frozenset({"of", "and", "the", "for", "&", "in", "on", "to", "a", "an"})
# Single capitalised words that are never a name on their own, and the plain words a
# multi-word title-case phrase may be made of.
_SINGLE_STOP = COMMON_WORDS | SPAN_STOP | ORG_LEGAL_SUFFIXES | DEMONYMS | GENERIC_WORDS
_PLAIN_WORDS = COMMON_WORDS | GENERIC_WORDS
_ROMAN = frozenset(["II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"])


def type_of_span(folds: Sequence[str], honorific: bool = False) -> str:
    """The entity type a capitalised span's own words suggest (lowercased tokens)."""
    return base_type(folds, honorific)[0]


def find_abbreviations(tk: Tokens, abbrs: dict[str, tuple[str, str, str]]) -> None:
    toks, folds, flags, n = tk.toks, tk.folds, tk.flags, len(tk)
    for i, tok in enumerate(toks):
        if not (2 <= len(tok) <= 8 and tok.isupper() and tok.isalpha()) or tok in abbrs:
            continue
        before = tk.gap_before(i).strip()
        after = tk.gap_before(i + 1).strip() if i + 1 < n else tk.text[tk.ends[i] :].strip()[:1]
        target = tok.lower()
        if before.endswith("(") and after.startswith(")"):
            lo = max(0, i - len(tok) - 3)
            for s in range(i - 1, lo - 1, -1):
                if s < i - 1 and not flags[s + 1] & JOIN:
                    break
                span = range(s, i)
                if toks[s][0].isupper() and _abbreviates(target, folds, span):
                    _define(tk, tok, s, i, abbrs)
                    break
        elif i + 1 < n and after == "(":
            for k in range(i + 1, min(n, i + len(tok) + 4)):
                tail = tk.gap_before(k + 1) if k + 1 < n else tk.text[tk.ends[k] :]
                if ")" in tail:
                    span = range(i + 1, k + 1)
                    if toks[i + 1][0].isupper() and _abbreviates(target, folds, span):
                        _define(tk, tok, span.start, span.stop, abbrs)
                    break
                if k > i + 1 and not flags[k] & JOIN:
                    break


def _initials(folds: list[str], span: range) -> str:
    return "".join(folds[k][0] for k in span if folds[k] not in _ABBR_SKIP)


def _abbreviates(abbr: str, folds: list[str], span: range) -> bool:
    """``abbr`` is the initials of the span's words, or (a Schwartz-Hearst style match) every
    content word gives its first letter and possibly more letters in order ("Hindustan
    Unilever" -> HUL, "Bharat Petroleum" -> BPCL is not: "c" and "l" are missing)."""
    if _initials(folds, span) == abbr:
        return True
    words = [folds[k] for k in span if folds[k] not in _ABBR_SKIP]
    return len(words) < len(abbr) and _letters(abbr, 0, words, 0)


def _letters(abbr: str, a: int, words: list[str], w: int) -> bool:
    if w == len(words):
        return a == len(abbr)
    word = words[w]
    if a >= len(abbr) or word[0] != abbr[a]:
        return False
    pos, take = 1, 0  # take 0, 1, 2 ... more letters of this word, in order
    while True:
        if _letters(abbr, a + 1 + take, words, w + 1):
            return True
        if a + 1 + take >= len(abbr):
            return False
        pos = word.find(abbr[a + 1 + take], pos) + 1
        if not pos:
            return False
        take += 1


def _define(tk: Tokens, abbr: str, s: int, e: int, abbrs: dict[str, tuple[str, str, str]]) -> None:
    folds = [tk.folds[k] for k in range(s, e)]
    if _is_role(folds):
        return
    etype = type_of_span(folds)
    long_form = tk.text[tk.starts[s] : tk.ends[e - 1]]
    key = normalise_name(long_form, entity_type=etype)
    if key:
        abbrs[abbr] = (etype, key, long_form)


def token_pass(
    tk: Tokens,
    config: Any,
    abbrs: dict[str, tuple[str, str, str]],
    mid_caps: set[str],
    lower_seen: set[str],
    covered: bytearray,
    hits: list,
    acc: Any,
    camel: set[int] | tuple[()] = (),
) -> None:
    """Ids, defined abbreviations and capitalised spans of one chunk. ``camel``: indices of
    lowercase-initial tokens with capitals ("iOS", "ideaForge"), found while the document's
    tokens are first read; they may start or continue a name when they look like a brand."""
    toks, folds, flags, starts, ends, blocked = (
        tk.toks,
        tk.folds,
        tk.flags,
        tk.starts,
        tk.ends,
        tk.blocked,
    )
    n = len(toks)
    text = tk.text
    if camel:
        camel = {i for i in camel if camel_brand(tk, i)}
    poss = "'s" in text or "’s" in text
    i = 0
    while i < n:
        if covered[i] or i in blocked:
            i += 1
            continue
        tok = toks[i]
        c = tok[0]
        if not c.isupper() and (not camel or i not in camel):
            i += 1
            continue
        if HAS_DIGIT(tok) and not NAME_DIGIT.match(tok):
            if config.ids and RECORD_ID.match(tok) and not NOT_RECORD_ID.match(tok):
                key = normalise_name(tok)
                acc.entity("record", key, tok)
                hits.append((i, "record", key, starts[i], ends[i], "id", 0.9))
                covered[i] = 1
            i += 1
            continue
        owner = tok[:-2] if poss and tok.endswith(POSSESSIVE) else tok  # "HUL's IT lead"
        if owner in abbrs and config.abbreviations:
            etype, key, _ = abbrs[owner]
            hits.append((i, etype, key, starts[i], starts[i] + len(owner), "abbrev", 0.9))
            covered[i] = 1
            # a long form directly before "(ABBR)" is a mention too
            i += 1
            continue
        if not config.capitalised:
            i += 1
            continue
        if "-" in tok and place_pair(tok):
            place_parts(tk, i, hits, covered)  # "Mumbai-Chennai link": two places
            i += 1
            continue
        j = i + 1
        while j < n and flags[j] & JOIN and not covered[j] and j not in blocked:
            if poss and toks[j - 1].endswith(POSSESSIVE) and folds[j] not in _OWNED_HEADS:
                break  # "HSBC's Global Banking": the possessive ends the name
            t = toks[j]
            if "-" in t and place_pair(t):
                break  # "The Mumbai-Chennai link": the places start their own spans
            if (
                (t[0].isupper() and (not HAS_DIGIT(t) or NAME_DIGIT.match(t)) and t not in abbrs)
                or (camel and j in camel)
            ) or (
                folds[j] in CONNECTORS
                and j + 1 < n
                and flags[j + 1] & JOIN
                and (
                    toks[j + 1][0].isupper()
                    or (folds[j + 1] in CONNECTORS and toks[j + 1][0].islower())  # "de la"
                )
                and not covered[j + 1]
                and not HAS_DIGIT(toks[j + 1])
            ):
                j += 1
            else:
                break
        # a short number ends a multi-word name ("Data Retention Policy 2", "Acme Corp 17"),
        # but not a year ("Annual Report 2025" keeps the report name)
        if j - i > 1 and folds[j - 1].rstrip(".") in ORG_LEGAL_SUFFIXES:
            pass  # "Orion Pharma Oy 5 ...": nothing follows a legal suffix
        elif (j - i > 1 and j < n and flags[j] & JOIN and not covered[j] and toks[j].isdigit()
                and len(toks[j]) <= 3 and (j + 1 >= n or not flags[j + 1] & JOIN)):  # fmt: skip
            j += 1
        elif (j < n and flags[j] & JOIN and not covered[j] and j not in blocked
              and is_model_token(toks[j])
              and folds[j - 1] not in lexicon().model_stop):  # fmt: skip
            j += 1  # a model number: "Zephyr X2", "Atlas 300", "Nimbus 12"
        _span(tk, i, j, config, abbrs, mid_caps, lower_seen, covered, hits, acc)
        i = j


def _span(
    tk: Tokens,
    i: int,
    j: int,
    config: Any,
    abbrs: dict,
    mid_caps: set[str],
    lower_seen: set[str],
    covered: bytearray,
    hits: list,
    acc: Any,
) -> None:
    folds, toks, flags = tk.folds, tk.toks, tk.flags
    n = len(toks)
    long_forms = {v[2].lower() for v in abbrs.values()} if abbrs else ()
    segments: list[list[int]] = [[]]
    for k in range(i, j):
        fold = folds[k]
        if fold == "and" and and_inside(tk, segments[-1], k, j):
            segments[-1].append(k)  # "Ministry of Electronics and Information Technology"
        elif (
            fold in _SPLIT
            or fold == "and"
            or (
                fold == "of"
                and k > i
                and folds[k - 1] not in ORG_HEAD_WORDS
                and folds[k - 1] not in OF_HEADS
            )
        ):
            segments.append([])  # "Boston and Chicago", "Ravi Kumar of Acme Corp": two names
        else:
            segments[-1].append(k)
    for seg in segments:
        honorific = False
        while (
            seg
            and (
                folds[seg[0]] in _LEAD_TRIM
                or (folds[seg[0]] in CONNECTORS and toks[seg[0]][0].islower())
            )
            and not _acronym(toks[seg[0]])
        ):
            honorific = honorific or folds[seg[0]] in HONORIFICS
            seg = seg[1:]
        while seg and (
            (((folds[seg[-1]] in CONNECTORS and toks[seg[-1]][0].islower())
              or folds[seg[-1]] in STOPWORDS)
             and not _acronym(toks[seg[-1]]))
            or (len(seg) > 1 and toks[seg[-1]] in ACRONYM_STOP  # "Chennai MPLS"
                and base_type([folds[k] for k in seg[:-1]])[0] in ("place", "person"))
        ):  # fmt: skip
            seg = seg[:-1]
        while (
            len(seg) > 1
            and flags[seg[0]] & START
            and (folds[seg[0]] in SENTENCE_LEAD or folds[seg[0]] in VERBS)
            and not _acronym(toks[seg[0]])
        ):
            seg = seg[1:]
        for p in range(len(seg) - 3, -1, -1) if len(seg) > 2 else ():
            # "CFO Daniel Abernathy", "Chief Technology Officer Alejandro Ruiz": the role is not
            # part of the name
            if folds[seg[p]] in ROLE_HEADS and plain(folds[seg[p + 1]]) in given_names():
                honorific = True
                seg = seg[p + 1 :]
                break
        if not seg or (len(seg) > config.max_span_tokens and (
                len(seg) > config.max_span_tokens + 3 or not of_head(folds, seg))):  # fmt: skip
            continue
        seg_folds = [folds[k] for k in seg]
        first = seg[0]
        if (first > 1 and folds[first - 1] == "of" and folds[first - 2] in _ROLE_WORDS
                and " ".join(seg_folds) in lexicon().departments):  # fmt: skip
            continue  # "Head of Procurement", "VP of Customer Success": a title, not a unit
        if len(seg) == 2 and toks[seg[1]] in _ROMAN and seg_folds[0] in lexicon().model_stop:
            continue  # "Type II", "Phase III", "Tier IV": a kind and a number
        k = seg[-1] + 1
        if k < n and flags[k] & JOIN and toks[k][0].isupper() and record_label(tk, seg, seg_folds):
            continue  # "Purchase Order PO-55102": the label of the record id after it
        if len(seg) == 1:
            tok, fold = toks[first], seg_folds[0]
            if _department(tk, first, tok, fold):
                pass  # "Legal will review", "approved by Finance", "HR will run"
            elif len(tok) < 2 or fold in _SINGLE_STOP:
                continue
            elif tok.isupper():
                if tok in ACRONYM_STOP or len(tok) > 6:
                    continue
            elif (fold in lower_seen and not honorific and not shaped(tok)) or (
                flags[first] & START
                and tok not in mid_caps
                and not honorific
                and not shaped(tok)
                and not owner_before_name(tk, first)
                and not (fold in lexicon().known and tk.gap_before(first).strip() == ":")
                and (
                    fold not in given_names()
                    or fold in ambiguous_names()
                    or fold in lexicon().known
                )
                and (fold not in places() or fold in ambiguous_places())
                and not _subject(tk, first)
            ):
                continue
        elif (
            _PLAIN_WORDS.issuperset(seg_folds)
            and " ".join(seg_folds) not in long_forms
            and " ".join(seg_folds) not in lexicon().departments
            and (
                flags[first] & START or (not numbered(tk, seg[-1]) and base_type(seg_folds)[1] == 0)
            )
        ):
            continue  # "Contract Term", "Status Update", "Economy Class", "Great Weekend"
        if _is_role(seg_folds):
            continue
        s, e = tk.starts[first], tk.ends[seg[-1]]
        surface = tk.text[s:e]
        if surface.endswith(("'s", "’s")):
            surface, e = surface[:-2], e - 2
        generic = normalise_name(surface)
        if not generic:
            continue
        votes, _ = span_votes(tk, seg, seg_folds, honorific)
        # typed per document by graph_typing.finalise_document
        pending = Pending(first, s, e, surface, votes, len(seg), generic)
        hits.append((first, "entity", "", s, e, "caps", 0.0, pending))
        for k in seg:
            covered[k] = 1


def _is_role(folds: Sequence[str]) -> bool:
    """A job title or role ("Chief Risk Officer", "Head of Sales", "Vice President")."""
    return folds[-1] in ROLE_HEADS or (len(folds) > 1 and folds[0] in ROLE_FIRST)


def _subject(tk: Tokens, i: int) -> bool:
    """A capitalised sentence-initial token followed by a verb ("Gringotts requested ...")."""
    if i + 1 >= len(tk) or not tk.flags[i + 1] & JOIN:
        return False
    nxt = tk.toks[i + 1]
    return nxt[0].islower() and (nxt in ("said", "says") or (nxt.endswith("ed") and len(nxt) > 4))


def _department(tk: Tokens, i: int, tok: str, fold: str) -> bool:
    """A one-word department name: mid-sentence, or opening a sentence before a verb."""
    if fold not in lexicon().departments or (fold == "it" and tok != "IT"):
        return False
    if i > 1 and tk.folds[i - 1] == "of" and tk.folds[i - 2] in _ROLE_WORDS:
        return False  # "Head of Sales", "VP of Finance"
    if not tk.flags[i] & START:
        return True
    nxt = i + 1
    return (nxt < len(tk) and bool(tk.flags[nxt] & JOIN)
            and tk.folds[nxt] in lexicon().subject_verbs)  # fmt: skip


def _acronym(tok: str) -> bool:
    return len(tok) > 1 and tok.isupper()
