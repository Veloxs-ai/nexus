# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

from pathlib import Path

import pytest

from nexus.config import load_config
from nexus.platform import NexusPlatform, PlatformSecurityError


def test_platform_validates_layer_contracts():
    platform = NexusPlatform.from_config(Path("configs/nexus.yaml"))

    statuses = platform.layer_statuses()

    assert len(statuses) == 7
    assert all(status.ready for status in statuses)


def test_platform_resolves_relative_paths():
    platform = NexusPlatform.from_config(Path("configs/nexus.yaml"))

    assert platform.resolve("enterprise-data-pipeline").name == "enterprise-data-pipeline"


def test_resolve_rejects_path_traversal_outside_base_dir():
    platform = NexusPlatform.from_config(Path("configs/nexus.yaml"))

    with pytest.raises(PlatformSecurityError):
        platform.resolve("../../../etc/passwd")


def test_resolve_rejects_absolute_path_outside_base_dir():
    platform = NexusPlatform.from_config(Path("configs/nexus.yaml"))

    with pytest.raises(PlatformSecurityError):
        platform.resolve("/etc/passwd")


def test_run_layer_rejects_bogus_python_executable(tmp_path):
    config = load_config(Path("configs/nexus.yaml"))
    config.platform.python_executable = "/nonexistent/python"
    platform = NexusPlatform(config, Path("configs/nexus.yaml").parent.parent)

    with pytest.raises(PlatformSecurityError):
        platform.run_layer("enterprise-data-pipeline", ["--help"])


def test_run_layer_rejects_relative_python_executable():
    config = load_config(Path("configs/nexus.yaml"))
    config.platform.python_executable = "python"
    platform = NexusPlatform(config, Path("configs/nexus.yaml").parent.parent)

    with pytest.raises(PlatformSecurityError):
        platform.run_layer("enterprise-data-pipeline", ["--help"])


def test_run_layer_rejects_malformed_cli_module():
    config = load_config(Path("configs/nexus.yaml"))
    config.layers["enterprise-data-pipeline"].cli_module = "evil; rm -rf /"
    platform = NexusPlatform(config, Path("configs/nexus.yaml").parent.parent)

    with pytest.raises(PlatformSecurityError):
        platform.run_layer("enterprise-data-pipeline", ["--help"])

