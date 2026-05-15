from pathlib import Path

from nexus_security.config import load_config


def test_load_config_parses_roles_tenants_and_integrations():
    config = load_config(Path("configs/security.yaml"))

    assert len(config.roles) == 3
    assert len(config.tenants) == 2
    assert config.integration.experience_project == "../experience-api-engagement"
    assert "read:data" in config.roles["analyst"].permissions

