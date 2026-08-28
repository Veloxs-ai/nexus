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

from nexus_guardrails.config import VerificationConfig
from nexus_guardrails.models import Citation
from nexus_guardrails.verification import verify_grounding


def test_verify_grounding_scores_overlap():
    confidence, findings = verify_grounding(
        "MFA is required for sensitive systems",
        [Citation(source_id="a", collection="docs", text="MFA sensitive systems", score=1.0)],
        VerificationConfig(min_confidence=0.1),
    )

    assert confidence > 0
    assert findings == []


def test_verify_grounding_blocks_without_citations():
    confidence, findings = verify_grounding("answer", [], VerificationConfig())

    assert confidence == 0.0
    assert findings[0].severity == "block"
