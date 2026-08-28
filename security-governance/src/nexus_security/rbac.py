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
from .models import AccessDecision, AccessRequest, Decision
from .tenant import same_tenant, tenant_allows_scope, validate_tenant


def authorize(config: SecurityConfig, request: AccessRequest) -> AccessDecision:
    validate_tenant(config, request.user_tenant)
    validate_tenant(config, request.resource_tenant)

    role = config.roles.get(request.role)
    if role is None:
        return AccessDecision(decision=Decision.DENIED, reason="unknown role", request=request)

    if request.permission not in role.permissions:
        return AccessDecision(decision=Decision.DENIED, reason="permission denied", request=request)

    if (
        not same_tenant(request.user_tenant, request.resource_tenant)
        and "cross_tenant:read" not in role.permissions
    ):
        return AccessDecision(
            decision=Decision.DENIED, reason="cross-tenant access denied", request=request
        )

    if not tenant_allows_scope(config, request.resource_tenant, request.data_scope):
        return AccessDecision(
            decision=Decision.DENIED, reason="tenant scope denied", request=request
        )

    if (
        request.data_scope
        and "*" not in role.data_scopes
        and request.data_scope not in role.data_scopes
    ):
        return AccessDecision(decision=Decision.DENIED, reason="role scope denied", request=request)

    return AccessDecision(decision=Decision.ALLOWED, reason="authorized", request=request)
