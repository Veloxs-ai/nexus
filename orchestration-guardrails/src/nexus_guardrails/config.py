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
from pydantic import BaseModel, Field


class TenantConfig(BaseModel):
    id: str = "default"
    allowed_domains: list[str] = Field(default_factory=list)


class IntegrationConfig(BaseModel):
    processing_project: str | None = None
    retrieval_project: str | None = None
    retrieval_config: str | None = None
    vector_index_uri: str
    lexical_index_uri: str
    graph_index_uri: str | None = None


class PromptSecurityConfig(BaseModel):
    blocked_patterns: list[str] = Field(default_factory=list)
    leakage_terms: list[str] = Field(default_factory=list)


class PiiConfig(BaseModel):
    enabled: bool = True
    mask: bool = True
    detectors: list[str] = Field(default_factory=lambda: ["email", "ssn", "phone", "credit_card"])


class PolicyRuleConfig(BaseModel):
    id: str
    description: str
    blocked_terms: list[str] = Field(default_factory=list)
    require_citations: bool = False
    require_pii_masking: bool = False
    action: str = "warn"


class OffTopicConfig(BaseModel):
    enabled: bool = True
    min_keyword_overlap: int = 1
    allowed_keywords: list[str] = Field(default_factory=list)


class RagConfig(BaseModel):
    top_k: int = 3
    min_context_score: float = 0.05
    require_citations: bool = True


class VerificationConfig(BaseModel):
    min_confidence: float = 0.2
    require_grounded_terms: bool = True


class GuardrailsConfig(BaseModel):
    tenant: TenantConfig = Field(default_factory=TenantConfig)
    integration: IntegrationConfig
    prompt_security: PromptSecurityConfig = Field(default_factory=PromptSecurityConfig)
    pii: PiiConfig = Field(default_factory=PiiConfig)
    policies: list[PolicyRuleConfig] = Field(default_factory=list)
    off_topic: OffTopicConfig = Field(default_factory=OffTopicConfig)
    rag: RagConfig = Field(default_factory=RagConfig)
    verification: VerificationConfig = Field(default_factory=VerificationConfig)


def load_config(path: Path) -> GuardrailsConfig:
    with path.open("r", encoding="utf-8") as config_file:
        raw = yaml.safe_load(config_file)
    return GuardrailsConfig.model_validate(raw)

