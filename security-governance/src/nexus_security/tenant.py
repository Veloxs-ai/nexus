from __future__ import annotations

from nexus_security.config import SecurityConfig


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

