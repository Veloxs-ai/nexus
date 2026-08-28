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
from typing import Any

from .config import MetadataConfig

EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
DATE_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
MONEY_PATTERN = re.compile(r"\$\s?\d+(?:,\d{3})*(?:\.\d{2})?\b")
CAPITALIZED_ENTITY_PATTERN = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b")


def build_text(record: dict[str, Any], fields: list[str]) -> str:
    values = [str(record[field]) for field in fields if record.get(field) is not None]
    return " ".join(values)


def extract_metadata(text: str, config: MetadataConfig) -> dict[str, Any]:
    tags = extract_tags(text, config.keyword_tags)
    entities = sorted(set(CAPITALIZED_ENTITY_PATTERN.findall(text)))
    emails = sorted(set(EMAIL_PATTERN.findall(text)))
    dates = sorted(set(DATE_PATTERN.findall(text)))
    money = sorted(set(MONEY_PATTERN.findall(text)))

    return {
        "tags": tags,
        "entities": entities,
        "emails": emails,
        "dates": dates,
        "money": money,
        "classification": classify(tags),
    }


def extract_tags(text: str, keyword_tags: dict[str, list[str]]) -> list[str]:
    normalized = text.lower()
    tags = [
        tag
        for tag, keywords in keyword_tags.items()
        if any(keyword.lower() in normalized for keyword in keywords)
    ]
    return sorted(tags)


def classify(tags: list[str]) -> str:
    if "security" in tags:
        return "security"
    if "finance" in tags:
        return "finance"
    if "customer" in tags:
        return "customer"
    return "general"
