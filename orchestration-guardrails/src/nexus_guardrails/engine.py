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
from .normalization import strip_invisible
from .orchestrator import evaluate
from .pii import PiiSpan, detect_pii, detect_pii_spans, mask_pii, mask_spans
from .pii_columns import classify_columns, mask_record, mask_records, merge_column_kinds
from .prompt_security import detect_injection, inspect_prompt

SpanDetector = Callable[[str], list[tuple[int, int]]]


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
                enabled=True, mask=True, detectors=["api_key", "jwt", "email", "ssn", "credit_card", "phone"]
            ),
            policies=[],
            off_topic=OffTopicConfig(enabled=False),
            rag=RagConfig(top_k=3, min_context_score=0.05, require_citations=False),
            verification=VerificationConfig(min_confidence=0.1, require_grounded_terms=False),
        )
        self.base_dir = base_dir
        self.retrieval_engine = retrieval_engine
        self.search_provider = search_provider
        self._detectors: dict[str, SpanDetector] = {}

    def register_detector(self, entity: str, detector: SpanDetector) -> None:
        """Add a custom PII detector (e.g. an NER model the caller owns).

        ``detector(text)`` returns ``(start, end)`` spans of ``entity`` values in ``text``.
        Its spans are merged with the built-in ones in ``mask_pii`` and
        ``detect_pii_spans`` (built-in detectors win on overlap); the entity is masked as
        ``[ENTITY]``. Exceptions raised by ``detector`` propagate to the caller.
        """
        self._detectors[str(entity)] = detector

    def detect_pii_spans(self, text: str, entities: list[str] | None = None) -> list[PiiSpan]:
        """PII spans on the original text: built-in detectors plus registered ones."""
        spans = detect_pii_spans(text, self.config.pii, entities)
        for entity, detector in self._detectors.items():
            if entities is not None and entity not in entities:
                continue
            spans.extend(PiiSpan(int(a), int(b), entity) for a, b in detector(text) or [] if b > a)
        return sorted(spans, key=lambda s: (s.start, -s.end))

    def merge_column_kinds(
        self, known: dict[str, str] | None, rows: list[dict[str, Any]]
    ) -> dict[str, str]:
        """Stable column kinds: ``known`` kinds kept, new or empty columns classified."""
        return merge_column_kinds(known, rows)

    def detect_injection(self, text: str) -> list[str]:
        """Names of the prompt-injection rules ``text`` matches (indirect injection)."""
        return detect_injection(text)

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
        """Direct PII masking utility (registered detectors included)."""
        if not self._detectors:
            return mask_pii(text, self.config.pii)
        if not self.config.pii.enabled or not self.config.pii.mask or not text:
            return text
        return strip_invisible(mask_spans(text, self.detect_pii_spans(text)))

    def classify_columns(self, rows: list[dict[str, Any]]) -> dict[str, str]:
        """Classify table columns once (email, phone, ..., identifier, numeric, text)."""
        return classify_columns(rows)

    def mask_record(
        self,
        record: dict[str, Any],
        column_kinds: dict[str, str] | None = None,
        token_secret: str | None = None,
    ) -> dict[str, Any]:
        """Column-aware masking of one row: PII columns masked, ids/numbers/times kept."""
        kinds = column_kinds if column_kinds is not None else classify_columns([record])
        return mask_record(record, kinds, self.config.pii, token_secret)

    def mask_records(
        self,
        rows: list[dict[str, Any]],
        column_kinds: dict[str, str] | None = None,
        token_secret: str | None = None,
    ) -> list[dict[str, Any]]:
        """Column-aware masking of a whole table (columns are classified once)."""
        return mask_records(rows, self.config.pii, column_kinds, token_secret)[0]

    def detect_pii(self, text: str) -> list[Finding]:
        """Direct PII detection scanner."""
        return detect_pii(text, self.config.pii)

    def inspect_prompt(self, text: str) -> list[Finding]:
        """Direct prompt injection scanner."""
        return inspect_prompt(text, self.config.prompt_security)
