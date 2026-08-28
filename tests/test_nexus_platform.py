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

from pathlib import Path

import pytest

from nexus.config import load_config
from nexus.platform import NexusPlatform, PlatformSecurityError


def test_platform_validates_layer_contracts():
    platform = NexusPlatform.from_config(Path("configs/nexus.json"))

    statuses = platform.layer_statuses()

    assert len(statuses) == 7
    assert all(status.ready for status in statuses)


def test_platform_resolves_relative_paths():
    platform = NexusPlatform.from_config(Path("configs/nexus.json"))

    assert platform.resolve("enterprise-data-pipeline").name == "enterprise-data-pipeline"


def test_resolve_rejects_path_traversal_outside_base_dir():
    platform = NexusPlatform.from_config(Path("configs/nexus.json"))

    with pytest.raises(PlatformSecurityError):
        platform.resolve("../../../etc/passwd")


def test_resolve_rejects_absolute_path_outside_base_dir():
    platform = NexusPlatform.from_config(Path("configs/nexus.json"))

    with pytest.raises(PlatformSecurityError):
        platform.resolve("/etc/passwd")


def test_run_layer_rejects_bogus_python_executable(tmp_path):
    config = load_config(Path("configs/nexus.json"))
    config.platform.python_executable = "/nonexistent/python"
    platform = NexusPlatform(config, Path("configs/nexus.json").parent.parent)

    with pytest.raises(PlatformSecurityError):
        platform.run_layer("enterprise-data-pipeline", ["--help"])


def test_run_layer_rejects_relative_python_executable():
    config = load_config(Path("configs/nexus.json"))
    config.platform.python_executable = "python"
    platform = NexusPlatform(config, Path("configs/nexus.json").parent.parent)

    with pytest.raises(PlatformSecurityError):
        platform.run_layer("enterprise-data-pipeline", ["--help"])


def test_run_layer_rejects_malformed_cli_module():
    config = load_config(Path("configs/nexus.json"))
    config.layers["enterprise-data-pipeline"].cli_module = "evil; rm -rf /"
    platform = NexusPlatform(config, Path("configs/nexus.json").parent.parent)

    with pytest.raises(PlatformSecurityError):
        platform.run_layer("enterprise-data-pipeline", ["--help"])
