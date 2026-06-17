# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

import json
from pathlib import Path

from typer.testing import CliRunner

from nexus_retrieval.cli import app


runner = CliRunner()


def test_validate_config_command_loads_collections():
    result = runner.invoke(app, ["validate-config", "configs/retrieval.yaml"])

    assert result.exit_code == 0
    assert "Loaded 2 retrieval collections." in result.output


def test_build_index_and_search_commands(tmp_path, monkeypatch):
    input_path = tmp_path / "processed.jsonl"
    input_path.write_text(
        json.dumps(
            {
                "chunk_id": "doc-1:0",
                "document_id": "doc-1",
                "text": "MFA access security policy",
                "metadata": {"tags": ["security"], "entities": ["Security Policy"]},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "configs" / "retrieval.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        f"""
embedding:
  provider: local_hashing
  dimensions: 16
  normalize: true
stores:
  vector_index_uri: data/indexes/vector.json
  lexical_index_uri: data/indexes/lexical.json
  graph_index_uri: data/indexes/graph.json
collections:
  policy_documents:
    input_uri: {input_path}
    id_field: chunk_id
    text_field: text
    metadata_field: metadata
    graph:
      entity_fields:
        - metadata.entities
      tag_fields:
        - metadata.tags
      parent_field: document_id
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    build_result = runner.invoke(app, ["build-index", str(config_path)])
    search_result = runner.invoke(
        app, ["search", str(config_path), "security access", "--limit", "1"]
    )

    assert build_result.exit_code == 0
    assert "Indexed 1 documents." in build_result.output
    assert search_result.exit_code == 0
    assert "doc-1:0" in search_result.output
    assert Path("data/indexes/vector.json").exists()

