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

from nexus_experience.api import create_service


def test_create_service_loads_config_and_gateway(tmp_path):
    config_path = tmp_path / "engagement.yaml"
    config_path.write_text(
        """
tenant:
  id: api-test
integration:
  mode: mock
channels:
  assistant:
    type: assistant
    enabled: true
    allowed_capabilities:
      - ask
      - session
""",
        encoding="utf-8",
    )

    service = create_service(Path(config_path))

    assert service.health() == {"status": "ok", "tenant": "api-test"}

