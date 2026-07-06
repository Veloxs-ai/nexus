# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

from pathlib import Path

from nexus_pipeline.cli import main


def test_validate_config_command_loads_sources(capsys):
    exit_code = main(["validate-config", "configs/sources.json"])

    assert exit_code == 0
    assert "Loaded 4 sources." in capsys.readouterr().out


def test_run_api_rejects_non_api_source(capsys):
    exit_code = main(["run-api", "configs/sources.json", "finance_transactions"])

    assert exit_code != 0
    assert "not api" in capsys.readouterr().err


def test_run_batch_command_uses_configured_checkpoint_store(monkeypatch, tmp_path, capsys):
    config_path = Path("configs/sources.json")

    def fake_load_config(path):
        config = __import__("nexus_pipeline.config", fromlist=["load_config"]).load_config(config_path)
        config.platform.checkpoint_store = str(tmp_path)
        return config

    monkeypatch.setattr("nexus_pipeline.cli.load_config", fake_load_config)
    exit_code = main(["run-batch", "configs/sources.json", "finance_transactions"])

    assert exit_code == 0
    assert "Processed 2 batch records for finance_transactions." in capsys.readouterr().out
