# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

from nexus_security.models import AccessRequest, Decision
from nexus_security.rbac import authorize


def test_authorize_allows_role_permission_and_scope(sample_config):
    decision = authorize(
        sample_config,
        AccessRequest(
            role="analyst",
            permission="read:data",
            user_tenant="tenant-a",
            resource_tenant="tenant-a",
            data_scope="customer",
        ),
    )

    assert decision.decision == Decision.ALLOWED


def test_authorize_denies_unknown_role(sample_config):
    decision = authorize(
        sample_config,
        AccessRequest(
            role="missing",
            permission="read:data",
            user_tenant="tenant-a",
            resource_tenant="tenant-a",
        ),
    )

    assert decision.reason == "unknown role"


def test_authorize_denies_missing_permission(sample_config):
    decision = authorize(
        sample_config,
        AccessRequest(
            role="analyst",
            permission="write:data",
            user_tenant="tenant-a",
            resource_tenant="tenant-a",
        ),
    )

    assert decision.reason == "permission denied"


def test_authorize_denies_cross_tenant_without_permission(sample_config):
    decision = authorize(
        sample_config,
        AccessRequest(
            role="analyst",
            permission="read:data",
            user_tenant="tenant-a",
            resource_tenant="tenant-b",
        ),
    )

    assert decision.reason == "cross-tenant access denied"


def test_authorize_allows_admin_cross_tenant(sample_config):
    decision = authorize(
        sample_config,
        AccessRequest(
            role="admin",
            permission="read:data",
            user_tenant="tenant-a",
            resource_tenant="tenant-b",
            data_scope="customer",
        ),
    )

    assert decision.decision == Decision.ALLOWED


def test_authorize_denies_role_scope(sample_config):
    decision = authorize(
        sample_config,
        AccessRequest(
            role="analyst",
            permission="read:data",
            user_tenant="tenant-a",
            resource_tenant="tenant-a",
            data_scope="finance",
        ),
    )

    assert decision.decision == Decision.DENIED

