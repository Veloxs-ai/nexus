# Copyright 2026 Veloxs AI Inc.
# SPDX-License-Identifier: Apache-2.0
"""Very large cells and documents: linear token counting and splitting, record and document
caps."""

from __future__ import annotations

import random

from nexus_processing import token_budget
from nexus_processing.chunk_store import prepare_chunks
from nexus_processing.record_caps import TRUNCATED_KEY, cap_document, cap_record_values
from nexus_processing.token_budget import _TOKENISH, estimate_tokens, fit_text


def _text(rng: random.Random, words: int) -> str:
    vocab = [
        "alpha",
        "invoice",
        "x",
        "SO-1234",
        "12345678",
        "naïve",
        "٣٤",
        "€",
        "a|b",
        "...",
        "\t",
        "\x1c",
        "Ω",
    ]
    seps = [" ", " ", " ", ". ", ", ", "; ", "\n", "\n\n", " | ", "! "]
    return "".join(rng.choice(vocab) + rng.choice(seps) for _ in range(words))


def test_estimate_counts_like_the_regex():
    rng = random.Random(1)
    alphabet = "aZ09 .\t\n|-_\x1c\x0b€٣éxyzQ"
    for _ in range(5000):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randrange(0, 60)))
        assert estimate_tokens(text) == -(-len(_TOKENISH.findall(text)) * 6 // 5), text
    assert estimate_tokens("") == 0


def test_fit_text_fast_path_gives_the_generic_pieces():
    rng = random.Random(2)
    heads = ["", "[Table: t | Row 1] ", "Section: A > B\n", "| a | b |\n|---|---|\n"]
    generic = lambda s: estimate_tokens(s)  # noqa: E731 - not the built-in: the generic path
    for _ in range(150):
        text = rng.choice(heads) + _text(rng, rng.choice([5, 60, 600, 3000]))
        for budget in (16, 64, 450):
            fast = fit_text(text, budget)
            assert fast == fit_text(text, budget, generic)
            assert fast == fit_text(text, budget, known=estimate_tokens(text))
            assert "".join(fast).replace(" ", "") != "" or not text.strip()


def test_fit_text_counts_each_character_about_once(monkeypatch):
    rng = random.Random(3)
    body = " ".join(
        " ".join(rng.choice(["alpha", "beta", "gamma", "delta"]) for _ in range(14)) + "."
        for _ in range(20000)
    )
    text = "[Table: notes | PK: 1] id: 1 | status: open | body: " + body
    counted = []
    real = token_budget._raw_tokens
    monkeypatch.setattr(token_budget, "_raw_tokens", lambda s: counted.append(len(s)) or real(s))
    pieces = fit_text(text, 450)
    assert len(pieces) > 100 and sum(counted) < 1.2 * len(text)


def test_cap_record_values_marks_what_it_cut():
    record = {"id": 1, "body": "x" * 50, "nested": {"note": "y" * 30, "n": 5}, "tags": ["z" * 25]}
    capped = cap_record_values(record, 20)
    assert capped["body"] == "x" * 20 and capped["nested"]["note"] == "y" * 20
    assert capped["tags"] == ["z" * 20] and capped["id"] == 1
    assert capped[TRUNCATED_KEY] == {"body": 50, "nested.note": 30, "tags.0": 25}
    assert record["body"] == "x" * 50  # the caller's record is untouched
    small = {"id": 2, "body": "short"}
    assert cap_record_values(small, 20) is small
    again = cap_record_values({**capped, "more": "w" * 40}, 20)
    assert again[TRUNCATED_KEY] == {"body": 50, "nested.note": 30, "tags.0": 25, "more": 40}


def test_cap_document_and_prepare_chunks_bounds():
    chunks = [{"text": f"part {i} " + "t" * 90, "metadata": {"i": i}} for i in range(10)]
    kept, report = cap_document(chunks, 250)
    assert [len(c["text"]) for c in kept] == [97, 97, 56] and kept[-1]["metadata"]["truncated"]
    assert report == {"truncated": True, "chars": 970, "kept_chars": 250, "dropped_chunks": 7}
    assert cap_document(chunks, None)[0] is chunks
    info: dict = {}
    rows = [
        {"text": f"row {i}", "metadata": {"record": {"id": i, "body": "b" * 300}}} for i in range(3)
    ]
    out = prepare_chunks(rows, max_record_chars=100, max_document_chars=10, report=info)
    assert len(out) == 2 and info["truncated"] and info["capped_records"] == 2
    assert out[0]["metadata"]["record"]["body"] == "b" * 100
    assert rows[0]["metadata"]["record"]["body"] == "b" * 300


def test_prepare_chunks_long_text_counted_inside_fit_text():
    rng = random.Random(4)
    text = "[Doc] " + _text(rng, 9000)
    assert len(text) > 16384
    chunk = [{"text": text, "metadata": {"record": {"id": 1}}}]
    generic = lambda s: estimate_tokens(s)  # noqa: E731
    fast, slow = prepare_chunks(chunk), prepare_chunks(chunk, count_tokens=generic)
    assert [c["text"] for c in fast] == [c["text"] for c in slow]
    assert fast[0]["metadata"]["record"] == {"id": 1} and "record" not in fast[1]["metadata"]
