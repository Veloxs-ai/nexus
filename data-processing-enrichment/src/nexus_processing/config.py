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
from pydantic import BaseModel, Field, model_validator

from nexus_processing.models import JobMode


class IntegrationConfig(BaseModel):
    upstream_project: str | None = None
    upstream_sources_config: str | None = None
    raw_landing_contract: str = "jsonl"


class ChunkingConfig(BaseModel):
    max_tokens: int = 500
    overlap_tokens: int = 50

    @model_validator(mode="after")
    def validate_overlap(self) -> "ChunkingConfig":
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be greater than zero")
        if self.overlap_tokens < 0:
            raise ValueError("overlap_tokens cannot be negative")
        if self.overlap_tokens >= self.max_tokens:
            raise ValueError("overlap_tokens must be less than max_tokens")
        return self


class MetadataConfig(BaseModel):
    keyword_tags: dict[str, list[str]] = Field(default_factory=dict)


class DefaultsConfig(BaseModel):
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    metadata: MetadataConfig = Field(default_factory=MetadataConfig)


class TransformConfig(BaseModel):
    trim_strings: bool = True
    normalize_case_fields: dict[str, str] = Field(default_factory=dict)
    rename_fields: dict[str, str] = Field(default_factory=dict)
    default_values: dict[str, Any] = Field(default_factory=dict)


class ProcessingJobConfig(BaseModel):
    mode: JobMode
    input_uri: str
    output_uri: str
    primary_key: str
    text_fields: list[str] = Field(default_factory=list)
    transformations: TransformConfig = Field(default_factory=TransformConfig)
    document_text_field: str | None = None
    document_title_field: str | None = None
    chunking: ChunkingConfig | None = None
    metadata: MetadataConfig | None = None


class ProcessingConfig(BaseModel):
    integration: IntegrationConfig = Field(default_factory=IntegrationConfig)
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    jobs: dict[str, ProcessingJobConfig]


def _load_raw(path: Path):
    """Parse JSON (stdlib) natively; YAML only when PyYAML is installed (optional extra)."""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                f"{path} is YAML, but PyYAML is not installed. Use a JSON config "
                "or install the optional extra: pip install data-processing-enrichment[yaml]"
            ) from exc
        return yaml.safe_load(text)
    return json.loads(text)


def load_config(path: Path) -> ProcessingConfig:
    return ProcessingConfig.model_validate(_load_raw(path))

