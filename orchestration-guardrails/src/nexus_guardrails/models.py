from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Decision(StrEnum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"


class Finding(BaseModel):
    category: str
    message: str
    severity: str = "warn"


class Citation(BaseModel):
    source_id: str
    collection: str
    text: str
    score: float


class GuardrailResponse(BaseModel):
    decision: Decision
    query: str
    masked_query: str
    answer: str
    confidence: float
    citations: list[Citation] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

