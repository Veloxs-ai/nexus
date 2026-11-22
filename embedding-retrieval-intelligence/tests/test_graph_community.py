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

import random

from nexus_retrieval.graph_community import (
    COMMUNITY_SUMMARY_SYSTEM,
    CSRGraph,
    community_label,
    community_summary_inputs,
    community_summary_prompt,
    leiden,
    members_hash,
    modularity,
)

# Zachary's karate club (78 edges).
_KARATE_TEXT = """
0-1 0-2 0-3 0-4 0-5 0-6 0-7 0-8 0-10 0-11 0-12 0-13 0-17 0-19 0-21 0-31 1-2 1-3 1-7 1-13
1-17 1-19 1-21 1-30 2-3 2-7 2-8 2-9 2-13 2-27 2-28 2-32 3-7 3-12 3-13 4-6 4-10 5-6 5-10
5-16 6-16 8-30 8-32 8-33 9-33 13-33 14-32 14-33 15-32 15-33 18-32 18-33 19-33 20-32
20-33 22-32 22-33 23-25 23-27 23-29 23-32 23-33 24-25 24-27 24-31 25-31 26-29 26-33
27-33 28-31 28-33 29-32 29-33 30-32 30-33 31-32 31-33 32-33
"""
KARATE = [tuple(map(int, e.split("-"))) for e in _KARATE_TEXT.split()]


def karate() -> CSRGraph:
    return CSRGraph.from_edges(34, [(a, b, 1.0) for a, b in KARATE])


def planted(n_comm: int, size: int, p_in: float, p_out: float, seed: int = 1):
    rng = random.Random(seed)
    n = n_comm * size
    edges = [
        (u, v, 1.0)
        for u in range(n)
        for v in range(u + 1, n)
        if rng.random() < (p_in if u // size == v // size else p_out)
    ]
    return CSRGraph.from_edges(n, edges), [v // size for v in range(n)]


def test_csr_sums_duplicates_and_keeps_loops_apart():
    g = CSRGraph.from_edges(4, [(0, 1, 1.0), (1, 0, 2.0), (2, 2, 5.0), (1, 3, 0.0), (2, 3, 1.0)])
    idx, ws = g.neighbours(0)
    assert list(idx) == [1] and list(ws) == [3.0]
    assert g.loops[2] == 5.0 and g.edge_count == 2
    assert g.degree[2] == 11.0  # 1 neighbour weight + 2 x loop
    assert g.total_weight == (3 + 3 + 11 + 1) / 2
    assert g.nbytes() > 0


def test_leiden_karate_reaches_known_optimum():
    g = karate()
    levels = leiden(g)
    best = levels[-1]
    assert len(best) == 34
    assert modularity(g, best) > 0.41  # the optimum is 0.4198
    assert 3 <= len(set(best)) <= 5
    assert all(len(set(levels[i])) >= len(set(levels[i + 1])) for i in range(len(levels) - 1))


def test_leiden_recovers_planted_partition():
    g, truth = planted(8, 30, 0.35, 0.01)
    found = leiden(g)[-1]
    assert len(set(found)) == 8
    groups = {}
    for v, c in enumerate(found):
        groups.setdefault(c, set()).add(truth[v])
    assert all(len(t) == 1 for t in groups.values())  # every community is one planted block


def test_leiden_is_deterministic_and_warm_starts():
    g, _ = planted(5, 20, 0.4, 0.02, seed=3)
    a, b = leiden(g, seed=11), leiden(g, seed=11)
    assert a == b
    warm = leiden(g, initial=a[-1])
    assert modularity(g, warm[-1]) >= modularity(g, a[-1]) - 1e-9
    assert leiden(g, initial=[0, 1])[-1]  # a wrong-length warm start is ignored


def test_leiden_edge_cases_and_resolution():
    assert leiden(CSRGraph.from_edges(0, [])) == [[]]
    lonely = leiden(CSRGraph.from_edges(3, []))
    assert len(set(lonely[-1])) == 3
    g, _ = planted(4, 20, 0.4, 0.05, seed=5)
    coarse = leiden(g, resolution=0.2)[-1]
    fine = leiden(g, resolution=3.0)[-1]
    assert len(set(coarse)) <= len(set(fine))
    assert len(leiden(g, max_levels=1)) == 1
    assert leiden(g, max_seconds=0.000001)  # the time guard still returns a partition


def test_modularity_of_trivial_partitions():
    g = karate()
    assert abs(modularity(g, [0] * 34)) < 1e-9
    assert modularity(g, list(range(34))) < 0
    assert modularity(CSRGraph.from_edges(2, []), [0, 1]) == 0.0


def test_labels_hashes_and_summary_inputs():
    assert (
        community_label([("Acme", 5.0), ("Globex", 9.0), ("Initech", 1.0), ("Hooli", 3.0)])
        == "Globex · Acme · Hooli +1"
    )
    assert community_label([("Acme", 1.0)]) == "Acme"
    assert members_hash(["b", "a"]) == members_hash(["a", "b"]) != members_hash(["a"])
    g = karate()
    membership = leiden(g)[-1]
    nodes = [(f"id{v}", f"N{v}", "org") for v in range(34)]
    inputs = community_summary_inputs(membership, nodes, g, top_members=5, top_edges=3)
    assert sum(s.size for s in inputs) == 34
    first = inputs[0]
    assert len(first.top_members) <= 5 and len(first.top_edges) <= 3
    assert first.top_members[0][3] >= first.top_members[-1][3]
    assert all(membership[u] == membership[v] == first.community for u, v, _ in first.top_edges)
    weights = [1.0] * 34
    assert community_summary_inputs(membership, nodes, g, node_weight=weights, min_size=40) == []


def test_community_summary_prompt():
    g = karate()
    membership = leiden(g)[-1]
    nodes = [(f"id{v}", f"N{v}", "org") for v in range(34)]
    first = community_summary_inputs(membership, nodes, g)[0]
    prompt = community_summary_prompt(
        first, ["Passage one.", "x" * 50, "never shown"], max_chars=30
    )
    assert prompt.startswith(f"Community: {first.label}")
    assert "[1] Passage one." in prompt and "<->" in prompt
    assert "[3]" not in prompt  # the character budget is spent
    assert "Do not invent" in COMMUNITY_SUMMARY_SYSTEM
