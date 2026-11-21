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

"""Query-time inference does not queue behind ingestion."""

from __future__ import annotations

import threading
import time

try:
    from nexus.retrieval import semantic
except (ImportError, ModuleNotFoundError):
    from nexus_retrieval import semantic

PASSAGES = [
    f"Customer {i} in city {i % 50} renewed the gold plan for another year. " * 14
    for i in range(160)
]


def _query_latencies_during(embedder, passages: list[str]) -> tuple[list[float], float]:
    done = threading.Event()
    spent: list[float] = []

    def ingest() -> None:
        start = time.perf_counter()
        embedder.embed_batch(passages)
        spent.append(time.perf_counter() - start)
        done.set()

    worker = threading.Thread(target=ingest)
    worker.start()
    time.sleep(0.3)
    latencies: list[float] = []
    while not done.is_set():
        start = time.perf_counter()
        embedder.embed_query("what is the total balance in city 7?")
        latencies.append(time.perf_counter() - start)
        time.sleep(0.05)
    worker.join()
    return latencies, spent[0]


def test_embed_query_does_not_wait_for_a_running_batch():
    embedder = semantic.create_text_embedder()
    assert embedder.separate_query_model and embedder._query_lock is not embedder._passage_lock
    latencies, ingest_seconds = _query_latencies_during(embedder, PASSAGES)
    latencies.sort()
    assert latencies, "the batch finished before any query ran"
    # Before: one process-wide lock held for the whole batch, so a query waited for all of it.
    assert latencies[-1] < max(0.5, ingest_seconds / 4), (latencies[-1], ingest_seconds)


def test_shared_instance_waits_for_one_mini_batch_at_most():
    embedder = semantic.SemanticEmbedder(batch_size=8, separate_query_model=False)
    latencies, ingest_seconds = _query_latencies_during(embedder, PASSAGES)
    assert latencies and max(latencies) < ingest_seconds / 3, (max(latencies), ingest_seconds)


def test_length_sorted_batches_keep_input_order():
    embedder = semantic.create_text_embedder()
    texts = [
        "short note",
        "a much longer passage about quarterly renewal pipelines " * 6,
        "mid sized text here",
    ]
    batch = embedder.embed_batch(texts)
    single = [embedder.embed_batch([t])[0] for t in texts]
    for a, b in zip(batch, single, strict=True):
        assert sum(x * y for x, y in zip(a, b, strict=True)) > 0.999


def test_reranker_scores_large_pools_in_mini_batches_in_order():
    reranker = semantic.create_reranker()
    passages = [f"irrelevant filler text number {i}" for i in range(70)]
    passages[45] = "Employees receive 20 days of paid vacation per year."
    scores = reranker.score("how many vacation days do employees get", passages)
    assert len(scores) == 70 and max(range(70), key=scores.__getitem__) == 45
