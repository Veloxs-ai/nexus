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
            "observability": {"output_uri": "events.jsonl", "enabled": True, "service_name": "test"},
            "encryption": {
                "enabled": True,
                "key_id": "test-key",
                "key_material_env": "NEXUS_SECURITY_TEST_KEY",
                "require_tls": True,
                "allowed_tls_versions": ["TLSv1.3"],
            },
        }
    )

