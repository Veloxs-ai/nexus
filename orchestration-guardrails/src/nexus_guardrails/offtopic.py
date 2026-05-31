from __future__ import annotations

import re

from nexus_guardrails.config import OffTopicConfig
from nexus_guardrails.models import Finding
from nexus_guardrails.normalization import normalize_text

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

