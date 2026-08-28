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

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Protocol

from .config import EngagementConfig
from .models import Citation


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


class InMemoryGuardrailsGateway:
    """Zero-latency in-memory gateway communicating directly with GuardrailsEngine."""

    def __init__(self, engine: Any | None = None) -> None:
        self.engine = engine

    def ask(self, query: str) -> tuple[str, str, list[Citation], dict[str, str]]:
        if self.engine is None:
            try:
                from nexus.guardrails.engine import GuardrailsEngine
            except (ImportError, ModuleNotFoundError):
                from nexus_guardrails.engine import GuardrailsEngine
            self.engine = GuardrailsEngine()

        response = self.engine.evaluate(query)
        citations = [
            Citation(
                source_id=c.source_id,
                collection=c.collection,
                score=c.score,
            )
            for c in getattr(response, "citations", [])
        ]
        decision = (
            response.decision.value
            if hasattr(response.decision, "value")
            else str(response.decision)
        )
        meta = {
            "confidence": str(response.confidence),
            "mode": "in_memory",
        }
        if hasattr(response, "metadata") and response.metadata:
            meta.update({str(k): str(v) for k, v in response.metadata.items()})
        return decision, response.answer, citations, meta


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
            raise ValueError(
                "guardrails_project and guardrails_config are required for subprocess mode"
            )

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


def build_gateway(
    config: EngagementConfig,
    base_dir: Path,
    guardrails_engine: Any | None = None,
) -> AiGateway:
    if guardrails_engine is not None or config.integration.mode == "in_memory":
        return InMemoryGuardrailsGateway(guardrails_engine)
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
            try:
                collection, rest = raw.split(":", 1)
                source_id, score = rest.rsplit(":", 1)
                citations.append(
                    Citation(source_id=source_id, collection=collection, score=float(score))
                )
            except ValueError:
                continue
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
        raise GatewaySecurityError(f"path {path!r} resolves outside repository root {repo_root}")
    return resolved
