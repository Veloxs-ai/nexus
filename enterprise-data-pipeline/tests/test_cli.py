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

from typer.testing import CliRunner

from nexus_pipeline.cli import app


runner = CliRunner()


def test_validate_config_command_loads_sources():
    result = runner.invoke(app, ["validate-config", "configs/sources.yaml"])

    assert result.exit_code == 0
    assert "Loaded 4 sources." in result.output


def test_run_api_rejects_non_api_source():
    result = runner.invoke(app, ["run-api", "configs/sources.yaml", "finance_transactions"])

    assert result.exit_code != 0
    assert "not api" in result.output


def test_run_batch_command_uses_configured_checkpoint_store(monkeypatch, tmp_path):
    config_path = Path("configs/sources.yaml")

    def fake_load_config(path):
        config = __import__("nexus_pipeline.config", fromlist=["load_config"]).load_config(config_path)
        config.platform.checkpoint_store = str(tmp_path)
        return config

    monkeypatch.setattr("nexus_pipeline.cli.load_config", fake_load_config)
    result = runner.invoke(app, ["run-batch", "configs/sources.yaml", "finance_transactions"])

    assert result.exit_code == 0
    assert "Processed 2 batch records for finance_transactions." in result.output
