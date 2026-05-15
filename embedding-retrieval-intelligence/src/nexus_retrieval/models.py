from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class IndexedDocument(BaseModel):
    id: str
    collection: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: dict[str, Any] = Field(default_factory=dict)


class VectorEntry(BaseModel):
    id: str
    collection: str
    text: str
    embedding: list[float]
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResult(BaseModel):
    id: str
    collection: str
    text: str
    score: float
    semantic_score: float = 0.0
    lexical_score: float = 0.0
    graph_score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)

