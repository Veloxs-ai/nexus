from __future__ import annotations

from nexus_guardrails.config import PromptSecurityConfig
from nexus_guardrails.models import Finding
from nexus_guardrails.normalization import normalize_text


def inspect_prompt(prompt: str, config: PromptSecurityConfig) -> list[Finding]:
    normalized = normalize_text(prompt).lower()
    findings: list[Finding] = []
    for pattern in config.blocked_patterns:
        if pattern.lower() in normalized:
            findings.append(
                Finding(
                    category="prompt_security",
                    message=f"Blocked prompt pattern: {pattern}",
                    severity="block",
                )
            )
    for term in config.leakage_terms:
        if term.lower() in normalized:
            findings.append(
                Finding(
                    category="data_leakage",
                    message=f"Potential leakage request: {term}",
                    severity="block",
                )
            )
    return findings

