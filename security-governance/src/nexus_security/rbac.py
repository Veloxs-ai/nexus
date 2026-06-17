# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

from __future__ import annotations

from nexus_security.config import SecurityConfig
from nexus_security.models import AccessDecision, AccessRequest, Decision
from nexus_security.tenant import same_tenant, tenant_allows_scope, validate_tenant


def authorize(config: SecurityConfig, request: AccessRequest) -> AccessDecision:
    validate_tenant(config, request.user_tenant)
    validate_tenant(config, request.resource_tenant)

    role = config.roles.get(request.role)
    if role is None:
        return AccessDecision(decision=Decision.DENIED, reason="unknown role", request=request)

    if request.permission not in role.permissions:
        return AccessDecision(decision=Decision.DENIED, reason="permission denied", request=request)

    if not same_tenant(request.user_tenant, request.resource_tenant):
        if "cross_tenant:read" not in role.permissions:
            return AccessDecision(decision=Decision.DENIED, reason="cross-tenant access denied", request=request)

    if not tenant_allows_scope(config, request.resource_tenant, request.data_scope):
        return AccessDecision(decision=Decision.DENIED, reason="tenant scope denied", request=request)

    if request.data_scope and "*" not in role.data_scopes and request.data_scope not in role.data_scopes:
        return AccessDecision(decision=Decision.DENIED, reason="role scope denied", request=request)

    return AccessDecision(decision=Decision.ALLOWED, reason="authorized", request=request)

