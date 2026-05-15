from nexus_security.encryption import decrypt_text, encrypt_text, validate_tls


def test_encrypt_and_decrypt_round_trip(sample_config, monkeypatch):
    monkeypatch.setenv("NEXUS_SECURITY_TEST_KEY", "secret")

    encrypted = encrypt_text("sensitive", sample_config.encryption)

    assert encrypted != "sensitive"
    assert decrypt_text(encrypted, sample_config.encryption) == "sensitive"


def test_encryption_disabled_returns_plaintext(sample_config):
    sample_config.encryption.enabled = False

    assert encrypt_text("plain", sample_config.encryption) == "plain"
    assert decrypt_text("plain", sample_config.encryption) == "plain"


def test_validate_tls_uses_allowed_versions(sample_config):
    assert validate_tls(sample_config.encryption, "TLSv1.3") is True
    assert validate_tls(sample_config.encryption, "TLSv1.1") is False


def test_validate_tls_allows_when_not_required(sample_config):
    sample_config.encryption.require_tls = False

    assert validate_tls(sample_config.encryption, None) is True

