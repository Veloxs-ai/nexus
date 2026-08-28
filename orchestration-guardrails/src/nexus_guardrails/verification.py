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

from .config import VerificationConfig
from .models import Citation, Finding
from .offtopic import tokenize


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
