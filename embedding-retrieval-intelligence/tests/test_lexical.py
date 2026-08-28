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
