from __future__ import annotations

import hmac
import os
from typing import Protocol

from nexus_experience.config import EngagementConfig
from nexus_experience.models import Principal


class AuthError(Exception):
    """Raised when authentication or authorization fails."""


class Authorizer(Protocol):
    """Pluggable RBAC hook.

    Implementations may call into nexus_security.rbac.authorize or any
    other policy engine. Raise AuthError to deny.
    """

    def __call__(self, principal: Principal, capability: str, resource_tenant: str) -> None: ...


def _resolve_secret(value: str) -> str:
    if value.startswith("env:"):
        env_name = value[len("env:") :]
        resolved = os.environ.get(env_name, "")
        if not resolved:
            raise AuthError(f"API key environment variable {env_name!r} is unset or empty")
        return resolved
    return value


def verify_api_key(config: EngagementConfig, presented: str | None) -> Principal:
    if not config.auth.enabled:
        return Principal(
            user_id="anonymous",
            tenant_id=config.tenant.id,
            role="anonymous",
            permissions=[],
        )

    if not presented:
        raise AuthError("missing API key")

    presented_bytes = presented.encode("utf-8")
    for key_entry in config.auth.api_keys:
        expected = _resolve_secret(key_entry.secret).encode("utf-8")
        if hmac.compare_digest(presented_bytes, expected):
            return Principal(
                user_id=key_entry.user_id,
                tenant_id=key_entry.tenant_id,
                role=key_entry.role,
                permissions=list(key_entry.permissions),
            )
    raise AuthError("invalid API key")


def default_authorizer(principal: Principal, capability: str, resource_tenant: str) -> None:
    if principal.role == "anonymous":
        return
    if principal.tenant_id != resource_tenant:
        raise AuthError(
            f"principal tenant {principal.tenant_id!r} does not match "
            f"resource tenant {resource_tenant!r}"
        )
    if capability not in principal.permissions:
        raise AuthError(f"principal lacks capability {capability!r}")


def anonymous_principal(config: EngagementConfig) -> Principal:
    """Principal used for in-process callers (CLI, SDK) when auth is disabled.

    Raises AuthError if auth is enabled — those callers must supply a key.
    """
    if config.auth.enabled:
        raise AuthError("auth is enabled; an API key is required for this call")
    return Principal(
        user_id="anonymous",
        tenant_id=config.tenant.id,
        role="anonymous",
        permissions=[],
    )
