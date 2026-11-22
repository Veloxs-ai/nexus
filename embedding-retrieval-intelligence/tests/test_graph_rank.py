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

from nexus_retrieval.graph_community import CSRGraph
from nexus_retrieval.graph_rank import (
    degree_centrality,
    ego_subgraph,
    pagerank,
    personalized_pagerank,
    top_entities,
)


def star(n: int = 6) -> CSRGraph:
    return CSRGraph.from_edges(n, [(0, v, 1.0) for v in range(1, n)])


def test_pagerank_sums_to_one_and_ranks_hubs_first():
    pr = pagerank(star())
    assert abs(sum(pr) - 1.0) < 1e-9
    assert max(range(6), key=pr.__getitem__) == 0
    assert len(pagerank(CSRGraph.from_edges(0, []))) == 0
    isolated = pagerank(CSRGraph.from_edges(3, [(0, 1, 1.0)]))  # node 2 dangles
    assert abs(sum(isolated) - 1.0) < 1e-9 and isolated[2] > 0


def test_personalized_pagerank_stays_near_seeds():
    g = CSRGraph.from_edges(6, [(0, 1, 1.0), (1, 2, 1.0), (3, 4, 1.0), (4, 5, 1.0), (2, 3, 0.01)])
    scores = personalized_pagerank(g, {0: 1.0})
    assert scores[0] > scores.get(5, 0.0) and scores[1] > scores.get(4, 0.0)
    assert personalized_pagerank(g, {}) == {}
    assert personalized_pagerank(g, {0: -1.0}) == {}


def test_degree_and_top_entities():
    g = star()
    deg = degree_centrality(g)
    assert list(deg) == [5, 1, 1, 1, 1, 1]
    assert top_entities(deg, 2)[0] == (0, 5)
    types = ["org", "person", "org", "org", "place", "org"]
    best = top_entities({1: 0.5, 2: 0.9, 4: 0.7}, 5, types=types, allowed=["org"])
    assert [v for v, _ in best] == [2]


def _neigh(edges):
    out: dict[int, list[tuple[int, float]]] = {}
    for u, v, w in edges:
        out.setdefault(u, []).append((v, w))
        out.setdefault(v, []).append((u, w))
    return out


def test_ego_subgraph_limits_hops_and_keeps_paths():
    edges = [(0, 1, 5.0), (0, 2, 1.0), (1, 3, 4.0), (3, 4, 9.0), (2, 5, 0.1)]
    nb = _neigh(edges)
    one = ego_subgraph(0, nb, hops=1)
    assert one.nodes[0] == 0 and set(one.nodes) == {0, 1, 2}
    assert one.hops == {0: 0, 1: 1, 2: 1} and not one.truncated and one.total == 3
    two = ego_subgraph(0, nb, hops=2, limit=3)
    assert two.nodes[0] == 0 and len(two.nodes) == 3 and two.truncated
    assert set(two.nodes) == {0, 1, 3}  # node 3 is kept with its path through node 1
    assert {(a, b) for a, b, _ in two.edges} == {(0, 1), (1, 3)}
    assert ego_subgraph(9, nb).nodes == (9,)


def test_ego_subgraph_uses_node_weight():
    nb = _neigh([(0, 1, 1.0), (0, 2, 1.0), (0, 3, 1.0)])
    sel = ego_subgraph(0, nb, limit=2, node_weight={3: 10.0, 1: 0.1, 2: 0.2})
    assert sel.nodes == (0, 3)
