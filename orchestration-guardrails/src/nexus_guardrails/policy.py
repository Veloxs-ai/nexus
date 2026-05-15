from __future__ import annotations

import re

from nexus_guardrails.config import PolicyRuleConfig
from nexus_guardrails.models import Citation, Finding

RAW_PII_PATTERN = re.compile(
    r"(\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b|\b\d{3}-\d{2}-\d{4}\b)"
)


def enforce_input_policies(text: str, policies: list[PolicyRuleConfig]) -> list[Finding]:
    normalized = text.lower()
    findings: list[Finding] = []
    for policy in policies:
        for term in policy.blocked_terms:
            if term.lower() in normalized:
                findings.append(
                    Finding(
                        category="policy",
                        message=f"Policy {policy.id} matched blocked term: {term}",
                        severity=policy.action,
                    )
                )
    return findings


def enforce_output_policies(
    answer: str,
    citations: list[Citation],
    pii_was_masked: bool,
    policies: list[PolicyRuleConfig],
) -> list[Finding]:
    findings: list[Finding] = []
    for policy in policies:
        if policy.require_citations and not citations:
            findings.append(
                Finding(
                    category="policy",
                    message=f"Policy {policy.id} requires citations",
                    severity=policy.action,
                )
            )
        if policy.require_pii_masking and not pii_was_masked and RAW_PII_PATTERN.search(answer):
            findings.append(
                Finding(
                    category="policy",
                    message=f"Policy {policy.id} requires PII masking",
                    severity=policy.action,
                )
            )
    return findings
