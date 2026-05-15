from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
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


def load_config(path: Path) -> PipelineConfig:
    with path.open("r", encoding="utf-8") as config_file:
        raw = yaml.safe_load(config_file)
    return PipelineConfig.model_validate(raw)
