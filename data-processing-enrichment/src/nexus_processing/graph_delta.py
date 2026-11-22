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

"""Incremental graph maintenance: mention diffs, relation evidence and an in-memory graph.

A store keeps mentions and relation evidence keyed by chunk, so a changed chunk costs only
its own rows:

- ``mention_delta(old, new)``: per chunk, the mention rows to delete and to insert
  (``old`` rows are ``(chunk_key, entity_type, entity_key, start)``); ``touched_entities``
  lists the entities whose counts must be recomputed.
- ``aggregate_relations(relations)``: one ``RelationAggregate`` per ``(src, dst, type)`` with
  its weight and evidence ``(chunk_key, count)``; ``prune_relations`` keeps co-mentions seen
  at least twice or touching a structured entity.
- ``IncrementalGraph``: the same bookkeeping in memory (``add`` / ``remove_chunks`` return
  what changed), for callers without a database and for evaluation.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from .graph_types import EntityRef, GraphExtraction, Mention, RelationRef

__all__ = [
    "ChangeSet",
    "IncrementalGraph",
    "MentionDelta",
    "RelationAggregate",
    "aggregate_relations",
    "mention_delta",
    "prune_relations",
    "touched_entities",
]

Ref = tuple[str, str]


@dataclass(frozen=True, slots=True)
class MentionDelta:
    removed: tuple[tuple[str, str, str, int], ...]  # (chunk, type, key, start)
    added: tuple[Mention, ...]
    unchanged: int
    chunks: frozenset[str]


def mention_delta(old: Iterable[tuple[str, str, str, int]], new: Iterable[Mention]) -> MentionDelta:
    """Rows to delete and insert so the store holds exactly ``new`` for the chunks in ``new``
    (and nothing for chunks only in ``old``)."""
    old_set = {(c, t, k, int(s)) for c, t, k, s in old}
    added: list[Mention] = []
    new_keys: set[tuple[str, str, str, int]] = set()
    for m in new:
        k = (m.chunk_key, m.entity_type, m.entity_key, m.start)
        if k in new_keys:
            continue
        new_keys.add(k)
        if k not in old_set:
            added.append(m)
    removed = tuple(sorted(old_set - new_keys))
    chunks = frozenset({k[0] for k in old_set} | {k[0] for k in new_keys})
    return MentionDelta(removed, tuple(added), len(old_set & new_keys), chunks)


def touched_entities(delta: MentionDelta) -> frozenset[Ref]:
    """Entities whose mention or document counts may have changed."""
    out = {(t, k) for _, t, k, _ in delta.removed}
    out.update((m.entity_type, m.entity_key) for m in delta.added)
    return frozenset(out)


@dataclass(frozen=True, slots=True)
class RelationAggregate:
    src: Ref
    dst: Ref
    type: str
    origin: str
    weight: float
    evidence: tuple[tuple[str, int], ...]  # (chunk_key, count)

    @property
    def evidence_count(self) -> int:
        return len(self.evidence)


def aggregate_relations(relations: Iterable[RelationRef]) -> list[RelationAggregate]:
    """Relations grouped by ``(src, dst, type)``: weight = total count, evidence per chunk."""
    groups: dict[tuple[Ref, Ref, str], dict[str, int]] = defaultdict(dict)
    origins: dict[tuple[Ref, Ref, str], str] = {}
    for r in relations:
        k = ((r.src_type, r.src_key), (r.dst_type, r.dst_key), r.type)
        ev = groups[k]
        ev[r.chunk_key] = ev.get(r.chunk_key, 0) + r.count
        if origins.get(k) != "structured":
            origins[k] = r.origin
    return [
        RelationAggregate(
            s, d, t, origins[(s, d, t)], float(sum(ev.values())), tuple(sorted(ev.items()))
        )
        for (s, d, t), ev in groups.items()
    ]


def prune_relations(
    aggregates: Iterable[RelationAggregate],
    *,
    structured: Iterable[Ref] = (),
    min_evidence: int = 2,
) -> list[RelationAggregate]:
    """Structured relations, plus text relations with ``min_evidence`` total count or one end
    in ``structured`` (the entities that came from records)."""
    known = set(structured)
    return [
        a
        for a in aggregates
        if a.origin == "structured" or a.weight >= min_evidence or a.src in known or a.dst in known
    ]


@dataclass(frozen=True, slots=True)
class ChangeSet:
    entities: frozenset[Ref] = frozenset()
    relations: frozenset[tuple[Ref, Ref, str]] = frozenset()
    edges_changed: int = 0
    chunks: frozenset[str] = frozenset()


@dataclass(slots=True)
class _EntityState:
    entity: EntityRef
    chunks: dict[str, int] = field(default_factory=dict)  # chunk -> mentions


class IncrementalGraph:
    """An entity-mention graph kept up to date chunk by chunk.

    ``add(extraction, documents=)`` replaces everything known about the extraction's chunks
    (re-indexing a chunk is ``add`` again); ``remove_chunks(keys)`` deletes them. Both return
    a ``ChangeSet`` with the entities and relations whose counts changed. Entities with no
    mention left are dropped. ``documents`` maps chunk keys to document keys for document
    counts (a chunk is its own document otherwise)."""

    def __init__(self) -> None:
        self._entities: dict[Ref, _EntityState] = {}
        self._chunk_mentions: dict[str, list[Mention]] = {}
        self._chunk_relations: dict[str, list[RelationRef]] = {}
        self._relations: dict[tuple[Ref, Ref, str], dict[str, int]] = {}
        self._origins: dict[tuple[Ref, Ref, str], str] = {}
        self._doc_of: dict[str, str] = {}
        self._known: dict[Ref, EntityRef] = {}

    def add(
        self, extraction: GraphExtraction, documents: Mapping[str, str] | None = None
    ) -> ChangeSet:
        chunks = {m.chunk_key for m in extraction.mentions} | {
            r.chunk_key for r in extraction.relations
        }
        candidates = {
            ((r.src_type, r.src_key), (r.dst_type, r.dst_key), r.type) for r in extraction.relations
        }
        for chunk in chunks:
            candidates.update(
                ((r.src_type, r.src_key), (r.dst_type, r.dst_key), r.type)
                for r in self._chunk_relations.get(chunk, ())
            )
        before = {k for k in candidates if self._relations.get(k)}
        removed = self.remove_chunks(chunks, _drop_empty=False)
        for e in extraction.entities:
            old = self._known.get(e.ref)
            if old is None or old.origin != "structured" or e.origin == "structured":
                self._known[e.ref] = e
        touched_e = set(removed.entities)
        touched_r = set(removed.relations)
        for chunk in chunks:
            if documents and chunk in documents:
                self._doc_of[chunk] = documents[chunk]
        for m in extraction.mentions:
            ref = (m.entity_type, m.entity_key)
            state = self._entities.get(ref)
            if state is None:
                entity = self._known.get(ref) or EntityRef(
                    m.entity_key, m.surface, m.entity_type, "text"
                )
                state = self._entities[ref] = _EntityState(entity)
            state.chunks[m.chunk_key] = state.chunks.get(m.chunk_key, 0) + 1
            self._chunk_mentions.setdefault(m.chunk_key, []).append(m)
            touched_e.add(ref)
        for r in extraction.relations:
            k = ((r.src_type, r.src_key), (r.dst_type, r.dst_key), r.type)
            ev = self._relations.setdefault(k, {})
            ev[r.chunk_key] = ev.get(r.chunk_key, 0) + r.count
            if self._origins.get(k) != "structured":
                self._origins[k] = r.origin
            self._chunk_relations.setdefault(r.chunk_key, []).append(r)
            touched_r.add(k)
        self._drop_empty(touched_e, touched_r)
        edges = len(before ^ {k for k in candidates if self._relations.get(k)})
        return ChangeSet(frozenset(touched_e), frozenset(touched_r), edges, frozenset(chunks))

    def remove_chunks(self, chunk_keys: Iterable[str], *, _drop_empty: bool = True) -> ChangeSet:
        touched_e: set[Ref] = set()
        touched_r: set[tuple[Ref, Ref, str]] = set()
        edges = 0
        keys = set(chunk_keys)
        for chunk in keys:
            for m in self._chunk_mentions.pop(chunk, ()):
                ref = (m.entity_type, m.entity_key)
                state = self._entities.get(ref)
                if state is not None:
                    state.chunks.pop(chunk, None)
                    touched_e.add(ref)
            for r in self._chunk_relations.pop(chunk, ()):
                k = ((r.src_type, r.src_key), (r.dst_type, r.dst_key), r.type)
                ev = self._relations.get(k)
                if ev is not None and ev.pop(chunk, None) is not None:
                    touched_r.add(k)
                    if not ev:
                        edges += 1
            if _drop_empty:
                self._doc_of.pop(chunk, None)
        if _drop_empty:
            self._drop_empty(touched_e, touched_r)
        return ChangeSet(frozenset(touched_e), frozenset(touched_r), edges, frozenset(keys))

    def _drop_empty(self, entities: set[Ref], relations: set[tuple[Ref, Ref, str]]) -> None:
        for ref in entities:
            state = self._entities.get(ref)
            if state is not None and not state.chunks:
                del self._entities[ref]
        for k in relations:
            if not self._relations.get(k, True):
                del self._relations[k]
                self._origins.pop(k, None)

    # -- reads ---------------------------------------------------------------------------
    def entity(self, ref: Ref) -> EntityRef | None:
        state = self._entities.get(ref)
        return state.entity if state else None

    def entities(self) -> list[EntityRef]:
        return [s.entity for s in self._entities.values()]

    def mention_count(self, ref: Ref) -> int:
        state = self._entities.get(ref)
        return sum(state.chunks.values()) if state else 0

    def document_count(self, ref: Ref) -> int:
        state = self._entities.get(ref)
        if not state:
            return 0
        return len({self._doc_of.get(c, c) for c in state.chunks})

    def chunks_of(self, ref: Ref) -> list[str]:
        state = self._entities.get(ref)
        return sorted(state.chunks) if state else []

    def relations(self, *, min_evidence: int = 1) -> list[RelationAggregate]:
        structured = {r for r, s in self._entities.items() if s.entity.origin == "structured"}
        aggs = [
            RelationAggregate(
                s,
                d,
                t,
                self._origins.get((s, d, t), "text"),
                float(sum(ev.values())),
                tuple(sorted(ev.items())),
            )
            for (s, d, t), ev in self._relations.items()
            if ev
        ]
        return prune_relations(aggs, structured=structured, min_evidence=min_evidence)

    def edges(self, *, min_evidence: int = 2) -> tuple[list[Ref], list[tuple[int, int, float]]]:
        """Nodes and ``(i, j, weight)`` edges, ready for ``CSRGraph.from_edges``."""
        index: dict[Ref, int] = {}
        nodes: list[Ref] = []
        out: list[tuple[int, int, float]] = []
        for agg in self.relations(min_evidence=min_evidence):
            ids = []
            for ref in (agg.src, agg.dst):
                if ref not in index:
                    index[ref] = len(nodes)
                    nodes.append(ref)
                ids.append(index[ref])
            out.append((ids[0], ids[1], agg.weight))
        return nodes, out

    def __len__(self) -> int:
        return len(self._entities)
