from __future__ import annotations

from nexus_guardrails.config import VerificationConfig
from nexus_guardrails.models import Citation, Finding
from nexus_guardrails.offtopic import tokenize


def verify_grounding(
    answer: str,
    citations: list[Citation],
    config: VerificationConfig,
) -> tuple[float, list[Finding]]:
    if not citations:
        return 0.0, [
            Finding(
                category="verification",
                message="No citations available for grounding",
                severity="block",
            )
        ]

    answer_terms = tokenize(answer)
    context_terms = set()
    for citation in citations:
        context_terms.update(tokenize(citation.text))
    overlap = answer_terms & context_terms
    confidence = len(overlap) / max(len(answer_terms), 1)
    findings: list[Finding] = []

    if confidence < config.min_confidence:
        findings.append(
            Finding(
                category="verification",
                message="Answer confidence is below threshold",
                severity="block",
            )
        )
    if config.require_grounded_terms and not overlap:
        findings.append(
            Finding(
                category="verification",
                message="Answer does not share grounded terms with citations",
                severity="block",
            )
        )
    return confidence, findings

