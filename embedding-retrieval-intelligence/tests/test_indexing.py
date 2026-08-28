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

from nexus_retrieval.indexing import build_document, build_indexes, extract_text


def test_build_document_extracts_nested_text_and_metadata(sample_config):
    collection = sample_config.collections["policy_documents"]
    record = {
        "chunk_id": "doc-1:0",
        "text": "security policy",
        "metadata": {"tags": ["security"]},
    }

    document = build_document("policy_documents", collection, record)

    assert document.id == "doc-1:0"
    assert document.text == "security policy"
    assert document.metadata == {"tags": ["security"]}


def test_extract_text_joins_multiple_fields(sample_config):
    collection = sample_config.collections["policy_documents"].model_copy(
        update={"text_field": None, "text_fields": ["payload.name", "payload.notes"]}
    )

    assert extract_text({"payload": {"name": "Acme", "notes": "renewal support"}}, collection) == (
        "Acme renewal support"
    )


def test_build_indexes_writes_all_indexes(sample_config, tmp_path):
    count = build_indexes(sample_config, tmp_path)

    assert count == 2
    assert (tmp_path / "vector.json").exists()
    assert (tmp_path / "lexical.json").exists()
    assert (tmp_path / "graph.json").exists()
