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

"""Token-bounded chunk splitting.

Embedding models read a fixed number of tokens (512 for ``bge-small-en-v1.5``) and
silently ignore the rest, so text past the window is invisible to dense search.
``fit_text`` splits a chunk that is over a token budget into pieces that each fit,
at the most natural boundary available (paragraph, line, `` | `` field separator,
sentence, word, then characters), and repeats the chunk's context header
(``Section: A > B``, ``Columns: ...``, ``[Workbook: f | Sheet: s | Row 4]``, ...) on
every piece so each piece stays self-describing. No text is dropped.

Token counts come from the caller (the embedder's own tokenizer through
``NexusClient``); ``estimate_tokens`` is a conservative fallback.
"""

from __future__ import annotations

import re
from collections.abc import Callable

__all__ = [
    "DEFAULT_MAX_TOKENS",
    "estimate_tokens",
    "fit_text",
    "split_header",
]

# 512-token embedders (bge-small) with headroom for special tokens and a short
# document-name prefix added at embedding time.
DEFAULT_MAX_TOKENS = 450

TokenCounter = Callable[[str], int]

_LINE_HEADERS = ("Section: ", "Columns: ")
# A leading "[...]" tag; one level of nested brackets is allowed ("From: A <[EMAIL]>").
_BRACKET_HEADER = re.compile(r"\[(?:[^\[\]\n]|\[[^\[\]\n]*\]){1,400}\]")
# Boundaries tried in order as (split pattern, joiner). Sentence and clause splits keep
# their punctuation on the left part, so joining the parts restores the text.
_SEPARATORS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\n\n"), "\n\n"),
    (re.compile(r"\n"), "\n"),
    (re.compile(r" \| "), " | "),
    (re.compile(r"(?<=[.!?]) "), " "),
    (re.compile(r"(?<=[;,]) "), " "),
    (re.compile(r" "), " "),
)
_TABLE_SEPARATOR = re.compile(r"^\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?$")
# One match per estimated token: a letter run costs one per 4 letters, a digit run one per
# 2 digits, any other visible character one. Same counts as walking whole words, in C.
_TOKENISH = re.compile(r"[A-Za-z]{1,4}|\d{1,2}|[^\sA-Za-z\d]")
CountMany = Callable[[list[str]], list[int]]


def estimate_tokens(text: str) -> int:
    """Upper-bound WordPiece/BPE token estimate when no tokenizer is available.

    Letters: one token per 4 characters of a word (common words are one token);
    digits: one per 2 (number vocabularies split long runs); every other visible
    character (punctuation, non-Latin script) counts as one; plus a 20% margin for
    words a vocabulary splits further. The estimate is subadditive over whitespace
    boundaries (the parts' estimates never sum to less than the whole's).
    """
    if not text:
        return 0
    return -(-len(_TOKENISH.findall(text)) * 6 // 5)


def _additive(count: TokenCounter) -> bool:
    """The counter never counts a whitespace-joined text above the sum of its parts:
    ``estimate_tokens``, or a bound method of a counter object that declares
    ``additive_counts`` (an embedder whose tokenizer splits words at whitespace first)."""
    if count is estimate_tokens:
        return True
    return getattr(getattr(count, "__self__", None), "additive_counts", False) is True


def _counts(texts: list[str], count: TokenCounter, count_many: CountMany | None) -> list[int]:
    if not texts:
        return []
    if count_many is not None and len(texts) > 1:
        return list(count_many(texts))
    return [count(t) for t in texts]


def _table_header(text: str) -> tuple[str, str] | None:
    """``(header row + separator row, body)`` when ``text`` starts with a Markdown pipe table."""
    first, newline, rest = text.partition("\n")
    if not newline or not first.lstrip().startswith("|"):
        return None
    second, newline, body = rest.partition("\n")
    if newline and body.strip() and _TABLE_SEPARATOR.match(second.strip()):
        return f"{first}\n{second}", body
    return None


def split_header(text: str) -> tuple[str, str, str]:
    """Split ``text`` into ``(header, separator, body)``; header is "" when there is none.

    Recognised headers: a first line starting with ``Section: `` or ``Columns: ``, a
    Markdown table's header and separator rows (after such a line, or at the start), or a
    leading ``[...]`` context tag (followed by a space or a newline). A table header makes
    every split part of a table readable: each part repeats the column names.
    """
    first, newline, rest = text.partition("\n")
    if newline and rest.strip() and first.startswith(_LINE_HEADERS):
        table = _table_header(rest)
        if table is not None:
            return f"{first}\n{table[0]}", "\n", table[1]
        return first, "\n", rest
    table = _table_header(text)
    if table is not None:
        return table[0], "\n", table[1]
    match = _BRACKET_HEADER.match(text)
    if match and match.end() < len(text):
        body = text[match.end() :]
        if body.startswith("\n"):
            return match.group(0), "\n", body[1:]
        if body.startswith(" "):
            return match.group(0), " ", body.lstrip(" ")
    return "", "", text


def _hard_split(text: str, budget: int, count: TokenCounter) -> list[str]:
    """Character split for text with no usable boundary (a long token, base64, ...)."""
    pieces: list[str] = []
    pos = 0
    step = max(1, budget * 2)
    while pos < len(text):
        end = min(len(text), pos + step)
        while end - pos > 1 and count(text[pos:end]) > budget:
            end = pos + max(1, (end - pos) // 2)
        pieces.append(text[pos:end])
        pos = end
    return pieces


def _split(
    text: str,
    budget: int,
    count: TokenCounter,
    level: int,
    known: int | None = None,
    count_many: CountMany | None = None,
) -> list[str]:
    cost = count(text) if known is None else known
    if cost <= budget:
        return [text]
    while level < len(_SEPARATORS) and not _SEPARATORS[level][0].search(text):
        level += 1
    if level >= len(_SEPARATORS):
        return _hard_split(text, budget, count)
    pattern, sep = _SEPARATORS[level]
    sep_cost = count(sep.strip()) if sep.strip() else 0
    parts = pattern.split(text)
    costs = _counts(parts, count, count_many)
    # (text, verified): a piece of one part, or a piece from a deeper split, is known to fit.
    pieces: list[tuple[str, bool]] = []
    current: list[str] = []
    used = 0

    def flush() -> None:
        nonlocal current, used
        if current:
            pieces.append((sep.join(current), len(current) == 1))
        current, used = [], 0

    for part, part_cost in zip(parts, costs, strict=True):
        if part_cost > budget:
            flush()
            deeper = _split(part, budget, count, level + 1, part_cost, count_many)
            pieces.extend((p, True) for p in deeper)
            continue
        extra = part_cost + (sep_cost if current else 0)
        if current and used + extra > budget:
            flush()
            extra = part_cost
        current.append(part)
        used += extra
    flush()
    # Token counts are not always additive across a joined boundary: re-check joined
    # pieces, unless the counter is (sub)additive (the sum of the parts then bounds the whole).
    if _additive(count):
        return [p for p, _ in pieces]
    unverified = [p for p, ok in pieces if not ok]
    rechecked = iter(_counts(unverified, count, count_many))
    checked: list[str] = []
    for piece, ok in pieces:
        if ok:
            checked.append(piece)
            continue
        piece_cost = next(rechecked)
        if piece_cost <= budget:
            checked.append(piece)
        else:
            checked.extend(_split(piece, budget, count, level + 1, piece_cost, count_many))
    return checked


def fit_text(
    text: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    count: TokenCounter | None = None,
    *,
    known: int | None = None,
    count_many: CountMany | None = None,
) -> list[str]:
    """Return ``text`` as pieces of at most ``max_tokens`` tokens each.

    Text that already fits is returned unchanged as a single piece. Otherwise the
    context header is repeated on every piece and the body is split at the most
    natural boundary; joining the bodies back gives the original body (no loss).

    ``known`` is ``count(text)`` when the caller already has it, and ``count_many`` a
    batched form of ``count`` (one tokenizer call for many texts); both only save work.
    """
    count = count or estimate_tokens
    if not text or len(text) <= max_tokens:
        return [text]
    total = count(text) if known is None else known
    if total <= max_tokens:
        return [text]
    header, sep, body = split_header(text)
    budget = max_tokens - (count(header) + 1 if header else 0)
    body_cost: int | None = None
    if budget < max(16, max_tokens // 4):  # a header that eats the window is not repeated
        header, sep, body = "", "", text
        budget = max_tokens
        body_cost = total
    elif not header:
        body_cost = total
    pieces = [p for p in _split(body, budget, count, 0, body_cost, count_many) if p.strip()]
    return [f"{header}{sep}{p}" if header else p for p in pieces] or [text]
