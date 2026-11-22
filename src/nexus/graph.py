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

"""Knowledge graph: one import for extraction, resolution, deltas, communities and ranking.

Pure functions, standard library only, no I/O: the caller owns storage. The pieces:

  extraction   ``structured_graph`` (table rows), ``extract_mentions`` (text), ``Gazetteer``
  resolution   ``normalise_name``, ``resolve``, ``apply_resolution``, ``AliasIndex``
  deltas       ``mention_delta``, ``touched_entities``, ``aggregate_relations``,
               ``IncrementalGraph`` (add / remove chunks in memory)
  structure    ``CSRGraph``, ``leiden``, ``pagerank``, ``personalized_pagerank``,
               ``ego_subgraph``, ``community_summary_inputs``

``extract_graph(texts=, tables=)`` runs the whole extraction for a batch: structured
entities first, a gazetteer from them (names and ids), text mentions, then resolution.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from nexus.table_profile import profile_records

try:
    from nexus.processing.graph_delta import (
        ChangeSet,
        IncrementalGraph,
        MentionDelta,
        RelationAggregate,
        aggregate_relations,
        mention_delta,
        prune_relations,
        touched_entities,
    )
    from nexus.processing.graph_resolve import (
        AliasIndex,
        Resolution,
        acronym,
        apply_resolution,
        blocking_keys,
        normalise_name,
        resolve,
        similarity,
    )
    from nexus.processing.graph_structured import (
        EntityColumn,
        ForeignKey,
        RowEntitySpec,
        detect_foreign_keys,
        infer_entity_columns,
        infer_row_entity,
        is_masked,
        pk_index_for,
        structured_graph,
    )
    from nexus.processing.graph_text import TextGraphConfig, extract_mentions, type_of_span
    from nexus.processing.graph_tokens import Gazetteer, tokenise
    from nexus.processing.graph_types import (
        ENTITY_TYPES,
        EXTRACTOR_VERSION,
        Alias,
        EntityRef,
        GraphExtraction,
        Mention,
        RelationRef,
        entity_id,
        merge_extractions,
        relation_id,
    )
    from nexus.retrieval.graph_community import (
        COMMUNITY_SUMMARY_SYSTEM,
        CommunitySummaryInput,
        CSRGraph,
        community_label,
        community_summary_inputs,
        community_summary_prompt,
        leiden,
        members_hash,
        modularity,
    )
    from nexus.retrieval.graph_rank import (
        SubgraphSelection,
        degree_centrality,
        ego_subgraph,
        pagerank,
        personalized_pagerank,
        top_entities,
    )
except (ImportError, ModuleNotFoundError):  # layer packages installed on their own
    from nexus_processing.graph_delta import (  # type: ignore[no-redef]
        ChangeSet,
        IncrementalGraph,
        MentionDelta,
        RelationAggregate,
        aggregate_relations,
        mention_delta,
        prune_relations,
        touched_entities,
    )
    from nexus_processing.graph_resolve import (  # type: ignore[no-redef]
        AliasIndex,
        Resolution,
        acronym,
        apply_resolution,
        blocking_keys,
        normalise_name,
        resolve,
        similarity,
    )
    from nexus_processing.graph_structured import (  # type: ignore[no-redef]
        EntityColumn,
        ForeignKey,
        RowEntitySpec,
        detect_foreign_keys,
        infer_entity_columns,
        infer_row_entity,
        is_masked,
        pk_index_for,
        structured_graph,
    )
    from nexus_processing.graph_text import (  # type: ignore[no-redef]
        TextGraphConfig,
        extract_mentions,
        type_of_span,
    )
    from nexus_processing.graph_tokens import Gazetteer, tokenise  # type: ignore[no-redef]
    from nexus_processing.graph_types import (  # type: ignore[no-redef]
        ENTITY_TYPES,
        EXTRACTOR_VERSION,
        Alias,
        EntityRef,
        GraphExtraction,
        Mention,
        RelationRef,
        entity_id,
        merge_extractions,
        relation_id,
    )
    from nexus_retrieval.graph_community import (  # type: ignore[no-redef]
        COMMUNITY_SUMMARY_SYSTEM,
        CommunitySummaryInput,
        CSRGraph,
        community_label,
        community_summary_inputs,
        community_summary_prompt,
        leiden,
        members_hash,
        modularity,
    )
    from nexus_retrieval.graph_rank import (  # type: ignore[no-redef]
        SubgraphSelection,
        degree_centrality,
        ego_subgraph,
        pagerank,
        personalized_pagerank,
        top_entities,
    )

__all__ = [
    "COMMUNITY_SUMMARY_SYSTEM",
    "ENTITY_TYPES",
    "EXTRACTOR_VERSION",
    "Alias",
    "AliasIndex",
    "CSRGraph",
    "ChangeSet",
    "CommunitySummaryInput",
    "EntityColumn",
    "EntityRef",
    "ForeignKey",
    "Gazetteer",
    "GraphExtraction",
    "IncrementalGraph",
    "Mention",
    "MentionDelta",
    "RelationAggregate",
    "RelationRef",
    "Resolution",
    "RowEntitySpec",
    "SubgraphSelection",
    "TableInput",
    "TextGraphConfig",
    "acronym",
    "aggregate_relations",
    "apply_resolution",
    "blocking_keys",
    "community_label",
    "community_summary_inputs",
    "community_summary_prompt",
    "degree_centrality",
    "detect_foreign_keys",
    "ego_subgraph",
    "entity_id",
    "extract_graph",
    "extract_mentions",
    "gazetteer_from",
    "infer_entity_columns",
    "infer_row_entity",
    "is_masked",
    "leiden",
    "members_hash",
    "mention_delta",
    "merge_extractions",
    "modularity",
    "normalise_name",
    "pagerank",
    "personalized_pagerank",
    "pk_index_for",
    "prune_relations",
    "relation_id",
    "resolve",
    "similarity",
    "structured_graph",
    "tokenise",
    "top_entities",
    "touched_entities",
    "type_of_span",
]


@dataclass
class TableInput:
    """One table's rows for ``extract_graph``: ``records`` are ``(chunk_key, record)``."""

    name: str
    records: Sequence[tuple[str, Mapping[str, Any]]]
    primary_key: str | None = None
    profile: Mapping[str, Any] | None = None
    column_kinds: Mapping[str, str] | None = None
    hints: Mapping[str, str] | None = None
    foreign_keys: Sequence[ForeignKey] = field(default_factory=tuple)


def gazetteer_from(
    entities: Iterable[EntityRef],
    aliases: Iterable[Alias] = (),
    extra: Iterable[tuple[str, str, str]] = (),
) -> Gazetteer:
    """A gazetteer of active entity names, their aliases and ``extra`` triples."""
    names: list[tuple[str, str, str]] = [
        (e.name, e.key, e.type) for e in entities if e.status == "active"
    ]
    names += [(a.alias, a.entity_key, a.entity_type) for a in aliases]
    names += list(extra)
    return Gazetteer.build(names)


def extract_graph(
    *,
    texts: Iterable[Sequence[str]] = (),
    tables: Sequence[TableInput] = (),
    gazetteer_names: Iterable[tuple[str, str, str]] = (),
    known_aliases: AliasIndex | None = None,
    config: TextGraphConfig | None = None,
    extra_detector: Callable[[str], Iterable[tuple[int, int, str]]] | None = None,
    resolve_entities: bool = True,
    auto_merge: float = 0.92,
) -> GraphExtraction:
    """Structured entities from ``tables``, text mentions from ``texts`` (``(chunk_key, text)``
    or ``(chunk_key, text, document_key)``) using a gazetteer of those entities plus
    ``gazetteer_names``, then resolution against ``known_aliases``."""
    specs: dict[str, tuple[TableInput, Mapping[str, Any], RowEntitySpec | None]] = {}
    for table in tables:
        profile = table.profile or profile_records([r for _, r in table.records])
        row_spec = infer_row_entity(
            profile,
            primary_key=table.primary_key,
            table=table.name,
            column_kinds=table.column_kinds,
        )
        specs[table.name] = (table, profile, row_spec)
    pk_index: dict[str, dict[str, tuple[str, str, str]]] = {}
    for table, _, _ in specs.values():
        for fk in table.foreign_keys:
            target = specs.get(fk.ref_table)
            if target and target[2] is not None:
                index = pk_index_for((r for _, r in target[0].records), target[2], fk.ref_column)
                pk_index.setdefault(fk.ref_table, {}).update(index)
    parts: list[GraphExtraction] = []
    for table, profile, row_spec in specs.values():
        exclude = [table.primary_key] if table.primary_key else []
        exclude += [fk.column for fk in table.foreign_keys]
        if row_spec is not None:
            exclude.append(row_spec.name_column)
        columns = infer_entity_columns(
            profile, column_kinds=table.column_kinds, hints=table.hints, exclude=exclude
        )
        parts.append(
            structured_graph(
                table.records,
                columns,
                table=table.name,
                row_entity=row_spec,
                foreign_keys=table.foreign_keys,
                pk_index=pk_index,
            )
        )
    structured = merge_extractions(parts)
    gazetteer = gazetteer_from(structured.entities, structured.aliases, gazetteer_names)
    text = extract_mentions(
        texts, gazetteer=gazetteer, config=config, extra_detector=extra_detector
    )
    merged = merge_extractions([structured, text])
    if not resolve_entities:
        return merged
    weights: dict[tuple[str, str], float] = {}
    for m in merged.mentions:
        ref = (m.entity_type, m.entity_key)
        weights[ref] = weights.get(ref, 0.0) + 1.0
    candidates = [e for e in merged.entities if e.status == "active"]
    resolution = resolve(candidates, known_aliases, auto_merge=auto_merge, weights=weights)
    out = apply_resolution(merged, resolution)
    stats = dict(out.stats)
    stats["proposals"] = len(resolution.proposals)
    stats["auto_merges"] = len(resolution.merges)
    return GraphExtraction(out.entities, out.mentions, out.relations, out.aliases, stats)
