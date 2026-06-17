# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

from typer.testing import CliRunner

from nexus_security.cli import app


runner = CliRunner()


def test_validate_config_command():
    result = runner.invoke(app, ["validate-config", "configs/security.yaml"])

    assert result.exit_code == 0
    assert "Loaded 3 roles and 2 tenants." in result.output


def test_check_access_command_allows_request(tmp_path):
    config_path = tmp_path / "security.yaml"
    config_path.write_text(
        """
tenants:
  tenant-a:
    name: Tenant A
    data_scopes:
      - customer
roles:
  analyst:
    permissions:
      - read:data
    data_scopes:
      - customer
audit:
  output_uri: audit.jsonl
observability:
  output_uri: events.jsonl
""",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["check-access", str(config_path), "analyst", "read:data", "tenant-a", "tenant-a", "customer"],
    )

    assert result.exit_code == 0
    assert "allowed: true" in result.output


def test_encrypt_and_decrypt_commands_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_SECURITY_KEY", "secret")
    config_path = tmp_path / "security.yaml"
    config_path.write_text(
        """
tenants:
  tenant-a:
    name: Tenant A
roles:
  analyst:
    permissions: []
encryption:
  enabled: true
  key_id: local
  key_material_env: NEXUS_SECURITY_KEY
""",
        encoding="utf-8",
    )

    encrypted = runner.invoke(app, ["encrypt", str(config_path), "hello"])
    decrypted = runner.invoke(app, ["decrypt", str(config_path), encrypted.output.strip()])

    assert encrypted.exit_code == 0
    assert decrypted.exit_code == 0
    assert decrypted.output.strip() == "hello"


def test_audit_command_writes_event(tmp_path):
    config_path = tmp_path / "security.yaml"
    config_path.write_text(
        """
tenants:
  tenant-a:
    name: Tenant A
roles:
  analyst:
    permissions: []
audit:
  output_uri: audit.jsonl
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["audit", str(config_path), "user.login", "u1", "tenant-a", "allowed"])

    assert result.exit_code == 0
    assert "audit_event_written: true" in result.output

