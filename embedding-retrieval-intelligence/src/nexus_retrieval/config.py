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

import yaml
from pydantic import BaseModel, Field, model_validator


class IntegrationConfig(BaseModel):
    processing_project: str | None = None
    processing_config: str | None = None
    ingestion_project: str | None = None


class EmbeddingConfig(BaseModel):
    provider: str = "local_hashing"
    dimensions: int = 64
    normalize: bool = True

    @model_validator(mode="after")
    def validate_dimensions(self) -> "EmbeddingConfig":
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
    def validate_weights(self) -> "RankingConfig":
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
    def validate_text_fields(self) -> "CollectionConfig":
        if not self.text_field and not self.text_fields:
            raise ValueError("collection must define text_field or text_fields")
        return self


class RetrievalConfig(BaseModel):
    integration: IntegrationConfig = Field(default_factory=IntegrationConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    stores: StoreConfig
    ranking: RankingConfig = Field(default_factory=RankingConfig)
    collections: dict[str, CollectionConfig]


def load_config(path: Path) -> RetrievalConfig:
    with path.open("r", encoding="utf-8") as config_file:
        raw = yaml.safe_load(config_file)
    return RetrievalConfig.model_validate(raw)

