from pathlib import Path

from nexus.config import load_config


def test_load_config_parses_all_layers():
    config = load_config(Path("configs/nexus.yaml"))

    assert config.platform.name == "Nexus Enterprise AI Platform"
    assert len(config.layers) == 7
    assert config.layers["experience-api-engagement"].cli_module == "nexus_experience.cli"

