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

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .config import (
    GuardrailsConfig,
    OffTopicConfig,
    PiiConfig,
    PromptSecurityConfig,
    RagConfig,
    TenantConfig,
    VerificationConfig,
)
from .models import Citation, Finding, GuardrailResponse
from .orchestrator import evaluate
from .pii import detect_pii, mask_pii
from .prompt_security import inspect_prompt


class GuardrailsEngine:
    """In-memory AI safety, policy enforcement, and grounded orchestration engine.

    Validates prompts against injection attacks, masks PII with Luhn card checking,
    retrieves context, and calculates grounding confidence without subprocesses.
    """

    def __init__(
        self,
        config: GuardrailsConfig | None = None,
        base_dir: Path | None = None,
        retrieval_engine: Any | None = None,
        search_provider: Callable[[str, int], list[Citation]] | None = None,
    ) -> None:
        self.config = config or GuardrailsConfig(
            tenant=TenantConfig(
                id="default", allowed_domains=["security", "finance", "customer", "policy"]
            ),
            prompt_security=PromptSecurityConfig(
                blocked_patterns=[
                    "ignore previous instructions",
                    "reveal system prompt",
                    "exfiltrate",
                ],
                leakage_terms=["api key", "password", "secret", "token"],
            ),
            pii=PiiConfig(
                enabled=True, mask=True, detectors=["email", "ssn", "phone", "credit_card"]
            ),
            policies=[],
            off_topic=OffTopicConfig(enabled=False),
            rag=RagConfig(top_k=3, min_context_score=0.05, require_citations=False),
            verification=VerificationConfig(min_confidence=0.1, require_grounded_terms=False),
        )
        self.base_dir = base_dir
        self.retrieval_engine = retrieval_engine
        self.search_provider = search_provider

    def evaluate(self, query: str) -> GuardrailResponse:
        """Full guardrail screening, context retrieval, and grounded answer synthesis."""
        return evaluate(
            config=self.config,
            query=query,
            base_dir=self.base_dir,
            retrieval_engine=self.retrieval_engine,
            search_provider=self.search_provider,
        )

    def ask(self, query: str) -> GuardrailResponse:
        """Convenience alias for evaluate."""
        return self.evaluate(query)

    def mask_pii(self, text: str) -> str:
        """Direct PII masking utility."""
        return mask_pii(text, self.config.pii)

    def detect_pii(self, text: str) -> list[Finding]:
        """Direct PII detection scanner."""
        return detect_pii(text, self.config.pii)

    def inspect_prompt(self, text: str) -> list[Finding]:
        """Direct prompt injection scanner."""
        return inspect_prompt(text, self.config.prompt_security)
