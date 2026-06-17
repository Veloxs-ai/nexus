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

from nexus_guardrails.config import GuardrailsConfig
from nexus_guardrails.models import Decision, GuardrailResponse
from nexus_guardrails.offtopic import detect_off_topic
from nexus_guardrails.pii import detect_pii, mask_pii
from nexus_guardrails.policy import enforce_input_policies, enforce_output_policies
from nexus_guardrails.prompt_security import inspect_prompt
from nexus_guardrails.rag import compose_grounded_answer, retrieve_context
from nexus_guardrails.verification import verify_grounding


def evaluate(config: GuardrailsConfig, query: str, base_dir: Path) -> GuardrailResponse:
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

    citations = retrieve_context(config, masked_query, base_dir)
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

    decision = Decision.BLOCKED if any(finding.severity == "block" for finding in findings) else Decision.ALLOWED
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

