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

from nexus.config import load_config


def test_load_config_parses_all_layers():
    config = load_config(Path("configs/nexus.yaml"))

    assert config.platform.name == "Nexus Enterprise AI Platform"
    assert len(config.layers) == 7
    assert config.layers["experience-api-engagement"].cli_module == "nexus_experience.cli"

