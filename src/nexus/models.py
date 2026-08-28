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

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class PlatformInfo(BaseModel):
    name: str
    version: str
    python_executable: str | None = None


class LayerConfig(BaseModel):
    package: str
    project_path: str
    cli_module: str
    config_path: str
    responsibility: str


class FlowConfig(BaseModel):
    description: str
    sequence: list[str] = Field(default_factory=list)


class NexusConfig(BaseModel):
    platform: PlatformInfo = Field(
        default_factory=lambda: PlatformInfo(name="Nexus Enterprise AI", version="2.4.0")
    )
    layers: dict[str, LayerConfig] = Field(default_factory=dict)
    flows: dict[str, FlowConfig] = Field(default_factory=dict)

    @classmethod
    def from_file(cls, path: str | Path) -> NexusConfig:
        from nexus.config import load_config

        return load_config(Path(path))

    @classmethod
    def from_json(cls, path_or_json: str | Path) -> NexusConfig:
        p = Path(path_or_json)
        if p.exists() and p.is_file():
            from nexus.config import load_config

            return load_config(p)
        return cls.model_validate(json.loads(str(path_or_json)))


class LayerStatus(BaseModel):
    name: str
    project_exists: bool
    pyproject_exists: bool
    config_exists: bool
    readme_exists: bool
    cli_module: str
    ready: bool


class ProcessedChunk(BaseModel):
    chunk_id: str
    document_id: str
    chunk_index: int
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] = Field(default_factory=list)


class ProcessingStageTrace(BaseModel):
    step_number: int
    stage_name: str
    status: str = "completed"
    duration_ms: float
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)


class ProcessedDocumentPayload(BaseModel):
    document_id: str
    name: str
    file_type: str
    file_size_bytes: int
    content_hash: str
    classification: str
    chunks: list[ProcessedChunk] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    execution_trace: list[ProcessingStageTrace] = Field(default_factory=list)
    summary: str = ""
