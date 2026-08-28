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

from __future__ import annotations

import base64
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .config import EncryptionConfig

_HKDF_INFO = b"nexus-security/encryption/v1"


class EncryptionError(Exception):
    """Raised when encryption configuration or input is invalid."""


def _derive_fernet_key(
    config: EncryptionConfig,
    secret_key: str | None = None,
    tenant_id: str | None = None,
) -> bytes:
    secret = secret_key or config.secret_key or os.environ.get(config.key_material_env)
    if not secret:
        raise EncryptionError(
            f"Encryption is enabled but no secret_key was provided in configuration "
            f"and environment variable {config.key_material_env!r} is unset or empty."
        )
    # Dynamic tenant-bound cryptographic salt prevents rainbow-table
    # cross-tenant correlation attacks.
    tid = tenant_id or getattr(config, "tenant_id", None) or "default"
    salt = f"nexus-salt-{tid}-{config.key_id}".encode()

    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=_HKDF_INFO,
    ).derive(secret.encode("utf-8"))
    return base64.urlsafe_b64encode(derived)


def encrypt_text(
    plaintext: str,
    config: EncryptionConfig,
    secret_key: str | None = None,
    tenant_id: str | None = None,
) -> str:
    if not config.enabled:
        return plaintext
    cipher = Fernet(_derive_fernet_key(config, secret_key=secret_key, tenant_id=tenant_id))
    token = cipher.encrypt(plaintext.encode("utf-8"))
    return token.decode("ascii")


def decrypt_text(
    ciphertext: str,
    config: EncryptionConfig,
    secret_key: str | None = None,
    tenant_id: str | None = None,
) -> str:
    if not config.enabled:
        return ciphertext
    cipher = Fernet(_derive_fernet_key(config, secret_key=secret_key, tenant_id=tenant_id))
    try:
        plaintext = cipher.decrypt(ciphertext.encode("ascii"))
    except InvalidToken as exc:
        raise EncryptionError("ciphertext failed authentication or is malformed") from exc
    return plaintext.decode("utf-8")


def validate_tls(config: EncryptionConfig, tls_version: str | None) -> bool:
    if not config.require_tls:
        return True
    return tls_version in config.allowed_tls_versions
