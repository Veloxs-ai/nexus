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

