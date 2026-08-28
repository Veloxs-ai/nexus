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

import json
from pathlib import Path

from nexus_experience.api import create_service


def test_create_service_loads_config_and_gateway(tmp_path):
    config_path = tmp_path / "engagement.json"
    config_path.write_text(
        json.dumps(
            {
                "tenant": {"id": "api-test"},
                "integration": {"mode": "mock"},
                "channels": {
                    "assistant": {
                        "type": "assistant",
                        "enabled": True,
                        "allowed_capabilities": ["ask", "session"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    service = create_service(Path(config_path))

    assert service.health() == {"status": "ok", "tenant": "api-test"}
