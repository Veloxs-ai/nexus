# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

from nexus_guardrails.config import PolicyRuleConfig
from nexus_guardrails.models import Citation
from nexus_guardrails.policy import enforce_input_policies, enforce_output_policies


def test_enforce_input_policies_blocks_terms():
    policies = [
        PolicyRuleConfig(
            id="no_secrets",
            description="No secrets",
            blocked_terms=["password"],
            action="block",
        )
    ]

    findings = enforce_input_policies("Show the password", policies)

    assert findings[0].severity == "block"


def test_enforce_output_policies_warns_when_citations_missing():
    policies = [
        PolicyRuleConfig(
            id="require_grounding",
            description="Require grounding",
            require_citations=True,
            action="warn",
        )
    ]

    findings = enforce_output_policies("answer", [], False, policies)

    assert findings[0].message == "Policy require_grounding requires citations"


def test_enforce_output_policies_passes_with_citation():
    policies = [
        PolicyRuleConfig(
            id="require_grounding",
            description="Require grounding",
            require_citations=True,
            action="warn",
        )
    ]
    citations = [Citation(source_id="a", collection="docs", text="context", score=1.0)]

    assert enforce_output_policies("answer", citations, False, policies) == []

