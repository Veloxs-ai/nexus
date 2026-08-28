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

from nexus_security.config import SecurityConfig


@pytest.fixture
def sample_config() -> SecurityConfig:
    return SecurityConfig.model_validate(
        {
            "tenants": {
                "tenant-a": {"name": "Tenant A", "data_scopes": ["customer", "policy"]},
                "tenant-b": {"name": "Tenant B", "data_scopes": ["customer"]},
            },
            "roles": {
                "analyst": {
                    "permissions": ["read:data", "query:ai"],
                    "data_scopes": ["customer", "policy"],
                },
                "admin": {
                    "permissions": ["read:data", "cross_tenant:read"],
                    "data_scopes": ["*"],
                },
            },
            "audit": {"output_uri": "audit.jsonl", "enabled": True, "include_denied_events": True},
            "observability": {
                "output_uri": "events.jsonl",
                "enabled": True,
                "service_name": "test",
            },
            "encryption": {
                "enabled": True,
                "key_id": "test-key",
                "key_material_env": "NEXUS_SECURITY_TEST_KEY",
                "require_tls": True,
                "allowed_tls_versions": ["TLSv1.3"],
            },
        }
    )
