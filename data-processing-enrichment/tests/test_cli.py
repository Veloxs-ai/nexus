import json
from pathlib import Path

from typer.testing import CliRunner

from nexus_processing.cli import app


runner = CliRunner()


def test_validate_config_command_loads_jobs():
    result = runner.invoke(app, ["validate-config", "configs/processing.yaml"])

    assert result.exit_code == 0
    assert "Loaded 2 processing jobs." in result.output


def test_run_job_command_writes_output(tmp_path, monkeypatch):
    config_path = tmp_path / "configs" / "processing.yaml"
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
        """
jobs:
  customer_profiles:
    mode: records
    input_uri: data/raw/profiles.jsonl
    output_uri: data/processed/profiles.jsonl
    primary_key: customer_id
    text_fields:
      - notes
    transformations:
      trim_strings: true
      normalize_case_fields:
        status: lower
      rename_fields:
        customer_name: name
defaults:
  metadata:
    keyword_tags:
      customer:
        - renewal
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["run-job", str(config_path), "customer_profiles"])

    assert result.exit_code == 0
    assert "Processed 1 outputs for customer_profiles." in result.output
    assert Path("data/processed/profiles.jsonl").exists()

