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
import subprocess
import sys
from pathlib import Path
from typing import Protocol

from nexus_experience.config import EngagementConfig
from nexus_experience.models import Citation


class GatewaySecurityError(Exception):
    """Raised when the configured subprocess gateway would be unsafe to run."""


def _validate_python_executable(executable: str | None) -> str:
    if not executable:
        return sys.executable
    candidate = Path(executable)
    if not candidate.is_absolute():
        raise GatewaySecurityError(
            f"python_executable must be an absolute path, got: {executable!r}"
        )
    if not candidate.is_file() or not os.access(candidate, os.X_OK):
        raise GatewaySecurityError(
            f"python_executable does not exist or is not executable: {executable!r}"
        )
    return str(candidate)


class AiGateway(Protocol):
    def ask(self, query: str) -> tuple[str, str, list[Citation], dict[str, str]]:
        """Return decision, answer, citations, and metadata."""


class MockGuardrailsGateway:
    def ask(self, query: str) -> tuple[str, str, list[Citation], dict[str, str]]:
        if "ignore previous instructions" in query.lower():
            return "blocked", "Request blocked by guardrails.", [], {"mode": "mock"}
        return (
            "allowed",
            f"Mock grounded response for: {query}",
            [Citation(source_id="mock-source", collection="mock", score=1.0)],
            {"mode": "mock"},
        )


class SubprocessGuardrailsGateway:
    def __init__(self, config: EngagementConfig, base_dir: Path) -> None:
        self.config = config
        self.base_dir = base_dir

    def ask(self, query: str) -> tuple[str, str, list[Citation], dict[str, str]]:
        integration = self.config.integration
        if not integration.guardrails_project or not integration.guardrails_config:
            raise ValueError("guardrails_project and guardrails_config are required for subprocess mode")

        project_dir = resolve_path(integration.guardrails_project, self.base_dir)
        config_path = resolve_path(integration.guardrails_config, self.base_dir)
        executable = _validate_python_executable(integration.python_executable)
        env = dict(os.environ)
        env["PYTHONPATH"] = str(project_dir / "src")
        completed = subprocess.run(
            [
                executable,
                "-m",
                "nexus_guardrails.cli",
                "ask",
                str(config_path),
                query,
            ],
            cwd=project_dir,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        return parse_guardrails_output(completed.stdout)


def build_gateway(config: EngagementConfig, base_dir: Path) -> AiGateway:
    if config.integration.mode == "subprocess_cli":
        return SubprocessGuardrailsGateway(config, base_dir)
    return MockGuardrailsGateway()


def parse_guardrails_output(output: str) -> tuple[str, str, list[Citation], dict[str, str]]:
    decision = "unknown"
    answer = ""
    citations: list[Citation] = []
    metadata: dict[str, str] = {}

    for line in output.splitlines():
        if line.startswith("decision: "):
            decision = line.removeprefix("decision: ").strip()
        elif line.startswith("answer: "):
            answer = line.removeprefix("answer: ").strip()
        elif line.startswith("confidence: "):
            metadata["confidence"] = line.removeprefix("confidence: ").strip()
        elif line.startswith("citation: "):
            raw = line.removeprefix("citation: ").strip()
            collection, rest = raw.split(":", 1)
            source_id, score = rest.rsplit(":", 1)
            citations.append(Citation(source_id=source_id, collection=collection, score=float(score)))
    return decision, answer, citations, metadata

def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def resolve_path(path: str, base_dir: Path) -> Path:
    candidate = Path(path)
    resolved = candidate if candidate.is_absolute() else (base_dir / candidate).resolve()
    resolved = resolved.resolve()
    base_resolved = base_dir.resolve()
    repo_root = base_resolved.parent
    if not _is_within(resolved, repo_root):
        raise GatewaySecurityError(
            f"path {path!r} resolves outside repository root {repo_root}"
        )
    return resolved
