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

from nexus_security.config import load_config


def test_load_config_parses_roles_tenants_and_integrations():
    config = load_config(Path("configs/security.json"))

    assert len(config.roles) == 3
    assert len(config.tenants) == 2
    assert config.integration.experience_project == "../experience-api-engagement"
    assert "read:data" in config.roles["analyst"].permissions

