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

from pydantic import BaseModel, Field


class TenantConfig(BaseModel):
    id: str = "default"
    allowed_domains: list[str] = Field(default_factory=list)


class IntegrationConfig(BaseModel):
    processing_project: str | None = None
    retrieval_project: str | None = None
    retrieval_config: str | None = None
    vector_index_uri: str = "data/indexes/vector_index.json"
    lexical_index_uri: str = "data/indexes/lexical_index.json"
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
    integration: IntegrationConfig = Field(default_factory=IntegrationConfig)
    prompt_security: PromptSecurityConfig = Field(default_factory=PromptSecurityConfig)
    pii: PiiConfig = Field(default_factory=PiiConfig)
    policies: list[PolicyRuleConfig] = Field(default_factory=list)
    off_topic: OffTopicConfig = Field(default_factory=OffTopicConfig)
    rag: RagConfig = Field(default_factory=RagConfig)
    verification: VerificationConfig = Field(default_factory=VerificationConfig)


def _load_raw(path: Path):
    """Parse JSON (stdlib) natively; YAML only when PyYAML is installed (optional extra)."""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                f"{path} is YAML, but PyYAML is not installed. Use a JSON config "
                "or install the optional extra: pip install orchestration-guardrails[yaml]"
            ) from exc
        return yaml.safe_load(text)
    return json.loads(text)


def load_config(path: Path) -> GuardrailsConfig:
    return GuardrailsConfig.model_validate(_load_raw(path))
