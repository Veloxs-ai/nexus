# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

from pathlib import Path

from nexus_experience.config import load_config
from nexus_experience.models import ChannelType


def test_load_config_parses_channels_and_integration():
    config = load_config(Path("configs/engagement.json"))

    assert config.tenant.id == "default"
    assert config.integration.guardrails_project == "../orchestration-guardrails"
    assert len(config.channels) == 6
    assert config.channels["assistant"].type == ChannelType.ASSISTANT

