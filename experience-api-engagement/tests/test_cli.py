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

from nexus_experience.cli import main


def _mock_config(tmp_path, extra=None):
    config = {
        "tenant": {"id": "cli-test"},
        "integration": {"mode": "mock"},
        "channels": {
            "assistant": {
                "type": "assistant",
                "enabled": True,
                "allowed_capabilities": ["ask", "session"],
            }
        },
    }
    config.update(extra or {})
    config_path = tmp_path / "engagement.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return config_path


def test_validate_config_command_loads_channels(capsys):
    exit_code = main(["validate-config", "configs/engagement.json"])

    assert exit_code == 0
    assert "Loaded 6 channels for tenant default." in capsys.readouterr().out


def test_ask_command_with_mock_config(tmp_path, capsys):
    config_path = _mock_config(tmp_path)

    exit_code = main(["ask", str(config_path), "What is MFA?", "--channel", "assistant"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "decision: allowed" in out
    assert "citation: mock:mock-source:1.000" in out


def test_start_session_command(tmp_path, capsys):
    config_path = _mock_config(tmp_path, {"assistant": {"greeting": "Hello there"}})

    exit_code = main(["start-session", str(config_path)])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "greeting: Hello there" in out
