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

from .models import IngestionMode


class PlatformConfig(BaseModel):
    raw_landing_uri: str
    checkpoint_store: str
    dead_letter_uri: str


class SourceSchema(BaseModel):
    required_fields: list[str] = Field(default_factory=list)


class SourceConfig(BaseModel):
    mode: IngestionMode
    connector: str
    destination: str
    primary_key: str
    event_time_field: str
    connection: dict[str, Any]
    data_schema: SourceSchema = Field(default_factory=SourceSchema, alias="schema")
    schedule: str | None = None


class PipelineConfig(BaseModel):
    platform: PlatformConfig
    sources: dict[str, SourceConfig]


def _load_raw(path: Path):
    """Parse JSON (stdlib) natively; YAML only when PyYAML is installed (optional extra)."""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                f"{path} is YAML, but PyYAML is not installed. Use a JSON config "
                "or install the optional extra: pip install enterprise-data-pipeline[yaml]"
            ) from exc
        return yaml.safe_load(text)
    return json.loads(text)


def load_config(path: Path) -> PipelineConfig:
    return PipelineConfig.model_validate(_load_raw(path))
