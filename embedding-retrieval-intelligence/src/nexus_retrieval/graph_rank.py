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

"""Ranking and selection on an entity graph, standard library only.

- ``pagerank(g)``: weighted PageRank over a ``CSRGraph`` (dangling mass spread uniformly);
  the inner sum runs in C (``sum(map(mul, ...))``) over CSR slices.
- ``personalized_pagerank(g, seeds)``: the same with restarts to the seed nodes.
- ``top_entities(scores, k, ...)``: the ``k`` best nodes by a score (rank, degree, documents).
- ``ego_subgraph(focus, neighbours, hops=, limit=)``: the nodes around ``focus`` worth
  showing. The caller supplies neighbour lists (e.g. from SQL, capped per node); nodes are
  ranked by edge weight x node weight (halved per extra hop), and every kept node keeps the
  path to the focus, so the result is always connected.
"""

from __future__ import annotations

import heapq
from array import array
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from operator import mul

from .graph_community import CSRGraph

__all__ = [
    "SubgraphSelection",
    "degree_centrality",
    "ego_subgraph",
    "pagerank",
    "personalized_pagerank",
    "top_entities",
]


def _iterate(g: CSRGraph, restart: Sequence[float], alpha: float, iters: int, tol: float) -> array:
    n = g.n
    indptr, indices, weights, degree = g.indptr, g.indices, g.weights, g.degree
    out_w = [degree[v] - 2.0 * g.loops[v] for v in range(n)]  # loops do not spread rank
    rank = list(restart)
    for _ in range(iters):
        contrib = [rank[v] / out_w[v] if out_w[v] > 0 else 0.0 for v in range(n)]
        dangling = sum(rank[v] for v in range(n) if out_w[v] <= 0)
        new = [0.0] * n
        getc = contrib.__getitem__
        for v in range(n):
            a, b = indptr[v], indptr[v + 1]
            if a != b:
                new[v] = sum(map(mul, weights[a:b], map(getc, indices[a:b])))
        base = 1.0 - alpha
        spread = alpha * dangling
        new = [alpha * new[v] + (base + spread) * restart[v] for v in range(n)]
        delta = sum(abs(x - y) for x, y in zip(new, rank, strict=True))
        rank = new
        if delta < tol:
            break
    total = sum(rank) or 1.0
    return array("d", (r / total for r in rank))


def pagerank(g: CSRGraph, *, alpha: float = 0.85, iters: int = 30, tol: float = 1e-6) -> array:
    """PageRank score per node (sums to 1)."""
    if g.n == 0:
        return array("d")
    return _iterate(g, [1.0 / g.n] * g.n, alpha, iters, tol)


def personalized_pagerank(
    g: CSRGraph,
    seeds: Mapping[int, float],
    *,
    alpha: float = 0.85,
    iters: int = 20,
    tol: float = 1e-6,
    min_score: float = 1e-6,
) -> dict[int, float]:
    """Scores of the nodes reachable from ``seeds`` (restart distribution), above ``min_score``."""
    total = sum(w for w in seeds.values() if w > 0)
    if g.n == 0 or total <= 0:
        return {}
    restart = [0.0] * g.n
    for v, w in seeds.items():
        if w > 0:
            restart[v] = w / total
    scores = _iterate(g, restart, alpha, iters, tol)
    return {v: s for v, s in enumerate(scores) if s >= min_score}


def degree_centrality(g: CSRGraph) -> array:
    """Number of distinct neighbours per node."""
    return array("i", (g.indptr[v + 1] - g.indptr[v] for v in range(g.n)))


def top_entities(
    scores: Sequence[float] | Mapping[int, float],
    k: int = 50,
    *,
    types: Sequence[str] | None = None,
    allowed: Sequence[str] | None = None,
) -> list[tuple[int, float]]:
    """The ``k`` best ``(node, score)`` pairs; ``types[node]`` filtered by ``allowed``."""
    items = scores.items() if isinstance(scores, Mapping) else enumerate(scores)
    if types is not None and allowed:
        keep = set(allowed)
        items = ((v, s) for v, s in items if types[v] in keep)
    return heapq.nlargest(k, items, key=lambda vs: (vs[1], -vs[0]))


@dataclass(frozen=True, slots=True)
class SubgraphSelection:
    nodes: tuple[int, ...]  # focus first, then by score
    edges: tuple[tuple[int, int, float], ...]
    hops: dict[int, int]
    truncated: bool
    total: int  # nodes within ``hops`` before the limit


def ego_subgraph(
    focus: int,
    neighbours: Mapping[int, Sequence[tuple[int, float]]],
    *,
    hops: int = 1,
    limit: int = 300,
    node_weight: Mapping[int, float] | None = None,
) -> SubgraphSelection:
    """The best ``limit`` nodes within ``hops`` of ``focus`` (see the module docstring)."""
    hops = max(1, min(hops, 3))
    limit = max(1, limit)
    level = {focus: 0}
    parent: dict[int, int] = {}
    score: dict[int, float] = {}
    frontier = [focus]
    for depth in range(1, hops + 1):
        nxt = []
        for u in frontier:
            for v, w in neighbours.get(u, ()):
                if v == focus:
                    continue
                nw = node_weight.get(v, 1.0) if node_weight is not None else 1.0
                s = w * max(nw, 1e-9) * (0.5 ** (depth - 1))
                if depth > 1:
                    s = min(s, score.get(u, s))  # a path is as strong as its weakest link
                if v not in level:
                    level[v] = depth
                    parent[v] = u
                    score[v] = s
                    nxt.append(v)
                elif level[v] == depth and s > score[v]:
                    parent[v] = u
                    score[v] = s
        frontier = nxt
    total = len(level)
    kept: dict[int, None] = {focus: None}
    for v in sorted(score, key=lambda x: (-score[x], x)):
        if len(kept) >= limit:
            break
        if v in kept:
            continue
        path = []
        u = v
        while u not in kept:
            path.append(u)
            u = parent[u]
        if len(kept) + len(path) > limit:
            continue
        for u in reversed(path):
            kept[u] = None
    chosen = set(kept)
    edges: dict[tuple[int, int], float] = {}
    for u in kept:
        for v, w in neighbours.get(u, ()):
            if v in chosen and v != u:
                key = (u, v) if u < v else (v, u)
                if w > edges.get(key, 0.0):
                    edges[key] = w
    return SubgraphSelection(
        tuple(kept),
        tuple((a, b, w) for (a, b), w in edges.items()),
        {v: level[v] for v in kept},
        total > len(kept),
        total,
    )
