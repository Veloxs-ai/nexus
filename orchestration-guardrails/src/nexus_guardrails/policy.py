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

import re

from .config import PolicyRuleConfig
from .models import Citation, Finding
from .normalization import luhn_valid, normalize_text

_EMAIL_OR_SSN = re.compile(
    r"(\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b|\b\d{3}-\d{2}-\d{4}\b)"
)
_PHONE = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
_CREDIT_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def _raw_pii_present(text: str) -> bool:
    normalized = normalize_text(text)
    if _EMAIL_OR_SSN.search(normalized):
        return True
    if _PHONE.search(normalized):
        return True
    return any(luhn_valid(match.group(0)) for match in _CREDIT_CARD.finditer(normalized))


def enforce_input_policies(text: str, policies: list[PolicyRuleConfig]) -> list[Finding]:
    # Normalize first so confusables / full-width / zero-width tricks cannot
    # evade blocked-term matching (consistent with the other guardrails).
    normalized = normalize_text(text).lower()
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
        if policy.require_pii_masking and not pii_was_masked and _raw_pii_present(answer):
            findings.append(
                Finding(
                    category="policy",
                    message=f"Policy {policy.id} requires PII masking",
                    severity=policy.action,
                )
            )
    return findings
