from __future__ import annotations

import pytest

from nexus_experience.config import EngagementConfig
from nexus_experience.gateway import MockGuardrailsGateway
from nexus_experience.service import ExperienceService


@pytest.fixture
def sample_config() -> EngagementConfig:
    return EngagementConfig.model_validate(
        {
            "tenant": {"id": "test", "display_name": "Test Tenant"},
            "integration": {"mode": "mock"},
            "assistant": {"greeting": "Hello", "max_history_messages": 2},
            "channels": {
                "assistant": {
                    "type": "assistant",
                    "enabled": True,
                    "allowed_capabilities": ["ask", "session"],
                },
                "sdk": {
                    "type": "sdk",
                    "enabled": True,
                    "allowed_capabilities": ["ask", "session"],
                },
                "disabled": {
                    "type": "web",
                    "enabled": False,
                    "allowed_capabilities": ["ask"],
                },
            },
        }
    )


@pytest.fixture
def sample_service(sample_config) -> ExperienceService:
    return ExperienceService(sample_config, MockGuardrailsGateway())

