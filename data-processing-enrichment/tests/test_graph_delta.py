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

from nexus_processing.graph_delta import (
    IncrementalGraph,
    aggregate_relations,
    mention_delta,
    prune_relations,
    touched_entities,
)
from nexus_processing.graph_text import extract_mentions
from nexus_processing.graph_types import EntityRef, GraphExtraction, Mention, RelationRef


def _m(key, chunk, start=0, etype="org"):
    return Mention(key, etype, chunk, start, start + 4, key, "caps", 0.8)


def test_mention_delta_and_touched_entities():
    old = [("c1", "org", "acme", 0), ("c1", "org", "globex", 10), ("c2", "org", "acme", 0)]
    new = [_m("acme", "c1"), _m("initech", "c1", 20), _m("acme", "c1")]
    d = mention_delta(old, new)
    assert d.unchanged == 1
    assert [m.entity_key for m in d.added] == ["initech"]
    assert d.removed == (("c1", "org", "globex", 10), ("c2", "org", "acme", 0))
    assert d.chunks == {"c1", "c2"}
    assert touched_entities(d) == {("org", "globex"), ("org", "acme"), ("org", "initech")}


def test_aggregate_and_prune_relations():
    rels = [
        RelationRef("a", "org", "b", "org", "co_mentioned", "c1"),
        RelationRef("a", "org", "b", "org", "co_mentioned", "c2", 2),
        RelationRef("a", "org", "c", "org", "co_mentioned", "c1"),
        RelationRef("x", "org", "y", "person", "owner", "c3", 1, "structured"),
    ]
    aggs = {(a.src[1], a.dst[1]): a for a in aggregate_relations(rels)}
    assert aggs[("a", "b")].weight == 3 and aggs[("a", "b")].evidence == (("c1", 1), ("c2", 2))
    assert aggs[("a", "b")].evidence_count == 2
    kept = {(a.src[1], a.dst[1]) for a in prune_relations(aggs.values())}
    assert kept == {("a", "b"), ("x", "y")}
    kept = {(a.src[1], a.dst[1]) for a in prune_relations(aggs.values(), structured=[("org", "c")])}
    assert ("a", "c") in kept


def test_incremental_graph_add_replace_remove():
    g = IncrementalGraph()
    x1 = extract_mentions(
        [
            ("c1", "Acme Corp met Globex Inc in Pune.", "d1"),
            ("c2", "Acme Corp met Globex Inc again.", "d1"),
        ]
    )
    ch = g.add(x1, documents={"c1": "d1", "c2": "d1"})
    assert ("org", "acme corp") in ch.entities and ch.edges_changed >= 1
    assert (
        g.mention_count(("org", "acme corp")) == 2 and g.document_count(("org", "acme corp")) == 1
    )
    assert g.chunks_of(("org", "acme corp")) == ["c1", "c2"]
    rel = {(a.src[1], a.dst[1]): a for a in g.relations(min_evidence=1)}
    assert rel[("acme corp", "globex inc")].weight == 2
    # re-indexing c2 with new text replaces its rows only
    ch = g.add(extract_mentions([("c2", "Initech Ltd called.", "d1")]), documents={"c2": "d1"})
    assert g.mention_count(("org", "acme corp")) == 1
    assert g.entity(("org", "initech ltd")) is not None
    assert ("org", "acme corp") in ch.entities
    # re-adding identical content changes no edge
    again = g.add(extract_mentions([("c2", "Initech Ltd called.", "d1")]), documents={"c2": "d1"})
    assert again.edges_changed == 0
    ch = g.remove_chunks(["c1"])
    assert g.entity(("org", "acme corp")) is None and g.entity(("place", "pune")) is None
    assert ch.edges_changed >= 1 and len(g) == 1


def test_incremental_graph_edges_prune_and_keep_structured_names():
    structured = EntityRef("acme corp", "Acme Corp", "org", "structured")
    x = GraphExtraction(
        (structured,),
        (_m("acme corp", "r1"), _m("pune", "r1", 5, "place")),
        (
            RelationRef("acme corp", "org", "pune", "place", "city", "r1", 1, "structured"),
            RelationRef("acme corp", "org", "zed", "org", "co_mentioned", "r1"),
        ),
    )
    g = IncrementalGraph()
    g.add(x)
    assert g.entity(("org", "acme corp")).name == "Acme Corp"
    nodes, edges = g.edges(min_evidence=2)
    assert len(edges) == 2  # structured edge, and a co-mention touching a structured entity
    assert set(nodes) == {("org", "acme corp"), ("place", "pune"), ("org", "zed")}
    assert g.document_count(("missing", "x")) == 0 and g.chunks_of(("missing", "x")) == []
