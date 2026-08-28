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

from nexus_retrieval.hybrid import search
from nexus_retrieval.indexing import build_indexes


def test_hybrid_search_returns_contextually_relevant_result(sample_config, tmp_path):
    build_indexes(sample_config, tmp_path)

    results = search(sample_config, "MFA access security", tmp_path, limit=1)

    assert results[0].id == "doc-1:0"
    assert results[0].score > 0
    assert results[0].graph_score > 0
