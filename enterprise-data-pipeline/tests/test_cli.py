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
        config = __import__("nexus_pipeline.config", fromlist=["load_config"]).load_config(
            config_path
        )
        config.platform.checkpoint_store = str(tmp_path)
        return config

    monkeypatch.setattr("nexus_pipeline.cli.load_config", fake_load_config)
    exit_code = main(["run-batch", "configs/sources.json", "finance_transactions"])

    assert exit_code == 0
    assert "Processed 2 batch records for finance_transactions." in capsys.readouterr().out
