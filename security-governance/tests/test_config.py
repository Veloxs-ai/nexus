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

from nexus_security.config import load_config


def test_load_config_parses_roles_tenants_and_integrations():
    config = load_config(Path("configs/security.json"))

    assert len(config.roles) == 3
    assert len(config.tenants) == 2
    assert config.integration.experience_project == "../experience-api-engagement"
    assert "read:data" in config.roles["analyst"].permissions
