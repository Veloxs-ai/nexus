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

import re
from collections.abc import Sequence
from typing import Any

from .graph_lexicon import (
    ACRONYM_STOP,
    COMMON_WORDS,
    CONNECTORS,
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
)
from .graph_resolve import normalise_name
from .graph_tokens import JOIN, START, Tokens
from .graph_typing import Pending, base_type, is_model_token, lexicon, span_votes

__all__ = ["find_abbreviations", "token_pass", "type_of_span"]

_ID = re.compile(r"^(?:[A-Z][A-Za-z0-9]*(?:[-_/][A-Za-z0-9]+)+|[A-Z]{2,}\d{3,})$")
_NOT_ID = re.compile(
    r"^(?:(?:FY|CY|Q[1-4]|H[12]|COVID|ISO|UTF|SHA|MD|TLS|SSL|IPV)[-_]?\d|(?:W|I)-\d{1,2}[A-Z]*$)"
)  # also tax and employment forms: W-9, W-8BEN, I-9
_HAS_DIGIT = re.compile(r"\d").search
_LEAD_TRIM = STOPWORDS | HEADING_WORDS | SPAN_STOP | HONORIFICS
# Full month and weekday names split a capitalised run ("Acme on Monday"); short forms and
# months that are also given names ("May", "June") do not ("Blue Sun").
_SPLIT = frozenset(w for w in MONTHS | WEEKDAYS if len(w) > 3) - {"may", "june", "april", "august"}
_ROLE_WORDS = ROLE_HEADS | ROLE_FIRST | frozenset({"vp", "svp", "evp", "avp", "director"})
_ABBR_SKIP = frozenset({"of", "and", "the", "for", "&", "in", "on", "to", "a", "an"})


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
                if _initials(folds, span) == target and toks[s][0].isupper():
                    _define(tk, tok, s, i, abbrs)
                    break
        elif i + 1 < n and after == "(":
            for k in range(i + 1, min(n, i + len(tok) + 4)):
                tail = tk.gap_before(k + 1) if k + 1 < n else tk.text[tk.ends[k] :]
                if ")" in tail:
                    span = range(i + 1, k + 1)
                    if _initials(folds, span) == target and toks[i + 1][0].isupper():
                        _define(tk, tok, span.start, span.stop, abbrs)
                    break
                if k > i + 1 and not flags[k] & JOIN:
                    break


def _initials(folds: list[str], span: range) -> str:
    return "".join(folds[k][0] for k in span if folds[k] not in _ABBR_SKIP)


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
) -> None:
    toks, folds, flags, starts, ends, blocked = (
        tk.toks,
        tk.folds,
        tk.flags,
        tk.starts,
        tk.ends,
        tk.blocked,
    )
    n = len(toks)
    i = 0
    while i < n:
        if covered[i] or i in blocked:
            i += 1
            continue
        tok = toks[i]
        c = tok[0]
        if not c.isupper():
            i += 1
            continue
        if _HAS_DIGIT(tok):
            if config.ids and _ID.match(tok) and not _NOT_ID.match(tok):
                key = normalise_name(tok)
                acc.entity("record", key, tok)
                hits.append((i, "record", key, starts[i], ends[i], "id", 0.9))
                covered[i] = 1
            i += 1
            continue
        if tok in abbrs and config.abbreviations:
            etype, key, _ = abbrs[tok]
            hits.append((i, etype, key, starts[i], ends[i], "abbrev", 0.9))
            covered[i] = 1
            # a long form directly before "(ABBR)" is a mention too
            i += 1
            continue
        if not config.capitalised:
            i += 1
            continue
        j = i + 1
        while j < n and flags[j] & JOIN and not covered[j] and j not in blocked:
            t = toks[j]
            if (t[0].isupper() and not _HAS_DIGIT(t) and t not in abbrs) or (
                folds[j] in CONNECTORS
                and j + 1 < n
                and flags[j + 1] & JOIN
                and toks[j + 1][0].isupper()
                and not covered[j + 1]
                and not _HAS_DIGIT(toks[j + 1])
            ):
                j += 1
            else:
                break
        # a short number ends a multi-word name ("Data Retention Policy 2", "Acme Corp 17"),
        # but not a year ("Annual Report 2025" keeps the report name)
        if (j - i > 1 and j < n and flags[j] & JOIN and not covered[j] and toks[j].isdigit()
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
    long_forms = {v[2].lower() for v in abbrs.values()} if abbrs else ()
    segments: list[list[int]] = [[]]
    for k in range(i, j):
        fold = folds[k]
        if (
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
            and (folds[seg[0]] in _LEAD_TRIM or folds[seg[0]] in CONNECTORS)
            and not _acronym(toks[seg[0]])
        ):
            honorific = honorific or folds[seg[0]] in HONORIFICS
            seg = seg[1:]
        while (
            seg
            and (folds[seg[-1]] in CONNECTORS or folds[seg[-1]] in STOPWORDS)
            and not _acronym(toks[seg[-1]])
        ):
            seg = seg[:-1]
        while (
            len(seg) > 1
            and flags[seg[0]] & START
            and (folds[seg[0]] in SENTENCE_LEAD or folds[seg[0]] in VERBS)
            and not _acronym(toks[seg[0]])
        ):
            seg = seg[1:]
        while len(seg) > 2 and folds[seg[0]] in ROLE_HEADS and folds[seg[1]] in given_names():
            # "CFO Daniel Abernathy", "Chair Eleanor Whitfield": the role is not part of the name
            honorific = True
            seg = seg[1:]
        if not seg or len(seg) > config.max_span_tokens:
            continue
        seg_folds = [folds[k] for k in seg]
        first = seg[0]
        if len(seg) == 1:
            tok, fold = toks[first], seg_folds[0]
            if _department(tk, first, tok, fold):
                pass  # "Legal will review", "approved by Finance", "HR will run"
            elif (
                len(tok) < 2
                or fold in COMMON_WORDS
                or fold in SPAN_STOP
                or fold in ORG_LEGAL_SUFFIXES
            ):
                continue
            elif tok.isupper():
                if tok in ACRONYM_STOP or len(tok) > 6:
                    continue
            elif (fold in lower_seen and not honorific) or (
                flags[first] & START
                and tok not in mid_caps
                and not honorific
                and (fold not in given_names() or fold in ambiguous_names())
                and (fold not in places() or fold in ambiguous_places())
                and not _subject(tk, first)
            ):
                continue
        elif (
            all(f in COMMON_WORDS for f in seg_folds)
            and " ".join(seg_folds) not in long_forms
            and " ".join(seg_folds) not in lexicon().departments
            and flags[first] & START
        ):
            continue  # "Contract Term", "Status Update" as headings or labels
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
