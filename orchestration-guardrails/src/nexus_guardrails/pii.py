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

import re

from nexus_guardrails.config import PiiConfig
from nexus_guardrails.models import Finding
from nexus_guardrails.normalization import luhn_valid, normalize_text

PATTERNS = {
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "phone": re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
}

MASKS = {
    "email": "[EMAIL]",
    "ssn": "[SSN]",
    "phone": "[PHONE]",
    "credit_card": "[CREDIT_CARD]",
}


def _matches(detector: str, candidate: str) -> bool:
    if detector == "credit_card":
        return luhn_valid(candidate)
    return True


def _detector_findings(detector: str, text: str) -> bool:
    pattern = PATTERNS.get(detector)
    if not pattern:
        return False
    for match in pattern.finditer(text):
        if _matches(detector, match.group(0)):
            return True
    return False


def detect_pii(text: str, config: PiiConfig) -> list[Finding]:
    if not config.enabled:
        return []
    normalized = normalize_text(text)
    findings: list[Finding] = []
    for detector in config.detectors:
        if _detector_findings(detector, normalized):
            findings.append(Finding(category="pii", message=f"Detected {detector}", severity="warn"))
    return findings


def mask_pii(text: str, config: PiiConfig) -> str:
    if not config.enabled or not config.mask:
        return text
    masked = normalize_text(text)
    for detector in config.detectors:
        pattern = PATTERNS.get(detector)
        if not pattern:
            continue
        mask_value = MASKS[detector]
        if detector == "credit_card":
            masked = pattern.sub(
                lambda match: mask_value if luhn_valid(match.group(0)) else match.group(0),
                masked,
            )
        else:
            masked = pattern.sub(mask_value, masked)
    return masked
