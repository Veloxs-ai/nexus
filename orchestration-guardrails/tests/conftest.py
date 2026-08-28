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

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexus_guardrails.config import GuardrailsConfig


@pytest.fixture
def sample_config(tmp_path: Path) -> GuardrailsConfig:
    vector = tmp_path / "vector.json"
    lexical = tmp_path / "lexical.json"
    graph = tmp_path / "graph.json"
    vector.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "id": "doc-1:0",
                        "collection": "policy_documents",
                        "text": "All employees must use MFA for sensitive systems.",
                        "embedding": [1.0],
                        "metadata": {"tags": ["security"]},
                    },
                    {
                        "id": "doc-2:0",
                        "collection": "policy_documents",
                        "text": "Invoices must be reviewed before payment.",
                        "embedding": [0.5],
                        "metadata": {"tags": ["finance"]},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    lexical.write_text(
        json.dumps(
            {
                "documents": {
                    "doc-1:0": {
                        "id": "doc-1:0",
                        "collection": "policy_documents",
                        "text": "All employees must use MFA for sensitive systems.",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    graph.write_text(json.dumps({"nodes": {}, "edges": []}), encoding="utf-8")
    return GuardrailsConfig.model_validate(
        {
            "tenant": {"id": "test", "allowed_domains": ["security", "finance"]},
            "integration": {
                "vector_index_uri": str(vector),
                "lexical_index_uri": str(lexical),
                "graph_index_uri": str(graph),
            },
            "prompt_security": {
                "blocked_patterns": ["ignore previous instructions"],
                "leakage_terms": ["api key", "password"],
            },
            "pii": {"enabled": True, "mask": True, "detectors": ["email", "ssn", "phone"]},
            "policies": [
                {
                    "id": "no_secrets",
                    "description": "No secrets.",
                    "blocked_terms": ["password", "api key"],
                    "action": "block",
                },
                {
                    "id": "require_grounding",
                    "description": "Require citations.",
                    "require_citations": True,
                    "action": "warn",
                },
            ],
            "off_topic": {
                "enabled": True,
                "min_keyword_overlap": 1,
                "allowed_keywords": ["security", "mfa", "invoice", "payment"],
            },
            "rag": {"top_k": 2, "min_context_score": 0.01, "require_citations": True},
            "verification": {"min_confidence": 0.1, "require_grounded_terms": True},
        }
    )
