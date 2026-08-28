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

import pytest

from nexus_security.encryption import (
    EncryptionError,
    decrypt_text,
    encrypt_text,
    validate_tls,
)


def test_encrypt_and_decrypt_round_trip(sample_config, monkeypatch):
    monkeypatch.setenv("NEXUS_SECURITY_TEST_KEY", "secret")

    encrypted = encrypt_text("sensitive", sample_config.encryption)

    assert encrypted != "sensitive"
    assert decrypt_text(encrypted, sample_config.encryption) == "sensitive"


def test_encryption_disabled_returns_plaintext(sample_config):
    sample_config.encryption.enabled = False

    assert encrypt_text("plain", sample_config.encryption) == "plain"
    assert decrypt_text("plain", sample_config.encryption) == "plain"


def test_encrypt_raises_when_key_env_unset(sample_config, monkeypatch):
    monkeypatch.delenv("NEXUS_SECURITY_TEST_KEY", raising=False)

    with pytest.raises(EncryptionError):
        encrypt_text("sensitive", sample_config.encryption)


def test_decrypt_raises_when_key_env_unset(sample_config, monkeypatch):
    monkeypatch.setenv("NEXUS_SECURITY_TEST_KEY", "secret")
    encrypted = encrypt_text("sensitive", sample_config.encryption)
    monkeypatch.delenv("NEXUS_SECURITY_TEST_KEY", raising=False)

    with pytest.raises(EncryptionError):
        decrypt_text(encrypted, sample_config.encryption)


def test_ciphertext_is_randomized(sample_config, monkeypatch):
    monkeypatch.setenv("NEXUS_SECURITY_TEST_KEY", "secret")

    first = encrypt_text("sensitive", sample_config.encryption)
    second = encrypt_text("sensitive", sample_config.encryption)

    assert first != second
    assert decrypt_text(first, sample_config.encryption) == "sensitive"
    assert decrypt_text(second, sample_config.encryption) == "sensitive"


def test_decrypt_rejects_tampered_ciphertext(sample_config, monkeypatch):
    monkeypatch.setenv("NEXUS_SECURITY_TEST_KEY", "secret")
    encrypted = encrypt_text("sensitive", sample_config.encryption)
    tampered = encrypted[:-2] + ("AA" if encrypted[-2:] != "AA" else "BB")

    with pytest.raises(EncryptionError):
        decrypt_text(tampered, sample_config.encryption)


def test_decrypt_rejects_wrong_key(sample_config, monkeypatch):
    monkeypatch.setenv("NEXUS_SECURITY_TEST_KEY", "secret")
    encrypted = encrypt_text("sensitive", sample_config.encryption)
    monkeypatch.setenv("NEXUS_SECURITY_TEST_KEY", "different")

    with pytest.raises(EncryptionError):
        decrypt_text(encrypted, sample_config.encryption)


def test_key_id_acts_as_domain_separator(sample_config, monkeypatch):
    monkeypatch.setenv("NEXUS_SECURITY_TEST_KEY", "secret")
    encrypted = encrypt_text("sensitive", sample_config.encryption)

    sample_config.encryption.key_id = "other-key"
    with pytest.raises(EncryptionError):
        decrypt_text(encrypted, sample_config.encryption)


def test_validate_tls_uses_allowed_versions(sample_config):
    assert validate_tls(sample_config.encryption, "TLSv1.3") is True
    assert validate_tls(sample_config.encryption, "TLSv1.1") is False


def test_validate_tls_allows_when_not_required(sample_config):
    sample_config.encryption.require_tls = False

    assert validate_tls(sample_config.encryption, None) is True
