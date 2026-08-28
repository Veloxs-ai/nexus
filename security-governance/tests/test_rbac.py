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
