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

"""Scoring a knowledge-graph extraction against labelled entities.

``score_extraction(extraction, gold, documents=)`` returns:

  entity_precision   active entities that match a gold entity / active entities
  mention_recall     macro average over gold entities of (gold documents with a mention of
                     the entity / gold documents) - "everything about X"
  typing_accuracy    matched entities whose type equals the gold type (``entity`` gold types
                     accept any type)
  false_positives    a sample of unmatched active entities (for error analysis)

A predicted entity matches a gold entity when its key (without a ``#primary-key`` part) equals
the normalised gold name or one of its aliases under any type, or when it was merged into one.
Candidates (noun-phrase concepts not yet promoted) are not scored.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from nexus.graph import ENTITY_TYPES, GraphExtraction, normalise_name

__all__ = ["GoldEntity", "score_extraction"]


@dataclass(frozen=True)
class GoldEntity:
    name: str
    type: str
    documents: frozenset[str] = frozenset()  # documents that mention it (for recall)
    aliases: tuple[str, ...] = ()


@dataclass
class _Index:
    by_key: dict[str, list[int]] = field(default_factory=dict)

    def add(self, key: str, idx: int) -> None:
        if key:
            bucket = self.by_key.setdefault(key, [])
            if idx not in bucket:
                bucket.append(idx)


def score_extraction(
    extraction: GraphExtraction,
    gold: Iterable[GoldEntity],
    *,
    documents: Mapping[str, str] | None = None,
    sample: int = 25,
) -> dict[str, Any]:
    """Precision, recall and typing accuracy (see the module docstring)."""
    gold = list(gold)
    index = _Index()
    for i, g in enumerate(gold):
        for surface in (g.name, *g.aliases):
            for t in {g.type, *ENTITY_TYPES}:
                index.add(normalise_name(surface, entity_type=t), i)
    docs = documents or {}
    active = [e for e in extraction.entities if e.status == "active"]
    matched: dict[tuple[str, str], int] = {}
    false_pos: list[str] = []
    typed_ok = 0
    for e in active:
        hits = index.by_key.get(e.key) or index.by_key.get(e.key.split("#", 1)[0])
        if hits:
            g_idx = next((h for h in hits if gold[h].type == e.type), hits[0])
            matched[e.ref] = g_idx
            if gold[g_idx].type in ("entity", e.type):
                typed_ok += 1
        else:
            false_pos.append(f"{e.type}:{e.name}")
    for a in extraction.aliases:  # aliases point predicted names at their canonical entity
        ref = (a.entity_type, a.entity_key)
        if ref not in matched:
            hits = index.by_key.get(a.alias_key)
            if hits:
                matched[ref] = hits[0]
    found_docs: dict[int, set[str]] = {}
    for m in extraction.mentions:
        g_idx = matched.get((m.entity_type, m.entity_key))
        if g_idx is not None:
            found_docs.setdefault(g_idx, set()).add(docs.get(m.chunk_key, m.chunk_key))
    recalls = []
    per_entity = {}
    for i, g in enumerate(gold):
        if not g.documents:
            continue
        got = len(found_docs.get(i, set()) & g.documents) / len(g.documents)
        recalls.append(got)
        per_entity[g.name] = round(got, 4)
    n_matched = len(active) - len(false_pos)
    return {
        "active_entities": len(active),
        "matched_entities": n_matched,
        "entity_precision": round(n_matched / len(active), 4) if active else 1.0,
        "mention_recall": round(sum(recalls) / len(recalls), 4) if recalls else 1.0,
        "gold_entities": len(gold),
        "gold_found": sum(1 for i, g in enumerate(gold) if found_docs.get(i)),
        "typing_accuracy": round(typed_ok / n_matched, 4) if n_matched else 1.0,
        "false_positives": sorted(false_pos)[:sample],
        "per_entity_recall": per_entity,
    }
