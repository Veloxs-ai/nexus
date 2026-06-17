# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

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

