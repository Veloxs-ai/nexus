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

"""Linear-time building blocks of PII detection (standard library only).

- :func:`email_matches` finds exactly what ``\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}\\b``
  finds with ``finditer``, anchored on each ``@``: the regex restarts at every word
  boundary of a long ``a-b-c-...`` run (quadratic time on base64url blobs, signed URLs and
  dash-separated numbers); the scan reads each character a bounded number of times.
- :func:`shadow` builds the detection view of a text (each character NFKC-normalised,
  invisible format characters removed) with one ``str.translate`` and maps shadow
  positions back to the original text through sparse breakpoints instead of a list of
  one int per character.
- :data:`MAYBE_PII` is a prefilter: ASCII text it does not match cannot hold a value of
  any built-in detector (each needs a digit, ``@`` or a secret prefix).
"""

from __future__ import annotations

import bisect
import re
import unicodedata
from collections.abc import Iterator
from functools import lru_cache

from .normalization import is_invisible

# ASCII text that this does not match holds no value of a built-in detector.
MAYBE_PII = re.compile(r"[0-9@]|eyJ|sk[-_]|AKIA|AIza|gh[pousr]_|xox[abprs]-")

_LOCAL = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._%+-")
_DOMAIN = re.compile(r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def _word(char: str) -> bool:
    """``re``'s ``\\w`` for one character of a ``str`` pattern."""
    return char.isalnum() or char == "_"


class TextMatch:
    """The parts of ``re.Match`` the detectors use, for a match found without ``re``."""

    __slots__ = ("_end", "_start", "string")

    def __init__(self, string: str, start: int, end: int) -> None:
        self.string, self._start, self._end = string, start, end

    def span(self, group: int = 0) -> tuple[int, int]:
        return self._start, self._end

    def start(self, group: int = 0) -> int:
        return self._start

    def end(self, group: int = 0) -> int:
        return self._end

    def group(self, group: int = 0) -> str:
        return self.string[self._start : self._end]


def email_matches(text: str) -> Iterator[TextMatch]:
    """The e-mail matches of ``text``, identical to the ``PATTERNS["email"]`` regex.

    The local part cannot contain ``@``, so a match through an ``@`` starts at the first
    word boundary of the run of local-part characters before it (and not before the end
    of the previous match), and its domain is the regex's domain match after the ``@``.
    """
    pos = 0
    at = text.find("@")
    while at != -1:
        start = at
        while start > pos and text[start - 1] in _LOCAL:
            start -= 1
        if start < at:
            domain = _DOMAIN.match(text, at + 1)
            if domain:
                for s in range(start, at):
                    if (s > 0 and _word(text[s - 1])) != _word(text[s]):
                        yield TextMatch(text, s, domain.end())
                        pos = domain.end()
                        break
        at = text.find("@", max(at + 1, pos))


class _Pieces(dict):
    """``ord(char)`` -> the char's detection piece: ``""`` when invisible, else its NFKC
    form. Filled on first sight; ``odd`` collects the characters whose piece is not
    exactly one character long (they shift positions)."""

    def __init__(self) -> None:
        super().__init__()
        self.odd: set[str] = set()

    def __missing__(self, code: int) -> str:
        char = chr(code)
        piece = "" if is_invisible(char) else unicodedata.normalize("NFKC", char)
        if len(piece) != 1:
            self.odd.add(char)
        self[code] = piece
        return piece


_PIECES = _Pieces()


@lru_cache(maxsize=32)
def _odd_pattern(odd: frozenset[str]) -> re.Pattern[str]:
    return re.compile("[" + "".join(re.escape(c) for c in sorted(odd)) + "]")


class Offsets:
    """Shadow index -> original index, stored only where the two drift apart."""

    __slots__ = ("_deltas", "_keys")

    def __init__(self, keys: list[int], deltas: list[int]) -> None:
        self._keys, self._deltas = keys, deltas

    def __getitem__(self, index: int) -> int:
        k = bisect.bisect_right(self._keys, index) - 1
        return index + (self._deltas[k] if k >= 0 else 0)


def shadow(text: str) -> tuple[str, Offsets | None]:
    """The detection view of ``text`` and, when positions moved, its map back to ``text``.

    Same result as normalising each character on its own and recording each piece's
    source index, at C speed: ``None`` means every shadow index is its original index.
    """
    if text.isascii():
        return text, None
    view = text.translate(_PIECES)
    if view == text or not _PIECES.odd:
        return view, None
    odd = _odd_pattern(frozenset(_PIECES.odd))
    keys: list[int] = []
    deltas: list[int] = []
    delta = 0  # original index - shadow index of the characters that follow
    for match in odd.finditer(text):
        i = match.start()
        piece = _PIECES[ord(text[i])]
        s = i - delta  # where this character's piece starts in the shadow
        for j in range(len(piece)):  # every char of a multi-char piece maps back to i
            keys.append(s + j)
            deltas.append(i - s - j)
        delta += 1 - len(piece)
        key = i + 1 - delta
        if keys and keys[-1] == key:
            deltas[-1] = delta
        else:
            keys.append(key)
            deltas.append(delta)
    if not keys:
        return view, None
    return view, Offsets(keys, deltas)
