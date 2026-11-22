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

"""Token budgeting counts each text once: same pieces, far fewer counter calls."""

from __future__ import annotations

import random
import re

from nexus_processing.chunk_store import prepare_chunks
from nexus_processing.token_budget import estimate_tokens, fit_text

WORDS = [
    "Neither",
    "party",
    "is",
    "liable",
    "for",
    "delays.",
    "Invoices",
    "are",
    "payable",
    "within",
    "thirty",
    "days",
    "2026-11-01",
    "INV-004512",
    "$1,234.50",
    "réseau",
    "naïve",
    "東京",
    "مرحبا",
    "नमस्ते",
    "supercalifragilistic",
    "|",
    ";",
    ",",
    "x",
]


def _reference_estimate(text: str) -> int:
    """The 3.2.0 word-walking estimate the regex version must reproduce exactly."""
    total = 0
    for match in re.finditer(r"[A-Za-z]+|\d+|[^\sA-Za-z\d]", text or ""):
        piece = match.group(0)
        if piece[0].isdigit():
            total += -(-len(piece) // 2)
        elif piece[0].isascii() and piece[0].isalpha():
            total += -(-len(piece) // 4)
        else:
            total += 1
    return -(-total * 6 // 5)


def _texts(n: int, seed: int = 3) -> list[str]:
    r = random.Random(seed)
    out = ["", " ", "²³ ① ٣ १२", "a" * 37, "9" * 41]
    for _ in range(n):
        paras = [" ".join(r.choice(WORDS) for _ in range(r.randint(1, 300))) for _ in range(3)]
        out.append("Section: A > B\n" + "\n\n".join(paras))
    return out


def test_estimate_tokens_is_unchanged():
    for text in _texts(150):
        assert estimate_tokens(text) == _reference_estimate(text)


class Counter:
    """A non-additive counter (its own class): joined pieces are always re-checked."""

    def __init__(self) -> None:
        self.calls = 0
        self.batches = 0

    def count(self, text: str) -> int:
        self.calls += 1
        return max(1, -(-len(text) // 3))

    def many(self, texts: list[str]) -> list[int]:
        self.batches += 1
        return [max(1, -(-len(t) // 3)) for t in texts]


def test_fit_text_known_count_and_batches_give_the_same_pieces():
    for text in _texts(40):
        plain = Counter()
        expected = fit_text(text, 120, plain.count)
        fast = Counter()
        got = fit_text(text, 120, fast.count, known=plain.count(text), count_many=fast.many)
        assert got == expected
        assert fast.calls <= plain.calls


def _rows(n: int) -> list[dict]:
    long = " ".join(random.Random(5).choice(WORDS) for _ in range(900))
    rows = [
        {
            "text": f"[Table: t | PK: {i}] id: {i} | amount: {i}.50",
            "metadata": {"record": {"id": i}},
        }
        for i in range(n)
    ]
    rows[3]["text"] += " | notes: " + long
    return rows


def test_prepare_chunks_output_is_unchanged_and_texts_are_counted_once():
    rows = _rows(60)
    single = Counter()
    expected = prepare_chunks(rows, max_tokens=120, count_tokens=single.count)
    batched = Counter()
    got = prepare_chunks(rows, max_tokens=120, count_tokens=batched.count, count_many=batched.many)
    assert got == expected
    assert batched.batches >= 1 and batched.calls < single.calls
    assert any(c["metadata"].get("parts") for c in got)  # the long row was split


def test_estimate_counter_needs_no_recheck_and_stays_within_budget():
    for text in _texts(30):
        for piece in fit_text(text, 64):
            assert estimate_tokens(piece) <= 64


class Additive:
    """An embedder-like object whose bound ``count_tokens`` declares additive counts."""

    additive_counts = True

    def __init__(self) -> None:
        self.calls = 0

    def count_tokens(self, text: str) -> int:
        self.calls += 1
        return len(text.split())


def test_additive_counter_skips_rechecks_with_identical_pieces():
    text = "\n\n".join(" ".join(["word"] * 9) for _ in range(60))
    additive = Additive()
    fast = fit_text(text, 50, additive.count_tokens)
    calls = additive.calls
    plain_calls = []

    def plain(t: str) -> int:
        plain_calls.append(1)
        return len(t.split())

    assert fit_text(text, 50, plain) == fast
    assert calls < len(plain_calls)
