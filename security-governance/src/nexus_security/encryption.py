from __future__ import annotations

import base64
import hashlib
import os

from nexus_security.config import EncryptionConfig


def get_key_material(config: EncryptionConfig) -> bytes:
    raw = os.getenv(config.key_material_env, config.key_id)
    return hashlib.sha256(raw.encode("utf-8")).digest()


def encrypt_text(plaintext: str, config: EncryptionConfig) -> str:
    if not config.enabled:
        return plaintext
    key = get_key_material(config)
    data = plaintext.encode("utf-8")
    encrypted = bytes(byte ^ key[index % len(key)] for index, byte in enumerate(data))
    return base64.urlsafe_b64encode(encrypted).decode("ascii")


def decrypt_text(ciphertext: str, config: EncryptionConfig) -> str:
    if not config.enabled:
        return ciphertext
    key = get_key_material(config)
    data = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
    decrypted = bytes(byte ^ key[index % len(key)] for index, byte in enumerate(data))
    return decrypted.decode("utf-8")


def validate_tls(config: EncryptionConfig, tls_version: str | None) -> bool:
    if not config.require_tls:
        return True
    return tls_version in config.allowed_tls_versions

