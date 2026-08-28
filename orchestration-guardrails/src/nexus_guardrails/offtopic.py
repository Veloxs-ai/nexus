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

from .config import OffTopicConfig
from .models import Finding
from .normalization import normalize_text

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")


def tokenize(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_PATTERN.findall(normalize_text(text))}


def detect_off_topic(text: str, config: OffTopicConfig) -> list[Finding]:
    if not config.enabled:
        return []
    terms = tokenize(text)
    allowed = {keyword.lower() for keyword in config.allowed_keywords}
    overlap = terms & allowed
    if len(overlap) < config.min_keyword_overlap:
        return [
            Finding(
                category="off_topic",
                message="Query is outside configured enterprise AI context",
                severity="block",
            )
        ]
    return []
