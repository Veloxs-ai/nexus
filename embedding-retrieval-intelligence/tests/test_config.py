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

from pathlib import Path

from nexus_retrieval.config import load_config


def test_load_config_parses_collections_and_integration():
    config = load_config(Path("configs/retrieval.json"))

    assert config.integration.processing_project == "../data-processing-enrichment"
    assert set(config.collections) == {"customer_profiles", "policy_documents"}
    assert config.embedding.dimensions == 3072


def test_collection_requires_text_source():
    try:
        load_config(Path("configs/retrieval.json")).collections["policy_documents"].model_copy(
            update={"text_field": None, "text_fields": []}
        )
    except Exception:
        raise AssertionError("model_copy should not revalidate by default") from None
