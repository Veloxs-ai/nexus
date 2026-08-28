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
