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

"""Unicode lexical tokens, BM25, Reciprocal Rank Fusion and multi-query re-ranking."""

from __future__ import annotations

from nexus_retrieval.config import RankingConfig
from nexus_retrieval.embeddings import tokenize
from nexus_retrieval.lexical import LexicalIndex
from nexus_retrieval.models import IndexedDocument, SearchResult
from nexus_retrieval.ranking import combine_scores, reciprocal_rank_fusion, rerank_multi


def test_tokenize_covers_every_script():
    assert tokenize("In-memory ABC_def 42") == ["in-memory", "abc_def", "42"]  # ASCII unchanged
    assert tokenize("Café naïve") == ["cafe", "naive"]
    assert tokenize("हिन्दी क्‍ष") == ["हिन्दी", "क्ष"]
    assert tokenize("Москва") == ["москва"]
    assert tokenize("東京都") == ["東京", "京都"]
    assert tokenize("日") == ["日"]


def _doc(i, text):
    return IndexedDocument(id=i, collection="c", text=text, metadata={})


def test_lexical_index_finds_non_latin_text():
    index = LexicalIndex()
    index.add(_doc("hi", "भुगतान की अंतिम तिथि"))
    index.add(_doc("en", "payment due date"))
    assert index.search("भुगतान")[0].id == "hi"


def test_bm25_saturates_term_frequency_and_normalises_length():
    index = LexicalIndex(scoring="bm25")
    index.add(_doc("short", "refund policy"))
    index.add(_doc("spam", "refund " * 50 + "unrelated words " * 200))
    index.add(_doc("other", "shipping times"))
    results = index.search("refund policy")
    assert results[0].id == "short" and results[0].lexical_score == 1.0


def test_reciprocal_rank_fusion():
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["c", "a"]])
    assert fused == ["a", "c", "b"]
    items = reciprocal_rank_fusion([[{"id": 1}, {"id": 2}], [{"id": 2}]], key=lambda x: x["id"])
    assert [i["id"] for i in items] == [2, 1]


def test_combine_scores_rrf_mode_is_scale_free():
    sem = [
        SearchResult(id="a", collection="c", text="", score=0.9, semantic_score=0.9),
        SearchResult(id="b", collection="c", text="", score=0.8, semantic_score=0.8),
    ]
    lex = [SearchResult(id="b", collection="c", text="", score=40.0, lexical_score=40.0)]
    out = combine_scores(sem, lex, {}, RankingConfig(fusion="rrf"), limit=2)
    assert [r.id for r in out] == ["b", "a"]


def test_rerank_multi_keeps_the_best_score_per_passage():
    def score(query, passages):
        return [1.0 if query.split()[-1] in p else 0.0 for p in passages]

    out = rerank_multi(
        ["compare A and B", "about A", "about B"], ["A side", "B side"], score, found_by=[{1}, {2}]
    )
    assert out == [1.0, 1.0]
    assert rerank_multi(["q"], [], score) == []
