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

"""Knowledge-graph data shapes shared by the extractors, the resolver and the deltas.

Every shape is immutable. ``Mention`` and ``RelationRef`` are named tuples (made in the
millions: about 3x cheaper to create than frozen dataclasses); the others are frozen
dataclasses with ``__slots__``. Entities are identified by ``(type, key)``; ``key`` is the
normalised name (``graph_resolve.normalise_name``). Chunk keys are opaque (the caller's chunk id).

Ids are deterministic (``uuid5``), so a store can upsert idempotently and a job can be
retried: ``entity_id(workspace, type, key)`` and ``relation_id(workspace, src, dst, type)``.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import NamedTuple

__all__ = [
    "ENTITY_TYPES",
    "EXTRACTOR_VERSION",
    "METHODS",
    "NAMESPACE",
    "SYMMETRIC_RELATIONS",
    "Alias",
    "EntityRef",
    "GraphExtraction",
    "Mention",
    "RelationRef",
    "entity_id",
    "merge_extractions",
    "relation_id",
]

ENTITY_TYPES = ("person", "org", "place", "product", "project", "record", "concept", "entity")
# How a mention was found. "field"/"fk" come from table records, the rest from text.
METHODS = ("field", "fk", "gazetteer", "caps", "abbrev", "np", "id", "hook")
# Bump when extraction output changes for the same input: stores re-extract changed chunks only.
EXTRACTOR_VERSION = "kg1"
NAMESPACE = uuid.UUID("6f1c2b0e-9d43-5b7a-8e21-4c7f0a9d3e55")
SYMMETRIC_RELATIONS = frozenset({"co_mentioned"})
_SEP = "\x1f"


@dataclass(frozen=True, slots=True)
class EntityRef:
    """An entity as an extractor saw it, before it is stored."""

    key: str
    name: str
    type: str
    origin: str  # "structured" | "text"
    attributes: tuple[tuple[str, str], ...] = ()
    status: str = "active"  # "candidate" for noun-phrase concepts until seen in 2+ documents

    @property
    def ref(self) -> tuple[str, str]:
        return (self.type, self.key)


class Mention(NamedTuple):
    entity_key: str
    entity_type: str
    chunk_key: str
    start: int  # char offset in the chunk text; -1 for a field mention
    end: int
    surface: str
    method: str
    confidence: float
    field: str | None = None


class RelationRef(NamedTuple):
    """One relation seen in one chunk (the evidence unit)."""

    src_key: str
    src_type: str
    dst_key: str
    dst_type: str
    type: str
    chunk_key: str
    count: int = 1
    origin: str = "text"


@dataclass(frozen=True, slots=True)
class Alias:
    """A row for an alias table: ``alias`` (normalised to ``alias_key``) names the entity."""

    alias_key: str
    alias: str
    entity_key: str
    entity_type: str
    source: str  # name | structured_id | abbrev | fuzzy | manual
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class GraphExtraction:
    entities: tuple[EntityRef, ...] = ()
    mentions: tuple[Mention, ...] = ()
    relations: tuple[RelationRef, ...] = ()
    aliases: tuple[Alias, ...] = ()
    stats: dict[str, int] = field(default_factory=dict)


def entity_id(workspace_id: str, entity_type: str, key: str) -> str:
    """Deterministic entity id: the same workspace, type and key always give the same uuid."""
    return str(uuid.uuid5(NAMESPACE, _SEP.join(("e", workspace_id, entity_type, key))))


def relation_id(workspace_id: str, src_id: str, dst_id: str, relation_type: str) -> str:
    """Deterministic relation id; symmetric types (``co_mentioned``) ignore direction."""
    if relation_type in SYMMETRIC_RELATIONS and dst_id < src_id:
        src_id, dst_id = dst_id, src_id
    return str(uuid.uuid5(NAMESPACE, _SEP.join(("r", workspace_id, src_id, dst_id, relation_type))))


_ORIGIN_RANK = {"manual": 4, "structured": 3, "llm": 2, "text": 1}


def merge_extractions(parts: Iterable[GraphExtraction]) -> GraphExtraction:
    """One extraction from several: entities deduplicated by ``(type, key)`` (a structured
    entity wins over a text one, and keeps its name), mentions by ``(entity, chunk, start)``,
    relations by ``(src, dst, type, chunk)`` with counts summed, aliases by
    ``(alias_key, entity)``; stats are summed."""
    entities: dict[tuple[str, str], EntityRef] = {}
    mentions: dict[tuple[str, str, str, int], Mention] = {}
    relations: dict[tuple[str, str, str, str, str, str], RelationRef] = {}
    aliases: dict[tuple[str, str, str], Alias] = {}
    stats: dict[str, int] = {}
    for part in parts:
        for e in part.entities:
            old = entities.get(e.ref)
            if old is None or _better(e, old):
                entities[e.ref] = e
        for m in part.mentions:
            mentions.setdefault((m.entity_type, m.entity_key, m.chunk_key, m.start), m)
        for r in part.relations:
            k = (r.src_type, r.src_key, r.dst_type, r.dst_key, r.type, r.chunk_key)
            old_r = relations.get(k)
            if old_r is None:
                relations[k] = r
            else:
                origin = old_r.origin if old_r.origin == "structured" else r.origin
                relations[k] = RelationRef(
                    r.src_key,
                    r.src_type,
                    r.dst_key,
                    r.dst_type,
                    r.type,
                    r.chunk_key,
                    old_r.count + r.count,
                    origin,
                )
        for a in part.aliases:
            old_a = aliases.get((a.alias_key, a.entity_type, a.entity_key))
            if old_a is None or a.confidence > old_a.confidence:
                aliases[(a.alias_key, a.entity_type, a.entity_key)] = a
        for k2, v in part.stats.items():
            stats[k2] = stats.get(k2, 0) + v
    return GraphExtraction(
        tuple(entities.values()),
        tuple(mentions.values()),
        tuple(relations.values()),
        tuple(aliases.values()),
        stats,
    )


def _better(new: EntityRef, old: EntityRef) -> bool:
    rank_new, rank_old = _ORIGIN_RANK.get(new.origin, 0), _ORIGIN_RANK.get(old.origin, 0)
    if rank_new != rank_old:
        return rank_new > rank_old
    if new.status != old.status:
        return new.status == "active"
    return len(new.attributes) > len(old.attributes)
