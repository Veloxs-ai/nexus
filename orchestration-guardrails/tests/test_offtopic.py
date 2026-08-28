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

from nexus_guardrails.config import OffTopicConfig
from nexus_guardrails.offtopic import detect_off_topic, tokenize


def test_detect_off_topic_blocks_unrelated_query():
    config = OffTopicConfig(allowed_keywords=["security", "invoice"], min_keyword_overlap=1)

    findings = detect_off_topic("Tell me a cooking recipe", config)

    assert findings[0].severity == "block"


def test_detect_off_topic_allows_relevant_query():
    config = OffTopicConfig(allowed_keywords=["security", "invoice"], min_keyword_overlap=1)

    assert detect_off_topic("Explain security access", config) == []


def test_tokenize_normalizes_terms():
    assert tokenize("MFA, Security!") == {"mfa", "security"}
