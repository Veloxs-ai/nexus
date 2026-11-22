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

"""Top-k search paths give the same answers as a full sort, and index updates are exact."""

from __future__ import annotations

import math
import random
import threading
import time
from collections import Counter

import pytest

from nexus_retrieval import embeddings, lexical, semantic
from nexus_retrieval.config import RankingConfig
from nexus_retrieval.graph import KnowledgeGraph
from nexus_retrieval.lexical import LexicalIndex, query_terms
from nexus_retrieval.models import IndexedDocument, SearchResult, VectorEntry
from nexus_retrieval.ranking import combine_scores
from nexus_retrieval.vector_store import LocalVectorStore

WORDS = [
    "refund",
    "invoice",
    "policy",
    "dispute",
    "account",
    "billing",
    "card",
    "payment",
    "late",
    "fee",
    "window",
    "days",
]


def _cosine(a, b):
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb) if na and nb else 0.0


def test_vector_search_matches_full_cosine_sort():
    rng = random.Random(7)
    store = LocalVectorStore()
    vectors = [[rng.gauss(0, 1) for _ in range(48)] for _ in range(400)]
    for i, vec in enumerate(vectors):
        store.add(VectorEntry(id=f"v{i}", collection="c", text=f"t{i}", embedding=list(vec)))
    for _ in range(5):
        query = [rng.gauss(0, 1) for _ in range(48)]
        expected = sorted(
            ((f"v{i}", _cosine(query, v)) for i, v in enumerate(vectors)),
            key=lambda kv: kv[1],
            reverse=True,
        )[:20]
        got = store.search(query, 20)
        assert [r.id for r in got] == [k for k, _ in expected]
        assert max(abs(r.score - s) for r, (_, s) in zip(got, expected, strict=True)) < 1e-12
        assert all(r.semantic_score == r.score for r in got)


def test_vector_search_ties_keep_insertion_order_and_mismatched_dims_score_zero():
    store = LocalVectorStore()
    for i in range(5):
        store.add(VectorEntry(id=f"same{i}", collection="c", text="", embedding=[1.0, 0.0]))
    store.add(VectorEntry(id="short", collection="c", text="", embedding=[1.0]))
    out = store.search([2.0, 0.0], 10)
    assert [r.id for r in out] == ["same0", "same1", "same2", "same3", "same4", "short"]
    assert out[-1].score == 0.0
    assert store.search([0.0, 0.0], 3)[0].score == 0.0
    assert store.search([1.0, 0.0], 0) == []


def test_vector_store_readd_replaces_and_remove(tmp_path):
    store = LocalVectorStore("v.json", tmp_path, in_memory_only=False)
    store.add(VectorEntry(id="a", collection="c", text="old", embedding=[1.0, 0.0]))
    store.add(VectorEntry(id="b", collection="c", text="b", embedding=[0.0, 1.0]))
    store.add(VectorEntry(id="a", collection="c", text="new", embedding=[0.0, 3.0]))
    assert [e.id for e in store.entries] == ["a", "b"]
    top = store.search([0.0, 1.0], 5)
    assert [r.text for r in top] == ["new", "b"]
    store.save()
    loaded = LocalVectorStore("v.json", tmp_path, in_memory_only=False)
    loaded.load()
    assert [e.text for e in loaded.entries] == ["new", "b"]
    assert loaded.remove("a") and not loaded.remove("a")
    assert [r.id for r in loaded.search([0.0, 1.0], 5)] == ["b"]


def _head_share_order(index: LexicalIndex, query: str, limit: int) -> list[tuple[str, float]]:
    """The pre-3.2 full-sort ``share`` scoring, as the reference order."""
    terms = query_terms(query)
    total = len(index.documents)
    postings = {t: dict(index.postings.get(t, {})) for t in terms}
    idf = {t: math.log(1.0 + (total - len(d) + 0.5) / (len(d) + 0.5)) for t, d in postings.items()}
    weight = sum(idf.values()) or 1.0
    matched: dict[str, float] = {}
    counts: Counter[str] = Counter()
    for t, docs in postings.items():
        for doc_id, c in docs.items():
            matched[doc_id] = matched.get(doc_id, 0.0) + idf[t]
            counts[doc_id] += c
    rows = [(d, round(w / weight, 6)) for d, w in matched.items()]
    rows.sort(key=lambda r: (r[1], counts[r[0]]), reverse=True)
    return rows[:limit]


def _corpus(n: int, seed: int = 3) -> list[tuple[str, str]]:
    rng = random.Random(seed)
    return [
        (f"d{i}", " ".join(rng.choice(WORDS) for _ in range(rng.randint(3, 12)))) for i in range(n)
    ]


def test_lexical_share_top_k_matches_full_sort():
    index = LexicalIndex()
    for doc_id, text in _corpus(600):
        index.add(IndexedDocument(id=doc_id, collection="c", text=text))
    for query in ("refund policy", "late fee window", "card payment dispute days", "the billing"):
        got = [(r.id, r.lexical_score) for r in index.search(query, 25)]
        assert got == _head_share_order(index, query, 25)


def test_lexical_bm25_ties_keep_first_matched_order():
    index = LexicalIndex(scoring="bm25")
    for i in range(6):
        index.add(IndexedDocument(id=f"d{i}", collection="c", text="refund policy"))
    assert [r.id for r in index.search("refund", 4)] == ["d0", "d1", "d2", "d3"]


@pytest.mark.parametrize("scoring", ["share", "bm25"])
def test_lexical_readd_forgets_old_words(scoring):
    index = LexicalIndex(scoring=scoring)
    index.add(IndexedDocument(id="x", collection="c", text="obsolete pricing table"))
    index.add(IndexedDocument(id="y", collection="c", text="pricing for teams"))
    index.add(IndexedDocument(id="x", collection="c", text="new refund policy"))
    assert index.search("obsolete") == []
    assert [r.id for r in index.search("pricing")] == ["y"]
    assert [r.id for r in index.search("refund")] == ["x"]
    assert index.lengths == {"x": 3, "y": 3}
    assert index.remove("x") and not index.remove("x")
    assert index.search("refund") == [] and "refund" not in index.postings


def test_lexical_load_restores_lengths_without_retokenising(tmp_path, monkeypatch):
    index = LexicalIndex("lex.json", tmp_path, in_memory_only=False, scoring="bm25")
    for doc_id, text in _corpus(50):
        index.add(IndexedDocument(id=doc_id, collection="c", text=text))
    index.save()
    expected = [(r.id, r.score) for r in index.search("refund late fee", 10)]

    monkeypatch.setattr(lexical, "tokenize", lambda text: pytest.fail("load re-tokenised"))
    loaded = LexicalIndex("lex.json", tmp_path, in_memory_only=False, scoring="bm25")
    loaded.load()
    monkeypatch.undo()
    assert loaded.lengths == index.lengths
    assert [(r.id, r.score) for r in loaded.search("refund late fee", 10)] == expected
    # Indexes saved before 3.2 have no "lengths": they come from the postings.
    data = (tmp_path / "lex.json").read_text()
    import json

    payload = json.loads(data)
    payload.pop("lengths")
    (tmp_path / "lex.json").write_text(json.dumps(payload))
    old = LexicalIndex("lex.json", tmp_path, in_memory_only=False, scoring="bm25")
    old.load()
    assert old.lengths == index.lengths
    old.add(IndexedDocument(id="d0", collection="c", text="replacement words only"))
    assert "d0" not in {r.id for r in old.search(_corpus(50)[0][1], 50) if r.lexical_score == 1.0}


def _result(rid: str, score: float) -> SearchResult:
    return SearchResult(id=rid, collection="c", text="", score=score, semantic_score=score)


def test_rrf_ignores_an_all_zero_graph_ranking():
    sem = [_result("a", 0.9), _result("b", 0.8), _result("c", 0.7)]
    lex = [SearchResult(id="b", collection="c", text="", score=1.0, lexical_score=1.0)]
    zero = {"c": 0.0, "a": 0.0, "b": 0.0}
    out = combine_scores(sem, lex, zero, RankingConfig(fusion="rrf"), limit=3)
    assert [r.id for r in out] == ["b", "a", "c"]
    assert out[0].score == pytest.approx(1 / 62 + 1 / 61)
    assert out[1].score == pytest.approx(1 / 61)
    with_graph = combine_scores(
        sem, lex, {"c": 0.5, "a": 0.0}, RankingConfig(fusion="rrf"), limit=3
    )
    assert with_graph[-1].id == "a"
    assert {r.id: r.graph_score for r in with_graph}["c"] == 0.5


def test_graph_score_matches_whole_words_and_skips_stopwords():
    graph = KnowledgeGraph()
    graph.nodes["document:d"] = {"type": "document", "id": "d"}
    graph.nodes["parent:p"] = {"type": "parent", "id": "invoice-guide"}
    graph.nodes["tag:billing"] = {"type": "tag", "value": "billing"}
    graph.add_edge("document:d", "PART_OF", "parent:p")
    graph.add_edge("document:d", "TAGGED_AS", "tag:billing")
    assert graph.score("d", query_terms("is an parent document")) == 0.0
    assert graph.score("d", ["an", "the"]) == 0.0
    assert graph.score("d", ["bill"]) == 0.0  # no substring matches
    assert graph.score("d", query_terms("Billing question")) == 0.5
    assert graph.score("d", ["invoice"]) == 0.5


def test_fold_cache_gives_the_same_tokens():
    text = "Café naïve हिन्दी Привет 東京タワー Ärger"
    embeddings._fold.cache_clear()
    first = embeddings.tokenize(text)
    assert embeddings.tokenize(text) == first
    assert "cafe" in first and "naive" in first
    assert embeddings._fold.cache_info().hits > 0


def test_stable_sigmoid():
    assert semantic._sigmoid(-1000.0) == 0.0
    assert semantic._sigmoid(1000.0) == 1.0
    for x in (-30.0, -2.5, 0.0, 0.7, 12.0):
        assert semantic._sigmoid(x) == pytest.approx(1 / (1 + math.exp(-x)), rel=1e-12)


def test_onnx_and_tokenizer_thread_budget(monkeypatch):
    monkeypatch.delenv("NEXUS_ONNX_THREADS", raising=False)
    monkeypatch.delenv("NEXUS_ONNX_QUERY_THREADS", raising=False)
    monkeypatch.setattr(semantic.os, "cpu_count", lambda: 8)
    assert semantic._onnx_threads() == 4
    assert semantic._onnx_threads(query=True) == 2
    assert semantic._fastembed_kwargs("m")["threads"] == 4
    monkeypatch.setenv("NEXUS_ONNX_THREADS", "6")
    monkeypatch.setenv("NEXUS_ONNX_QUERY_THREADS", "1")
    assert semantic._fastembed_kwargs("m", query=True)["threads"] == 1
    assert semantic._onnx_threads() == 6
    monkeypatch.delenv("RAYON_NUM_THREADS", raising=False)
    monkeypatch.delenv("NEXUS_TOKENIZER_THREADS", raising=False)
    semantic._budget_tokenizer_threads()
    assert "RAYON_NUM_THREADS" not in semantic.os.environ  # default: the library's own pool
    monkeypatch.setenv("NEXUS_TOKENIZER_THREADS", "3")
    semantic._budget_tokenizer_threads()
    assert semantic.os.environ["RAYON_NUM_THREADS"] == "3"
    monkeypatch.setenv("RAYON_NUM_THREADS", "1")
    semantic._budget_tokenizer_threads()
    assert semantic.os.environ["RAYON_NUM_THREADS"] == "1"


def test_model_cache_loads_one_key_without_blocking_another():
    cache: dict[str, object] = {}
    started = threading.Event()
    release = threading.Event()

    def slow():
        started.set()
        release.wait(5)
        return "slow"

    worker = threading.Thread(target=lambda: semantic._cached(cache, "a", slow))
    worker.start()
    assert started.wait(5)
    t0 = time.perf_counter()
    assert semantic._cached(cache, "b", lambda: "fast") == "fast"
    assert time.perf_counter() - t0 < 1.0
    release.set()
    worker.join(5)
    assert semantic._cached(cache, "a", lambda: "other") == "slow"
