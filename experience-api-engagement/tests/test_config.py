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

from pathlib import Path

from nexus_experience.config import load_config
from nexus_experience.models import ChannelType


def test_load_config_parses_channels_and_integration():
    config = load_config(Path("configs/engagement.json"))

    assert config.tenant.id == "default"
    assert config.integration.guardrails_project == "../orchestration-guardrails"
    assert len(config.channels) == 6
    assert config.channels["assistant"].type == ChannelType.ASSISTANT
