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
