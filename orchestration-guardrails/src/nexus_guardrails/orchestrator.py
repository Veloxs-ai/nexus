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

from .config import GuardrailsConfig
from .models import Citation, Decision, GuardrailResponse
from .offtopic import detect_off_topic
from .pii import detect_pii, mask_pii
from .policy import enforce_input_policies, enforce_output_policies
from .prompt_security import inspect_prompt
from .rag import compose_grounded_answer, retrieve_context
from .verification import verify_grounding


def evaluate(
    config: GuardrailsConfig,
    query: str,
    base_dir: Path | None = None,
    retrieval_engine: Any | None = None,
    search_provider: Callable[[str, int], list[Citation]] | None = None,
) -> GuardrailResponse:
    pii_findings = detect_pii(query, config.pii)
    masked_query = mask_pii(query, config.pii)
    findings = [
        *inspect_prompt(masked_query, config.prompt_security),
        *enforce_input_policies(masked_query, config.policies),
        *detect_off_topic(masked_query, config.off_topic),
        *pii_findings,
    ]

    if any(finding.severity == "block" for finding in findings):
        return GuardrailResponse(
            decision=Decision.BLOCKED,
            query=query,
            masked_query=masked_query,
            answer="Request blocked by guardrails.",
            confidence=0.0,
            findings=findings,
        )

    citations = retrieve_context(
        config=config,
        query=masked_query,
        base_dir=base_dir,
        retrieval_engine=retrieval_engine,
        search_provider=search_provider,
    )
    answer = compose_grounded_answer(masked_query, citations)
    answer = mask_pii(answer, config.pii)
    confidence, verification_findings = verify_grounding(answer, citations, config.verification)
    output_findings = enforce_output_policies(
        answer,
        citations,
        pii_was_masked=bool(pii_findings),
        policies=config.policies,
    )
    # Re-screen the composed answer: retrieved context is untrusted and may carry
    # injected instructions or leakage content (indirect prompt injection).
    findings.extend(inspect_prompt(answer, config.prompt_security))
    findings.extend(verification_findings)
    findings.extend(output_findings)

    decision = (
        Decision.BLOCKED
        if any(finding.severity == "block" for finding in findings)
        else Decision.ALLOWED
    )
    return GuardrailResponse(
        decision=decision,
        query=query,
        masked_query=masked_query,
        answer=answer,
        confidence=confidence,
        citations=citations,
        findings=findings,
        metadata={"tenant": config.tenant.id},
    )
