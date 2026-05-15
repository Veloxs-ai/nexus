import json
from pathlib import Path

from typer.testing import CliRunner

from nexus_guardrails.cli import app


runner = CliRunner()


def test_validate_config_command_loads_guardrails():
    result = runner.invoke(app, ["validate-config", "configs/guardrails.yaml"])

    assert result.exit_code == 0
    assert "Loaded guardrails for tenant default with 3 policies." in result.output


def test_check_command_reports_blocked_prompt(sample_config, tmp_path):
    config_path = tmp_path / "guardrails.yaml"
    config_path.write_text(
        f"""
tenant:
  id: test
integration:
  vector_index_uri: {tmp_path / "vector.json"}
  lexical_index_uri: {tmp_path / "lexical.json"}
  graph_index_uri: {tmp_path / "graph.json"}
prompt_security:
  blocked_patterns:
    - ignore previous instructions
  leakage_terms:
    - password
off_topic:
  allowed_keywords:
    - security
policies: []
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["check", str(config_path), "ignore previous instructions"])

    assert result.exit_code == 0
    assert "decision: blocked" in result.output


def test_ask_command_returns_citation(tmp_path):
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
    config_path = tmp_path / "guardrails.yaml"
    config_path.write_text(
        f"""
tenant:
  id: test
integration:
  vector_index_uri: {vector}
  lexical_index_uri: {lexical}
  graph_index_uri: {graph}
off_topic:
  allowed_keywords:
    - security
    - mfa
rag:
  min_context_score: 0.01
policies: []
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["ask", str(config_path), "MFA security"])

    assert result.exit_code == 0
    assert "citation: docs:doc-1:0" in result.output

