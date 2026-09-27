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

import math

import pytest

from nexus import NexusClient

try:
    from nexus.processing.chunking import chunk_csv, chunk_markdown, pack_rows
    from nexus.retrieval import semantic
except (ImportError, ModuleNotFoundError):
    from nexus_processing.chunking import chunk_csv, chunk_markdown, pack_rows
    from nexus_retrieval import semantic


def test_client_semantic_api_is_consistent():
    client = NexusClient()
    info = client.embedding_info()
    assert info["dimensions"] > 0 and info["model"]
    q = client.embed_query("how many vacation days")
    p = client.embed_texts(["employees get 20 days paid time off", "kubernetes autoscaling"])
    assert len(q) == info["dimensions"] and all(len(v) == info["dimensions"] for v in p)
    assert math.isclose(sum(x * x for x in q), 1.0, rel_tol=1e-3)


def test_semantic_embedder_understands_paraphrase():
    client = NexusClient()
    q = client.embed_query("How many vacation days do employees get?")
    good, bad = client.embed_texts(
        ["Full-time employees receive 20 days of paid time off per year.", "Kubernetes cluster auto-scaling."]
    )
    dot = lambda a, b: sum(x * y for x, y in zip(a, b))  # noqa: E731
    assert dot(q, good) > dot(q, bad) + 0.15


def test_processing_returns_chunks_without_vectors():
    client = NexusClient()
    doc = client.process_document("d1", "notes.md", "# Title\n\nSome body text. " * 20, file_type="md")
    assert doc.chunks and all(not hasattr(c, 'embedding') for c in doc.chunks)


def test_long_single_line_text_is_not_treated_as_path():
    client = NexusClient()
    doc = client.process_document("d2", "long.txt", "word " * 2000, file_type="txt")
    assert len(doc.chunks) > 1


def test_markdown_chunks_carry_heading_breadcrumbs():
    text = "# Handbook\n\nIntro.\n\n## PTO\n\n" + "Employees get 20 days. " * 80 + "\n\n## MFA\n\nMFA is mandatory."
    chunks = chunk_markdown(text, chunk_size=600)
    assert any(c.startswith("Section: Handbook > PTO") for c in chunks)
    assert any(c.startswith("Section: Handbook > MFA") for c in chunks)
    assert all(len(c) <= 700 for c in chunks)
    assert not any(c.split("\n", 1)[1].startswith("ays") for c in chunks)


def test_csv_rows_are_packed_with_header():
    csv_text = "id,amount\n" + "\n".join(f"{i},{i * 10}" for i in range(300))
    chunks = chunk_csv(csv_text, max_chars=800)
    assert 1 < len(chunks) < 300
    assert all(c.startswith("Columns: id, amount") for c in chunks)
    assert "[Row ID: 1]" in chunks[0]


def test_pack_rows_respects_budget():
    rows = [f"row {i} " + "x" * 50 for i in range(100)]
    packs = pack_rows(rows, header="H", max_chars=400)
    assert all(len(p) <= 400 for p in packs)
    assert sum(p.count("row ") for p in packs) == 100


def test_openai_embedder_batches_and_orders(monkeypatch):
    import json

    calls = []

    class FakeResp:
        def __init__(self, payload):
            self.payload = payload

        def read(self):
            return json.dumps(self.payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=0):
        body = json.loads(req.data)
        calls.append(body)
        data = [{"index": i, "embedding": [float(i)] * body["dimensions"]} for i in range(len(body["input"]))]
        return FakeResp({"data": list(reversed(data))})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    emb = semantic.OpenAIEmbedder(api_key="k", dimensions=384)
    vecs = emb.embed_batch([f"t{i}" for i in range(300)])
    assert len(vecs) == 300 and len(vecs[0]) == 384
    assert vecs[1][0] == 1.0  # re-ordered by index
    assert [len(c["input"]) for c in calls] == [256, 44] and calls[0]["dimensions"] == 384
    assert emb.model_name == "openai/text-embedding-3-small@384"


def test_legacy_apis_are_removed():
    client = NexusClient()
    for name in ("embed", "embed_image", "embed_audio", "embed_video_scene", "chunk_embeddings"):
        assert not hasattr(client, name)
    try:
        from nexus.processing import normalize_mysql_cdc_event  # noqa: F401
    except ImportError:
        pass
    else:  # pragma: no cover
        raise AssertionError("legacy CDC normalizer should be removed")
