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

from nexus_retrieval.models import VectorEntry
from nexus_retrieval.vector_store import LocalVectorStore


def test_vector_store_search_and_persistence(tmp_path):
    store = LocalVectorStore("vector.json", tmp_path, in_memory_only=False)
    store.add(
        VectorEntry(
            id="a",
            collection="docs",
            text="security policy",
            embedding=[1.0, 0.0],
            metadata={"tags": ["security"]},
        )
    )
    store.add(
        VectorEntry(
            id="b",
            collection="docs",
            text="finance policy",
            embedding=[0.0, 1.0],
        )
    )
    store.save()

    loaded = LocalVectorStore("vector.json", tmp_path, in_memory_only=False)
    loaded.load()
    results = loaded.search([1.0, 0.0], limit=1)

    assert results[0].id == "a"
    assert results[0].semantic_score == 1.0
