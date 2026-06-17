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

from nexus_observability.config import load_config


def test_load_config_parses_services_exporters_and_integrations():
    config = load_config(Path("configs/observability.yaml"))

    assert len(config.services) == 7
    assert len(config.exporters) == 6
    assert config.integration.experience_api_engagement == "../experience-api-engagement"
    assert config.services["orchestration-guardrails"].layer == "guardrails"

