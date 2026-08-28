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

import json

from nexus_security.cli import main


def write_config(tmp_path, config):
    config_path = tmp_path / "security.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return config_path


def test_validate_config_command(capsys):
    exit_code = main(["validate-config", "configs/security.json"])

    assert exit_code == 0
    assert "Loaded 3 roles and 2 tenants." in capsys.readouterr().out


def test_check_access_command_allows_request(tmp_path, capsys):
    config_path = write_config(
        tmp_path,
        {
            "tenants": {"tenant-a": {"name": "Tenant A", "data_scopes": ["customer"]}},
            "roles": {"analyst": {"permissions": ["read:data"], "data_scopes": ["customer"]}},
            "audit": {"output_uri": "audit.jsonl"},
            "observability": {"output_uri": "events.jsonl"},
        },
    )

    exit_code = main(
        [
            "check-access",
            str(config_path),
            "analyst",
            "read:data",
            "tenant-a",
            "tenant-a",
            "customer",
        ]
    )

    assert exit_code == 0
    assert "allowed: true" in capsys.readouterr().out


def test_encrypt_and_decrypt_commands_round_trip(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("NEXUS_SECURITY_KEY", "secret")
    config_path = write_config(
        tmp_path,
        {
            "tenants": {"tenant-a": {"name": "Tenant A"}},
            "roles": {"analyst": {"permissions": []}},
            "encryption": {
                "enabled": True,
                "key_id": "local",
                "key_material_env": "NEXUS_SECURITY_KEY",
            },
        },
    )

    assert main(["encrypt", str(config_path), "hello"]) == 0
    ciphertext = capsys.readouterr().out.strip()
    assert main(["decrypt", str(config_path), ciphertext]) == 0
    assert capsys.readouterr().out.strip() == "hello"


def test_audit_command_writes_event(tmp_path, capsys):
    config_path = write_config(
        tmp_path,
        {
            "tenants": {"tenant-a": {"name": "Tenant A"}},
            "roles": {"analyst": {"permissions": []}},
            "audit": {"output_uri": "audit.jsonl"},
        },
    )

    exit_code = main(["audit", str(config_path), "user.login", "u1", "tenant-a", "allowed"])

    assert exit_code == 0
    assert "audit_event_written: true" in capsys.readouterr().out
