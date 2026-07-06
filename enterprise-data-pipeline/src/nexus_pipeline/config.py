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

from pathlib import Path
from typing import Any

import json
from pydantic import BaseModel, Field

from nexus_pipeline.models import IngestionMode


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
