from pathlib import Path

from nexus_experience.config import load_config
from nexus_experience.models import ChannelType


def test_load_config_parses_channels_and_integration():
    config = load_config(Path("configs/engagement.yaml"))

    assert config.tenant.id == "default"
    assert config.integration.guardrails_project == "../orchestration-guardrails"
    assert len(config.channels) == 6
    assert config.channels["assistant"].type == ChannelType.ASSISTANT

