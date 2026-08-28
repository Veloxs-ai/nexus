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
from pathlib import Path

from nexus_processing.cli import main


def test_validate_config_command_loads_jobs(capsys):
    exit_code = main(["validate-config", "configs/processing.json"])

    assert exit_code == 0
    assert "Loaded 2 processing jobs." in capsys.readouterr().out


def test_run_job_command_writes_output(tmp_path, monkeypatch, capsys):
    config_path = tmp_path / "configs" / "processing.json"
    raw_path = tmp_path / "data" / "raw"
    raw_path.mkdir(parents=True)
    config_path.parent.mkdir(parents=True)
    (raw_path / "profiles.jsonl").write_text(
        json.dumps(
            {
                "customer_id": "c001",
                "customer_name": " Acme ",
                "status": " ACTIVE ",
                "notes": "Renewal support request.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    config_path.write_text(
        json.dumps(
            {
                "jobs": {
                    "customer_profiles": {
                        "mode": "records",
                        "input_uri": "data/raw/profiles.jsonl",
                        "output_uri": "data/processed/profiles.jsonl",
                        "primary_key": "customer_id",
                        "text_fields": ["notes"],
                        "transformations": {
                            "trim_strings": True,
                            "normalize_case_fields": {"status": "lower"},
                            "rename_fields": {"customer_name": "name"},
                        },
                    }
                },
                "defaults": {"metadata": {"keyword_tags": {"customer": ["renewal"]}}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    exit_code = main(["run-job", str(config_path), "customer_profiles"])

    assert exit_code == 0
    assert "Processed 1 outputs for customer_profiles." in capsys.readouterr().out
    assert Path("data/processed/profiles.jsonl").exists()
