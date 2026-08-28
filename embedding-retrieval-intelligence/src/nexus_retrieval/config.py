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

from pydantic import BaseModel, Field, model_validator


class IntegrationConfig(BaseModel):
    processing_project: str | None = None
    processing_config: str | None = None
    ingestion_project: str | None = None


class EmbeddingConfig(BaseModel):
    provider: str = "local_hashing"
    dimensions: int = 3072
    normalize: bool = True

    @model_validator(mode="after")
    def validate_dimensions(self) -> EmbeddingConfig:
        if self.dimensions <= 0:
            raise ValueError("embedding dimensions must be greater than zero")
        return self


class StoreConfig(BaseModel):
    vector_index_uri: str
    lexical_index_uri: str
    graph_index_uri: str


class RankingConfig(BaseModel):
    semantic_weight: float = 0.6
    lexical_weight: float = 0.3
    graph_weight: float = 0.1

    @model_validator(mode="after")
    def validate_weights(self) -> RankingConfig:
        total = self.semantic_weight + self.lexical_weight + self.graph_weight
        if total <= 0:
            raise ValueError("ranking weights must sum to a positive value")
        return self


class GraphMappingConfig(BaseModel):
    entity_fields: list[str] = Field(default_factory=list)
    tag_fields: list[str] = Field(default_factory=list)
    parent_field: str | None = None


class CollectionConfig(BaseModel):
    input_uri: str
    id_field: str
    text_field: str | None = None
    text_fields: list[str] = Field(default_factory=list)
    metadata_field: str = "metadata"
    graph: GraphMappingConfig = Field(default_factory=GraphMappingConfig)

    @model_validator(mode="after")
    def validate_text_fields(self) -> CollectionConfig:
        if not self.text_field and not self.text_fields:
            raise ValueError("collection must define text_field or text_fields")
        return self


class RetrievalConfig(BaseModel):
    integration: IntegrationConfig = Field(default_factory=IntegrationConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    stores: StoreConfig
    ranking: RankingConfig = Field(default_factory=RankingConfig)
    collections: dict[str, CollectionConfig]


def _load_raw(path: Path):
    """Parse JSON (stdlib) natively; YAML only when PyYAML is installed (optional extra)."""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                f"{path} is YAML, but PyYAML is not installed. Use a JSON config "
                "or install the optional extra: pip install embedding-retrieval-intelligence[yaml]"
            ) from exc
        return yaml.safe_load(text)
    return json.loads(text)


def load_config(path: Path) -> RetrievalConfig:
    return RetrievalConfig.model_validate(_load_raw(path))
