import pytest

from nexus_experience.auth import (
    AuthError,
    anonymous_principal,
    default_authorizer,
    verify_api_key,
)
from nexus_experience.config import ApiKeyEntry, AuthConfig
from nexus_experience.models import Principal


def _with_auth(config, keys):
    config.auth = AuthConfig(enabled=True, api_keys=keys)
    return config


def test_disabled_auth_returns_anonymous_principal(sample_config):
    principal = verify_api_key(sample_config, presented=None)

    assert principal.role == "anonymous"
    assert principal.tenant_id == sample_config.tenant.id


def test_missing_key_when_required_raises(sample_config):
    _with_auth(sample_config, [ApiKeyEntry(secret="abc", user_id="u1", tenant_id="test")])

    with pytest.raises(AuthError):
        verify_api_key(sample_config, presented=None)


def test_invalid_key_raises(sample_config):
    _with_auth(sample_config, [ApiKeyEntry(secret="correct", user_id="u1", tenant_id="test")])

    with pytest.raises(AuthError):
        verify_api_key(sample_config, presented="wrong")


def test_valid_key_returns_bound_principal(sample_config):
    _with_auth(
        sample_config,
        [
            ApiKeyEntry(
                secret="correct",
                user_id="u1",
                tenant_id="test",
                role="analyst",
                permissions=["ask", "session"],
            )
        ],
    )

    principal = verify_api_key(sample_config, presented="correct")

    assert principal.user_id == "u1"
    assert principal.role == "analyst"
    assert "ask" in principal.permissions


def test_env_secret_resolves_from_environment(sample_config, monkeypatch):
    monkeypatch.setenv("TEST_API_KEY", "from-env")
    _with_auth(
        sample_config,
        [ApiKeyEntry(secret="env:TEST_API_KEY", user_id="u1", tenant_id="test")],
    )

    principal = verify_api_key(sample_config, presented="from-env")

    assert principal.user_id == "u1"


def test_env_secret_missing_raises(sample_config, monkeypatch):
    monkeypatch.delenv("MISSING_KEY", raising=False)
    _with_auth(
        sample_config,
        [ApiKeyEntry(secret="env:MISSING_KEY", user_id="u1", tenant_id="test")],
    )

    with pytest.raises(AuthError):
        verify_api_key(sample_config, presented="anything")


def test_anonymous_principal_helper_raises_when_auth_enabled(sample_config):
    _with_auth(sample_config, [ApiKeyEntry(secret="x", user_id="u1", tenant_id="test")])

    with pytest.raises(AuthError):
        anonymous_principal(sample_config)


def test_default_authorizer_blocks_cross_tenant():
    principal = Principal(user_id="u1", tenant_id="t1", role="analyst", permissions=["ask"])
    with pytest.raises(AuthError):
        default_authorizer(principal, "ask", "t2")


def test_default_authorizer_blocks_missing_capability():
    principal = Principal(user_id="u1", tenant_id="t1", role="analyst", permissions=["session"])
    with pytest.raises(AuthError):
        default_authorizer(principal, "ask", "t1")


def test_default_authorizer_allows_when_permitted():
    principal = Principal(
        user_id="u1", tenant_id="t1", role="analyst", permissions=["ask", "session"]
    )
    default_authorizer(principal, "ask", "t1")
