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

"""Shape and context tests for capitalised spans (used by ``graph_spans``).

Record ids and names with digits ("C-1014" vs "Log4j", "S/4HANA"), camel-case brands
("iOS", "ideaForge"), possessives ("HSBC's"), hyphenated place pairs ("Mumbai-Chennai"),
"<Ministry> of A and B" names, and labels before a record id ("Purchase Order PO-55102").
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from .graph_lexicon import (
    COMMON_WORDS,
    OF_HEADS,
    ORG_HEAD_WORDS,
    RECORD_KINDS,
    SECTORS,
    ambiguous_names,
    ambiguous_places,
    given_names,
    places,
    plain,
)
from .graph_resolve import normalise_name
from .graph_tokens import JOIN, Tokens
from .graph_typing import Pending, base_type, lexicon

__all__ = [
    "HAS_DIGIT",
    "NAME_DIGIT",
    "NOT_RECORD_ID",
    "POSSESSIVE",
    "RECORD_ID",
    "and_inside",
    "camel_brand",
    "numbered",
    "of_head",
    "owner_before_name",
    "place_pair",
    "place_parts",
    "possessive",
    "record_label",
    "shaped",
]

RECORD_ID = re.compile(r"^(?:[A-Z][A-Za-z0-9]*(?:[-_/][A-Za-z0-9]+)+|[A-Z]{2,}\d{3,})$")
NOT_RECORD_ID = re.compile(
    r"^(?:(?:FY|CY|Q[1-4]|H[12]|COVID|ISO|UTF|SHA|MD|TLS|SSL|IPV)[-_]?\d|(?:W|I)-\d{1,2}[A-Z]*$)"
)  # also tax and employment forms: W-9, W-8BEN, I-9
HAS_DIGIT = re.compile(r"\d").search
# A name token with a short number inside ("Log4j", "Neo4j", "S/4HANA"): not a record id.
NAME_DIGIT = re.compile(r"^(?:[A-Za-z]{2,}|[A-Z]/)\d{1,2}[A-Za-z]+[A-Za-z0-9]*$")
# A camel-case brand that starts lowercase ("iOS", "eBay", "iPhone", "ideaForge").
_CAMEL = re.compile(r"^([a-z]{1,5})[A-Z][A-Za-z]*$")
_CODE_AFTER = frozenset("([{=_.<")
POSSESSIVE = ("'s", "’s")


def camel_brand(tk: Tokens, i: int) -> bool:
    """A lowercase-initial camel-case brand, not a code identifier ("userId", "getUser()")."""
    tok = tk.toks[i]
    m = _CAMEL.match(tok)
    if not m or sum(c.isupper() for c in tok) > 2 or (m.end(1) > 2 and len(tok) - m.end(1) < 4):
        return False  # "userId": a long lowercase head needs a word-sized hump ("ideaForge")
    end = tk.ends[i]
    if tk.text[end : end + 1] in _CODE_AFTER and tk.text[end : end + 2] not in (". ", ".\n", "."):
        return False
    start = tk.starts[i]
    return not (start and tk.text[start - 1] in "._")


def possessive(tok: str) -> bool:
    return tok.endswith(POSSESSIVE) and len(tok) > 2


def place_pair(tok: str) -> bool:
    """A hyphenated run of known, unambiguous places that is not itself a place."""
    found = _PAIR_CACHE.get(tok)
    if found is None:
        parts = tok.split("-")
        known, amb = places(), ambiguous_places()
        found = (
            all(p[:1].isupper() and p.isalpha() for p in parts)
            and tok.lower() not in known
            and all(p.lower() in known and p.lower() not in amb for p in parts)
        )
        if len(_PAIR_CACHE) < 4096:
            _PAIR_CACHE[tok] = found
    return found


_PAIR_CACHE: dict[str, bool] = {}


def place_parts(tk: Tokens, i: int, hits: list, covered: bytearray) -> None:
    s = tk.starts[i]
    for part in tk.toks[i].split("-"):
        generic = normalise_name(part)
        pending = Pending(i, s, s + len(part), part, {"place": 3}, 1, generic)
        hits.append((i, "entity", "", s, s + len(part), "caps", 0.0, pending))
        s += len(part) + 1
    covered[i] = 1


def owner_before_name(tk: Tokens, i: int) -> bool:
    """A possessive before a capitalised name ("Safaricom's M-Pesa"): the owner is a name."""
    k = i + 1
    return (
        possessive(tk.toks[i])
        and k < len(tk)
        and bool(tk.flags[k] & JOIN)
        and (tk.toks[k][0].isupper())
    )


def shaped(tok: str) -> bool:
    """Inner capitals ("PagerDuty", "CERT-In", "iOS"): never an ordinary capitalised word."""
    rest = tok[1:]
    return rest != rest.lower() and not tok.isupper()


def numbered(tk: Tokens, last: int) -> bool:
    """A number right after the span ("Annual Report 2025"): a specific document or model."""
    k = last + 1
    return k < len(tk) and bool(tk.flags[k] & JOIN) and tk.toks[k][0].isdigit()


def of_head(folds: Sequence[str], seg: Sequence[int]) -> bool:
    return any(
        folds[k] == "of" and (folds[k - 1] in ORG_HEAD_WORDS or folds[k - 1] in OF_HEADS)
        for k in seg[1:]
    )


def and_inside(tk: Tokens, seg: Sequence[int], k: int, j: int) -> bool:
    """``and`` inside "<Ministry|Department|University> of A and B" (B: 1-3 plain words)."""
    folds = tk.folds
    if len(seg) < 3 or not of_head(folds, seg) or not 1 <= j - k - 1 <= 3:
        return False
    lex = lexicon()
    return all(
        (f := folds[m]) in SECTORS or f in COMMON_WORDS or f in lex.departments
        for m in range(k + 1, j)
    )


def record_label(tk: Tokens, seg: Sequence[int], folds: Sequence[str]) -> bool:
    """Words right before a record id that only name its kind ("Security Advisory SA-1")."""
    k = seg[-1] + 1
    if k >= len(tk) or not tk.flags[k] & JOIN or not tk.toks[k][0].isupper():
        return False
    tok = tk.toks[k]
    if not (
        HAS_DIGIT(tok)
        and RECORD_ID.match(tok)
        and not NOT_RECORD_ID.match(tok)
        and not NAME_DIGIT.match(tok)
    ):
        return False
    if folds[-1] in RECORD_KINDS:
        return True
    return base_type(folds)[1] == 0 and not any(
        plain(f) in given_names() and f not in ambiguous_names() for f in folds[:1]
    )
