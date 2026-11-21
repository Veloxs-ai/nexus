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
_WORDISH = re.compile(r"[A-Za-z]+|\d+|[^\sA-Za-z\d]")


def estimate_tokens(text: str) -> int:
    """Upper-bound WordPiece/BPE token estimate when no tokenizer is available.

    Letters: one token per 4 characters of a word (common words are one token);
    digits: one per 2 (number vocabularies split long runs); every other visible
    character (punctuation, non-Latin script) counts as one; plus a 20% margin for
    words a vocabulary splits further.
    """
    total = 0
    for match in _WORDISH.finditer(text or ""):
        piece = match.group(0)
        first = piece[0]
        if first.isdigit():
            total += -(-len(piece) // 2)
        elif first.isascii() and first.isalpha():
            total += -(-len(piece) // 4)
        else:
            total += 1
    return -(-total * 6 // 5)


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


def _split(text: str, budget: int, count: TokenCounter, level: int) -> list[str]:
    if count(text) <= budget:
        return [text]
    while level < len(_SEPARATORS) and not _SEPARATORS[level][0].search(text):
        level += 1
    if level >= len(_SEPARATORS):
        return _hard_split(text, budget, count)
    pattern, sep = _SEPARATORS[level]
    sep_cost = count(sep.strip()) if sep.strip() else 0
    pieces: list[str] = []
    current: list[str] = []
    used = 0

    def flush() -> None:
        nonlocal current, used
        if current:
            pieces.append(sep.join(current))
        current, used = [], 0

    for part in pattern.split(text):
        cost = count(part)
        if cost > budget:
            flush()
            pieces.extend(_split(part, budget, count, level + 1))
            continue
        extra = cost + (sep_cost if current else 0)
        if current and used + extra > budget:
            flush()
            extra = cost
        current.append(part)
        used += extra
    flush()
    # Token counts are not always additive across a joined boundary: re-check.
    checked: list[str] = []
    for piece in pieces:
        if count(piece) <= budget:
            checked.append(piece)
        else:
            checked.extend(_split(piece, budget, count, level + 1))
    return checked


def fit_text(
    text: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    count: TokenCounter | None = None,
) -> list[str]:
    """Return ``text`` as pieces of at most ``max_tokens`` tokens each.

    Text that already fits is returned unchanged as a single piece. Otherwise the
    context header is repeated on every piece and the body is split at the most
    natural boundary; joining the bodies back gives the original body (no loss).
    """
    count = count or estimate_tokens
    if not text or len(text) <= max_tokens or count(text) <= max_tokens:
        return [text]
    header, sep, body = split_header(text)
    budget = max_tokens - (count(header) + 1 if header else 0)
    if budget < max(16, max_tokens // 4):  # a header that eats the window is not repeated
        header, sep, body = "", "", text
        budget = max_tokens
    pieces = [p for p in _split(body, budget, count, 0) if p.strip()]
    return [f"{header}{sep}{p}" if header else p for p in pieces] or [text]
