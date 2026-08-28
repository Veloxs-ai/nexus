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

from nexus_guardrails.rag import compose_grounded_answer, retrieve_context


def test_retrieve_context_returns_relevant_citation(sample_config, tmp_path):
    citations = retrieve_context(sample_config, "MFA security", tmp_path)

    assert citations[0].source_id == "doc-1:0"
    assert citations[0].score > 0


def test_compose_grounded_answer_requires_citations():
    assert (
        compose_grounded_answer("query", [])
        == "I do not have enough trusted context to answer this request."
    )


def test_compose_grounded_answer_includes_context(sample_config, tmp_path):
    citations = retrieve_context(sample_config, "MFA security", tmp_path)

    answer = compose_grounded_answer("MFA security", citations)

    assert "MFA" in answer
