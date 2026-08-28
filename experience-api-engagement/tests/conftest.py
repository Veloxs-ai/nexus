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
