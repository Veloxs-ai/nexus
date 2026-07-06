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

from nexus_retrieval.cli import main


def test_validate_config_command_loads_collections(capsys):
    exit_code = main(["validate-config", "configs/retrieval.json"])

    assert exit_code == 0
    assert "Loaded 2 retrieval collections." in capsys.readouterr().out


def test_build_index_and_search_commands(tmp_path, monkeypatch, capsys):
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
    config_path = tmp_path / "configs" / "retrieval.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "embedding": {"provider": "local_hashing", "dimensions": 16, "normalize": True},
                "stores": {
                    "vector_index_uri": "data/indexes/vector.json",
                    "lexical_index_uri": "data/indexes/lexical.json",
                    "graph_index_uri": "data/indexes/graph.json",
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
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    build_exit = main(["build-index", str(config_path)])
    build_out = capsys.readouterr().out
    search_exit = main(["search", str(config_path), "security access", "--limit", "1"])
    search_out = capsys.readouterr().out

    assert build_exit == 0
    assert "Indexed 1 documents." in build_out
    assert search_exit == 0
    assert "doc-1:0" in search_out
    assert Path("data/indexes/vector.json").exists()
