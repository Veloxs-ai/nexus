from __future__ import annotations

import re

from nexus_guardrails.config import PiiConfig
from nexus_guardrails.models import Finding

PATTERNS = {
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "phone": re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
}

MASKS = {
    "email": "[EMAIL]",
    "ssn": "[SSN]",
    "phone": "[PHONE]",
    "credit_card": "[CREDIT_CARD]",
}


def detect_pii(text: str, config: PiiConfig) -> list[Finding]:
    if not config.enabled:
        return []
    findings: list[Finding] = []
    for detector in config.detectors:
        pattern = PATTERNS.get(detector)
        if pattern and pattern.search(text):
            findings.append(Finding(category="pii", message=f"Detected {detector}", severity="warn"))
    return findings


def mask_pii(text: str, config: PiiConfig) -> str:
    if not config.enabled or not config.mask:
        return text
    masked = text
    for detector in config.detectors:
        pattern = PATTERNS.get(detector)
        if pattern:
            masked = pattern.sub(MASKS[detector], masked)
    return masked

