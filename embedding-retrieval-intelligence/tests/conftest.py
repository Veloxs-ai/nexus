# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexus_retrieval.config import RetrievalConfig


@pytest.fixture
def sample_config(tmp_path: Path) -> RetrievalConfig:
    input_path = tmp_path / "processed.jsonl"
    input_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "chunk_id": "doc-1:0",
                        "document_id": "doc-1",
                        "text": "MFA access review security policy",
                        "metadata": {"tags": ["security"], "entities": ["Security Policy"]},
                    }
                ),
                json.dumps(
                    {
                        "chunk_id": "doc-2:0",
                        "document_id": "doc-2",
                        "text": "invoice payment finance procedure",
                        "metadata": {"tags": ["finance"], "entities": ["Invoice Procedure"]},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return RetrievalConfig.model_validate(
        {
            "embedding": {"provider": "local_hashing", "dimensions": 32, "normalize": True},
            "stores": {
                "vector_index_uri": "vector.json",
                "lexical_index_uri": "lexical.json",
                "graph_index_uri": "graph.json",
            },
            "ranking": {
                "semantic_weight": 0.5,
                "lexical_weight": 0.35,
                "graph_weight": 0.15,
            },
            "collections": {
                "policy_documents": {
                    "input_uri": str(input_path),
                    "id_field": "chunk_id",
                    "text_field": "text",
                    "metadata_field": "metadata",
                    "graph": {
                        "entity_fields": ["metadata.entities"],
                        "tag_fields": ["metadata.tags"],
                        "parent_field": "document_id",
                    },
                }
            },
        }
    )

