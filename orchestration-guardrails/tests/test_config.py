from pathlib import Path

from nexus_guardrails.config import load_config


def test_load_config_parses_policies_and_integrations():
    config = load_config(Path("configs/guardrails.yaml"))

    assert config.tenant.id == "default"
    assert len(config.policies) == 3
    assert config.integration.retrieval_project == "../embedding-retrieval-intelligence"

