from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from nexus.config import load_config
from nexus.models import LayerStatus, NexusConfig


class NexusPlatform:
    def __init__(self, config: NexusConfig, base_dir: Path) -> None:
        self.config = config
        self.base_dir = base_dir

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
        env = dict(os.environ)
        env["PYTHONPATH"] = str(project_path / "src")
        return subprocess.run(
            [self.config.platform.python_executable or sys.executable, "-m", layer.cli_module, *args],
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
        return candidate if candidate.is_absolute() else (self.base_dir / candidate).resolve()
