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

"""Token-bounded chunks: nothing past the embedder's window, header on every piece."""

from __future__ import annotations

import json

from nexus import NexusClient

try:
    from nexus.processing.token_budget import estimate_tokens, fit_text, split_header
except (ImportError, ModuleNotFoundError):
    from nexus_processing.token_budget import estimate_tokens, fit_text, split_header


def test_embedding_info_exposes_the_token_window():
    info = NexusClient().embedding_info()
    assert info["window"] == 512 and info["max_tokens"] == 450


def test_count_tokens_uses_the_model_tokenizer_without_truncation():
    client = NexusClient()
    assert client.count_tokens("order 4155551234") == 6  # order 415 ##55 ##51 ##23 ##4
    assert client.count_tokens("word " * 2000) == 2000  # not capped at the 512 window


def test_header_detection():
    assert split_header("Section: A > B\nbody text") == ("Section: A > B", "\n", "body text")
    assert split_header("[Table: t | PK: 1] a: 1 | b: 2") == (
        "[Table: t | PK: 1]",
        " ",
        "a: 1 | b: 2",
    )
    assert split_header("plain text") == ("", "", "plain text")
    email = "[Email: m.eml | From: A <[EMAIL]> | Subject: Q3]\nbody"
    assert split_header(email)[0] == "[Email: m.eml | From: A <[EMAIL]> | Subject: Q3]"
    assert split_header('[Audio: a.mp3 | [00:00 - 00:58]] Transcript: "x"')[0].endswith("58]]")


def test_fit_text_repeats_header_and_loses_nothing():
    body = " | ".join(f"col{i}: value {i} renewal pipeline" for i in range(400))
    text = f"[Workbook: w.xlsx | Sheet: S | Row 2] {body}"
    pieces = fit_text(text, 120)
    assert len(pieces) > 1
    assert all(p.startswith("[Workbook: w.xlsx | Sheet: S | Row 2] ") for p in pieces)
    assert all(estimate_tokens(p) <= 120 for p in pieces)
    rebuilt = " | ".join(p.split("] ", 1)[1] for p in pieces)
    assert rebuilt == body


def test_estimate_is_an_upper_bound_of_the_real_tokenizer():
    client = NexusClient()
    samples = [
        "Quarterly revenue grew 12% across the northern region; churn fell.",
        "id: 4155551234 | amount: 9876543210.50 | ts: 2024-03-01T12:00:00Z",
        json.dumps({"customer": {"name": "Ana", "orders": [101, 102, 103]}}),
    ]
    assert all(estimate_tokens(s) >= client.count_tokens(s) for s in samples)


def test_no_processor_output_exceeds_the_window_and_sections_repeat():
    client = NexusClient()
    md = "# Policy\n\n## Refunds\n\n" + ("Refunds are issued within 30 days of purchase. " * 200)
    doc = client.process_document("m", "p.md", md)
    assert len(doc.chunks) > 1
    assert all(client.count_tokens(c.text) <= 450 for c in doc.chunks)
    assert all(c.text.startswith("Section: Policy > Refunds\n") for c in doc.chunks)

    wide = [{"id": i, **{f"metric_{k}": 123456.789 + k for k in range(120)}} for i in range(3)]
    doc = client.process_mysql_table("wide", wide)
    assert all(client.count_tokens(c.text) <= 450 for c in doc.chunks)
    assert sum(1 for c in doc.chunks if "record" in c.metadata) == 3
    assert {c.metadata["parts"] for c in doc.chunks} != {1}


def test_split_parts_are_numbered_and_point_to_their_parent():
    doc = NexusClient().process_document("t", "n.log", "renewal " * 3000)  # 1,000-word windows
    parts = [c for c in doc.chunks if "parent_chunk_id" in c.metadata]
    assert parts and [c.chunk_index for c in doc.chunks] == list(range(len(doc.chunks)))
    assert len({c.chunk_id for c in doc.chunks}) == len(doc.chunks)


def test_cap_can_be_lowered_or_turned_off():
    text = "renewal pipeline quarter " * 400
    small = NexusClient(chunk_max_tokens=100).process_document("t", "n.txt", text)
    off = NexusClient(chunk_max_tokens=0).process_document("t", "n.txt", text)
    assert all(NexusClient().count_tokens(c.text) <= 100 for c in small.chunks)
    assert len(off.chunks) < len(small.chunks)


def test_bge_tokenizer_counts_are_declared_additive_and_split_once():
    client = NexusClient()
    embedder = client.text_embedder
    assert getattr(embedder, "additive_counts", False) is True
    limiter = client.chunk_limiter
    text = "Section: Notes\n" + "\n\n".join(
        "Invoices are payable within thirty days of receipt. " * 12 for _ in range(12)
    )
    calls: list[int] = []

    def counting(t: str) -> int:  # a plain function: never trusted as additive
        calls.append(1)
        return embedder.count_tokens(t)

    expected = fit_text(text, limiter.max_tokens, counting)
    assert limiter.fit(text, embedder.count_tokens(text)) == expected
    assert all(embedder.count_tokens(p) <= limiter.max_tokens for p in expected)


def test_client_prepare_chunks_batches_token_counts(monkeypatch):
    client = NexusClient()
    limiter = client.chunk_limiter
    batches: list[int] = []
    original = limiter.count_many

    def count_many(texts):
        batches.append(len(texts))
        return original(texts)

    monkeypatch.setattr(limiter, "count_many", count_many)
    rows = [
        {"text": f"row {i} " + "detail " * 200, "metadata": {"record": {"id": i}}} for i in range(5)
    ]
    out = client.prepare_chunks(rows, title="Orders")
    assert batches and batches[0] == 5
    assert sum(1 for c in out if "record" in c["metadata"]) == 5
