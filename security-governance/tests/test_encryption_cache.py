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

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from nexus_security import encryption
from nexus_security.encryption import decrypt_text, encrypt_text


def test_cached_key_is_the_hkdf_key_and_tenants_stay_apart(sample_config, monkeypatch):
    monkeypatch.setenv("NEXUS_SECURITY_TEST_KEY", "secret")
    config = sample_config.encryption
    salt = f"nexus-salt-t1-{config.key_id}".encode()
    expected = base64.urlsafe_b64encode(
        HKDF(hashes.SHA256(), 32, salt, encryption._HKDF_INFO).derive(b"secret")
    )
    assert encryption._derive_fernet_key(config, tenant_id="t1") == expected
    token = encrypt_text("x", config, tenant_id="t1")
    assert Fernet(expected).decrypt(token.encode()) == b"x"  # same format as before
    hits = encryption._hkdf_key.cache_info().hits
    assert decrypt_text(token, config, tenant_id="t1") == "x"
    assert encryption._hkdf_key.cache_info().hits > hits
    other = encryption._derive_fernet_key(config, tenant_id="t2")
    assert other != expected
