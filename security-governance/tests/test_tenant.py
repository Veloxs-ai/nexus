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

