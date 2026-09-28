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

from nexus_retrieval.lexical import LexicalIndex
from nexus_retrieval.models import IndexedDocument


def test_lexical_index_scores_keyword_matches(tmp_path):
    index = LexicalIndex("lexical.json", tmp_path)
    index.add(IndexedDocument(id="a", collection="docs", text="security access access"))
    index.add(IndexedDocument(id="b", collection="docs", text="finance payment"))

    results = index.search("access security")

    assert results[0].id == "a"
    assert results[0].lexical_score == 1.0


def test_lexical_index_persists(tmp_path):
    index = LexicalIndex("lexical.json", tmp_path, in_memory_only=False)
    index.add(IndexedDocument(id="a", collection="docs", text="security access"))
    index.save()

    loaded = LexicalIndex("lexical.json", tmp_path, in_memory_only=False)
    loaded.load()

    assert loaded.search("security")[0].id == "a"


def test_lexical_index_ignores_stopword_only_matches(tmp_path):
    index = LexicalIndex("lexical.json", tmp_path)
    index.add(
        IndexedDocument(
            id="leave", collection="docs", text="The annual leave is 24 days of the year"
        )
    )
    index.add(
        IndexedDocument(id="laptops", collection="docs", text="Laptops must use disk encryption")
    )

    assert index.search("What is the capital of France?") == []
    assert index.search("the of is") == []


def test_lexical_score_is_share_of_query_matched(tmp_path):
    index = LexicalIndex("lexical.json", tmp_path)
    index.add(
        IndexedDocument(id="leave", collection="docs", text="Employees get 24 days of annual leave")
    )
    index.add(
        IndexedDocument(id="sick", collection="docs", text="Sick leave needs a medical certificate")
    )

    full = index.search("annual leave")[0]
    assert full.id == "leave" and full.lexical_score == 1.0

    partial = index.search("annual leave in France")[0]
    assert partial.id == "leave"
    assert 0.0 < partial.lexical_score < 1.0  # 'france' is unknown, so only part matched


def test_lexical_rare_words_outweigh_common_ones(tmp_path):
    index = LexicalIndex("lexical.json", tmp_path)
    for i in range(5):
        index.add(IndexedDocument(id=f"policy-{i}", collection="docs", text=f"policy section {i}"))
    index.add(
        IndexedDocument(id="vpn", collection="docs", text="vpn access requires a hardware token")
    )

    results = index.search("policy vpn")
    assert results[0].id == "vpn"
    assert results[0].lexical_score > results[1].lexical_score
