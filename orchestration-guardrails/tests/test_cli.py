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

import json

from nexus_guardrails.cli import main


def test_validate_config_command_loads_guardrails(capsys):
    exit_code = main(["validate-config", "configs/guardrails.json"])

    assert exit_code == 0
    assert "Loaded guardrails for tenant default with 3 policies." in capsys.readouterr().out


def test_check_command_reports_blocked_prompt(sample_config, tmp_path, capsys):
    config_path = tmp_path / "guardrails.json"
    config_path.write_text(
        json.dumps(
            {
                "tenant": {"id": "test"},
                "integration": {
                    "vector_index_uri": str(tmp_path / "vector.json"),
                    "lexical_index_uri": str(tmp_path / "lexical.json"),
                    "graph_index_uri": str(tmp_path / "graph.json"),
                },
                "prompt_security": {
                    "blocked_patterns": ["ignore previous instructions"],
                    "leakage_terms": ["password"],
                },
                "off_topic": {"allowed_keywords": ["security"]},
                "policies": [],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["check", str(config_path), "ignore previous instructions"])

    assert exit_code == 0
    assert "decision: blocked" in capsys.readouterr().out


def test_ask_command_returns_citation(tmp_path, capsys):
    vector = tmp_path / "vector.json"
    lexical = tmp_path / "lexical.json"
    graph = tmp_path / "graph.json"
    vector.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "id": "doc-1:0",
                        "collection": "docs",
                        "text": "MFA access security policy",
                        "embedding": [1.0],
                    }
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
                        "collection": "docs",
                        "text": "MFA access security policy",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    graph.write_text(json.dumps({"nodes": {}, "edges": []}), encoding="utf-8")
    config_path = tmp_path / "guardrails.json"
    config_path.write_text(
        json.dumps(
            {
                "tenant": {"id": "test"},
                "integration": {
                    "vector_index_uri": str(vector),
                    "lexical_index_uri": str(lexical),
                    "graph_index_uri": str(graph),
                },
                "off_topic": {"allowed_keywords": ["security", "mfa"]},
                "rag": {"min_context_score": 0.01},
                "policies": [],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["ask", str(config_path), "MFA security"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "citation: docs:doc-1:0" in out
