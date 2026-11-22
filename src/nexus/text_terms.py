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

"""Words and numbers of a text, the way document routing, map-reduce and grounding compare them.

  terms(text)        content words: casefolded, accents removed from Latin letters, stopwords
                     dropped, a light suffix stem ("expires", "expired", "expiring" -> "expir");
                     a hyphenated word also gives its parts ("2027-03-05" -> "2027", "03", "05")
  question_terms     the terms of a question without the words every question has ("list",
                     "every", "how", "many", "documents" ...)
  numbers(text)      the numeric values in a text with their precision (``1,234.50`` -> 1234.5;
                     ``45k`` / ``1.2 million`` scaled), skipping identifiers and ISO dates
  key_tokens(text)   identifiers and dates (``C-1014``, ``P1``, ``2027-03-05``): words with a digit

Standard library only; every function is pure and fast enough to run per answer.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

__all__ = [
    "GENERIC_QUESTION_WORDS",
    "STOPWORDS",
    "Number",
    "key_tokens",
    "numbers",
    "query_words",
    "question_terms",
    "stem",
    "terms",
    "words",
]

_STOPWORD_TEXT = """
a about above after again against all also am an and any are as at be because been before being
below between both but by can could did do does doing down during each few for from further had has
have having he her here hers him his how i if in into is it its itself just me more most my no nor
not now of off on once only or other our ours out over own same she should so some such than that
the their theirs them then there these they this those through to too under until up very was we
were what when where which while who whom why will with would you your yours
"""
STOPWORDS = frozenset(_STOPWORD_TEXT.split())
# Words of the question's form, not its subject: they do not tell documents apart.
_GENERIC_TEXT = """
list lists listed show give tell find name names every each all any many much number count total
which what who whom whose how please document documents doc docs file files source sources
mention mentions mentioned mentioning everything anything something item items record records
one ones them there still currently ever exist exists existing available know
"""
GENERIC_QUESTION_WORDS = frozenset(_GENERIC_TEXT.split())
_WORD = re.compile(r"[\w\-\u0300-\u036f]+", re.UNICODE)
_SUFFIXES = ("ations", "ation", "ingly", "ings", "ing", "edly", "ies", "ied", "es", "ed", "s")
_GENERIC_STEMS: frozenset[str] = frozenset()  # filled below, after ``stem`` is defined


@lru_cache(maxsize=131072)
def _fold(word: str) -> str:
    word = word.casefold()
    if word.isascii():
        return word
    decomposed = unicodedata.normalize("NFKD", word)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


@lru_cache(maxsize=131072)
def stem(word: str) -> str:
    """A light suffix stem: enough to match "renews"/"renewal"? no; "expires"/"expired" yes.

    Words with a digit, short words and words ending in "ss" are kept as they are."""
    if len(word) <= 3 or any(ch.isdigit() for ch in word) or word.endswith("ss"):
        return word
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            base = word[: -len(suffix)]
            if suffix in ("ies", "ied"):
                base += "y"
            return base
    return word


_GENERIC_STEMS = frozenset(stem(w) for w in GENERIC_QUESTION_WORDS)


def words(text: str) -> list[str]:
    """Casefolded words of ``text`` in order (hyphenated words kept whole)."""
    return [_fold(w).strip("-_") for w in _WORD.findall(text or "") if w.strip("-_")]


def terms(text: str, keep_stopwords: bool = False) -> set[str]:
    """Content terms of ``text`` (stemmed; a hyphenated word adds its parts)."""
    out: set[str] = set()
    for word in words(text):
        if not keep_stopwords and word in STOPWORDS:
            continue
        out.add(stem(word))
        if "-" in word or "_" in word:
            for part in re.split(r"[-_]+", word):
                if part and (keep_stopwords or part not in STOPWORDS):
                    out.add(stem(part))
    return out


def question_terms(question: str) -> list[str]:
    """Distinct content terms of a question, in order, without its generic question words."""
    out: list[str] = []
    for word in words(question):
        if word in STOPWORDS or word in GENERIC_QUESTION_WORDS:
            continue
        term = stem(word)
        if term not in out and term not in _GENERIC_STEMS:
            out.append(term)
    return out


def query_words(question: str) -> str:
    """A keyword query for a full-text engine: the question's content words as written (not
    stemmed: the engine stems), without stopwords and generic question words."""
    out: list[str] = []
    for word in words(question):
        if word in STOPWORDS or word in GENERIC_QUESTION_WORDS or stem(word) in _GENERIC_STEMS:
            continue
        if word not in out:
            out.append(word)
    return " ".join(out)


_KEY = re.compile(
    r"(?<![\w-])(?!\d+(?:\.\d+)?(?:k|m|mn|bn|b|st|nd|rd|th)(?![\w-]))(?=[\w-]*\d)(?=[\w-]*[A-Za-z])"
    r"[A-Za-z0-9]+(?:[-_/][A-Za-z0-9]+)*(?![\w-])",
    re.I,
)
_TIME = re.compile(r"(?<![\w:])\d{1,2}:\d{2}(?::\d{2})?(?![\w:])")
_ISO_DATE = re.compile(r"(?<![\w-])\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?)?(?![\w-])")


def key_tokens(text: str) -> set[str]:
    """Identifiers and dates in ``text``, casefolded (``C-1014``, ``P1``, ``2027-03-05``)."""
    found: set[str] = set()
    for m in _KEY.finditer(text or ""):
        key = m.group(0).casefold()
        found.add(key)
        if "_" in key or "/" in key:  # "contract_C-1014" also holds "c-1014"
            found.update(p for p in re.split(r"[_/]+", key) if _KEY.fullmatch(p))
    found.update(m.group(0)[:10] for m in _ISO_DATE.finditer(text or ""))
    return found


@dataclass(frozen=True)
class Number:
    """A numeric value as written: ``value`` with ``tolerance`` from its precision and scale."""

    text: str
    value: float
    tolerance: float
    percent: bool = False
    money: bool = False
    year: bool = False

    @property
    def soft(self) -> bool:
        """A small whole number with no unit (a count, an ordinal, "3 customers"): often derived."""
        return (
            not self.percent and not self.money and self.tolerance <= 0.5 and 0 <= self.value <= 10
        )

    def matches(self, other: Number) -> bool:
        tol = max(self.tolerance, other.tolerance)
        return abs(self.value - other.value) <= tol + 1e-9


_SCALES = {
    "k": 1e3,
    "thousand": 1e3,
    "m": 1e6,
    "mn": 1e6,
    "million": 1e6,
    "b": 1e9,
    "bn": 1e9,
    "billion": 1e9,
    "lakh": 1e5,
    "lakhs": 1e5,
    "crore": 1e7,
    "crores": 1e7,
}
_NUMBER = re.compile(
    r"(?<![\w.\-/])(?P<cur>[$€£₹]\s?)?(?P<int>\d{1,3}(?:,\d{3})+|\d+)(?:\.(?P<dec>\d+))?"
    r"(?:\s?(?P<pct>%|percent\b)|\s?(?P<scale>k|mn|m|bn|b|thousand|million|billion|lakhs?|crores?)\b)?"
    r"(?![\w\-/]*\d)(?!-\w)",
    re.I,
)


def numbers(text: str) -> list[Number]:
    """Numeric values in ``text``. Identifiers (``C-1014``, ``P1``), ISO dates and times are not
    numbers here (``key_tokens`` has them); ``1,234.50`` -> 1234.5, ``45k`` -> 45,000 (± 500)."""
    masked = _ISO_DATE.sub(" ", text or "")
    masked = _TIME.sub(" ", _KEY.sub(" ", masked))
    out: list[Number] = []
    for m in _NUMBER.finditer(masked):
        digits = m.group("int").replace(",", "")
        dec = m.group("dec") or ""
        value = float(f"{digits}.{dec}" if dec else digits)
        scale = _SCALES.get((m.group("scale") or "").lower(), 1.0)
        tolerance = 0.5 * (10 ** -len(dec)) * scale
        whole = not dec and scale == 1.0
        out.append(
            Number(
                text=m.group(0).strip(),
                value=value * scale,
                tolerance=tolerance,
                percent=bool(m.group("pct")),
                money=bool(m.group("cur")),
                year=whole and len(digits) == 4 and 1900 <= value <= 2100,
            )
        )
    return out
