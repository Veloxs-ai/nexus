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

from nexus_security.tenant import same_tenant, tenant_allows_scope, validate_tenant


def test_validate_tenant_accepts_known_tenant(sample_config):
    validate_tenant(sample_config, "tenant-a")


def test_validate_tenant_rejects_unknown_tenant(sample_config):
    try:
        validate_tenant(sample_config, "missing")
    except ValueError as exc:
        assert "Unknown tenant" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_same_tenant_compares_ids():
    assert same_tenant("a", "a") is True
    assert same_tenant("a", "b") is False


def test_tenant_allows_scope(sample_config):
    assert tenant_allows_scope(sample_config, "tenant-a", "customer") is True
    assert tenant_allows_scope(sample_config, "tenant-b", "policy") is False
