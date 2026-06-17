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

from nexus_guardrails.config import load_config


def test_load_config_parses_policies_and_integrations():
    config = load_config(Path("configs/guardrails.yaml"))

    assert config.tenant.id == "default"
    assert len(config.policies) == 3
    assert config.integration.retrieval_project == "../embedding-retrieval-intelligence"

