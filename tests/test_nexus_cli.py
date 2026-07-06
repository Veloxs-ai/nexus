# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

from nexus.cli import main


def test_validate_config_command(capsys):
    exit_code = main(["validate-config", "configs/nexus.json"])

    assert exit_code == 0
    assert "Loaded 7 layers." in capsys.readouterr().out


def test_validate_platform_command(capsys):
    exit_code = main(["validate-platform", "configs/nexus.json"])

    assert exit_code == 0
    assert "platform_ready: true" in capsys.readouterr().out


def test_prepare_demo_command(monkeypatch, capsys):
    outputs = ["Processed 2 outputs for customer_profiles.\n", "Indexed 4 documents.\n"]

    def fake_prepare_demo(self):
        return outputs

    monkeypatch.setattr("nexus.platform.NexusPlatform.prepare_demo", fake_prepare_demo)
    exit_code = main(["prepare-demo", "configs/nexus.json"])

    assert exit_code == 0
    assert "Indexed 4 documents." in capsys.readouterr().out
