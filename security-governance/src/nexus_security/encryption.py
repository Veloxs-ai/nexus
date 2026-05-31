from __future__ import annotations

import base64
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from nexus_security.config import EncryptionConfig

_HKDF_INFO = b"nexus-security/encryption/v1"


class EncryptionError(Exception):
    """Raised when encryption configuration or input is invalid."""


def _derive_fernet_key(config: EncryptionConfig) -> bytes:
    secret = os.environ.get(config.key_material_env)
    if not secret:
        raise EncryptionError(
            f"Encryption is enabled but environment variable "
            f"{config.key_material_env!r} is unset or empty."
        )
    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=config.key_id.encode("utf-8"),
        info=_HKDF_INFO,
    ).derive(secret.encode("utf-8"))
    return base64.urlsafe_b64encode(derived)


def encrypt_text(plaintext: str, config: EncryptionConfig) -> str:
    if not config.enabled:
        return plaintext
    cipher = Fernet(_derive_fernet_key(config))
    token = cipher.encrypt(plaintext.encode("utf-8"))
    return token.decode("ascii")


def decrypt_text(ciphertext: str, config: EncryptionConfig) -> str:
    if not config.enabled:
        return ciphertext
    cipher = Fernet(_derive_fernet_key(config))
    try:
        plaintext = cipher.decrypt(ciphertext.encode("ascii"))
    except InvalidToken as exc:
        raise EncryptionError("ciphertext failed authentication or is malformed") from exc
    return plaintext.decode("utf-8")


def validate_tls(config: EncryptionConfig, tls_version: str | None) -> bool:
    if not config.require_tls:
        return True
    return tls_version in config.allowed_tls_versions
