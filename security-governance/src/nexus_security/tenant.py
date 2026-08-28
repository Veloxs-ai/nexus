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

from .config import SecurityConfig


def validate_tenant(config: SecurityConfig, tenant_id: str) -> None:
    if tenant_id not in config.tenants:
        raise ValueError(f"Unknown tenant: {tenant_id}")


def same_tenant(user_tenant: str, resource_tenant: str) -> bool:
    return user_tenant == resource_tenant


def tenant_allows_scope(config: SecurityConfig, tenant_id: str, data_scope: str | None) -> bool:
    if data_scope is None:
        return True
    validate_tenant(config, tenant_id)
    return data_scope in config.tenants[tenant_id].data_scopes
