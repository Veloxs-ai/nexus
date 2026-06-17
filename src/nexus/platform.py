# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from nexus.config import load_config
from nexus.models import LayerStatus, NexusConfig

_MODULE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")


class PlatformSecurityError(Exception):
    """Raised when platform config would invoke an unsafe subprocess or path."""


class NexusPlatform:
    def __init__(self, config: NexusConfig, base_dir: Path) -> None:
        self.config = config
        self.base_dir = base_dir.resolve()

    @classmethod
    def from_config(cls, config_path: Path) -> "NexusPlatform":
        return cls(load_config(config_path), config_path.parent.parent)

    def layer_statuses(self) -> list[LayerStatus]:
        statuses: list[LayerStatus] = []
        for name, layer in self.config.layers.items():
            project_path = self.resolve(layer.project_path)
            config_path = self.resolve(layer.config_path)
            pyproject_exists = (project_path / "pyproject.toml").exists()
            readme_exists = (project_path / "README.md").exists()
            project_exists = project_path.exists()
            config_exists = config_path.exists()
            statuses.append(
                LayerStatus(
                    name=name,
                    project_exists=project_exists,
                    pyproject_exists=pyproject_exists,
                    config_exists=config_exists,
                    readme_exists=readme_exists,
                    cli_module=layer.cli_module,
                    ready=project_exists and pyproject_exists and config_exists and readme_exists,
                )
            )
        return statuses

    def validate(self) -> bool:
        return all(status.ready for status in self.layer_statuses())

    def run_layer(self, layer_name: str, args: list[str]) -> subprocess.CompletedProcess[str]:
        layer = self.config.layers[layer_name]
        project_path = self.resolve(layer.project_path)
        executable = _validate_python_executable(self.config.platform.python_executable)
        module = _validate_cli_module(layer.cli_module)
        env = dict(os.environ)
        env["PYTHONPATH"] = str(project_path / "src")
        return subprocess.run(
            [executable, "-m", module, *args],
            cwd=project_path,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )

    def ask(self, query: str, channel: str = "assistant") -> str:
        layer = self.config.layers["experience-api-engagement"]
        config_path = str(self.resolve(layer.config_path))
        result = self.run_layer(
            "experience-api-engagement",
            ["ask", config_path, query, "--channel", channel],
        )
        return result.stdout

    def prepare_demo(self) -> list[str]:
        processing = self.config.layers["data-processing-enrichment"]
        retrieval = self.config.layers["embedding-retrieval-intelligence"]
        processing_result = self.run_layer(
            "data-processing-enrichment",
            ["run-all", str(self.resolve(processing.config_path))],
        )
        retrieval_result = self.run_layer(
            "embedding-retrieval-intelligence",
            ["build-index", str(self.resolve(retrieval.config_path))],
        )
        return [processing_result.stdout, retrieval_result.stdout]

    def resolve(self, path: str) -> Path:
        candidate = Path(path)
        resolved = candidate if candidate.is_absolute() else (self.base_dir / candidate).resolve()
        resolved = resolved.resolve()
        if not _is_within(resolved, self.base_dir):
            raise PlatformSecurityError(
                f"path {path!r} resolves outside base directory {self.base_dir}"
            )
        return resolved


def _validate_python_executable(executable: str | None) -> str:
    if not executable:
        return sys.executable
    candidate = Path(executable)
    if not candidate.is_absolute():
        raise PlatformSecurityError(
            f"python_executable must be an absolute path, got: {executable!r}"
        )
    if not candidate.is_file():
        raise PlatformSecurityError(f"python_executable does not exist: {executable!r}")
    if not os.access(candidate, os.X_OK):
        raise PlatformSecurityError(f"python_executable is not executable: {executable!r}")
    return str(candidate)


def _validate_cli_module(module: str) -> str:
    if not _MODULE_PATTERN.match(module):
        raise PlatformSecurityError(f"cli_module is not a valid dotted module name: {module!r}")
    return module


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
