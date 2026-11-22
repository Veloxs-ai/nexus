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

"""Communities of an entity graph: CSR storage and the Leiden algorithm, standard library only.

``CSRGraph.from_edges(n, edges)`` stores an undirected weighted graph in compressed sparse
row form (``array('i')`` offsets and neighbours, ``array('d')`` weights; about 12 bytes per
directed entry, no per-edge Python objects). Duplicate edges are summed; self-loops are kept
apart (``loops``).

``leiden(g, resolution=, seed=, ...)`` (Traag, Waltman & van Eck 2019) optimises modularity
with a resolution parameter in three steps per iteration: queue-driven local moving,
refinement (a node joins a well-connected sub-community picked at random with probability
proportional to ``exp(dQ / theta)``, seeded so results are reproducible) and aggregation of
the refined partition. It returns one membership list per level, finest first; the last
level is the converged partition. ``initial=`` warm-starts from a previous membership.
"""

from __future__ import annotations

import hashlib
import math
import random
import time
from array import array
from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

__all__ = [
    "COMMUNITY_SUMMARY_SYSTEM",
    "CSRGraph",
    "CommunitySummaryInput",
    "community_label",
    "community_summary_inputs",
    "community_summary_prompt",
    "leiden",
    "members_hash",
    "modularity",
]


class CSRGraph:
    """Undirected weighted graph in CSR form (both directions stored)."""

    __slots__ = ("degree", "indices", "indptr", "loops", "n", "total_weight", "weights")

    def __init__(self, n: int, indptr: array, indices: array, weights: array, loops: array) -> None:
        self.n = n
        self.indptr, self.indices, self.weights, self.loops = indptr, indices, weights, loops
        # weighted degree: neighbour weights + twice the self-loop weight
        self.degree = array(
            "d", (sum(weights[indptr[v] : indptr[v + 1]]) + 2.0 * loops[v] for v in range(n))
        )
        self.total_weight = sum(self.degree) / 2.0  # m

    @classmethod
    def from_edges(cls, n: int, edges: Iterable[tuple[int, int, float]]) -> CSRGraph:
        rows: list[dict[int, float] | None] = [None] * n
        loops = array("d", bytes(8 * n))
        for u, v, w in edges:
            if w <= 0:
                continue
            if u == v:
                loops[u] += w
                continue
            for a, b in ((u, v), (v, u)):
                row = rows[a]
                if row is None:
                    row = rows[a] = {}
                row[b] = row.get(b, 0.0) + w
        indptr = array("i", [0])
        indices = array("i")
        weights = array("d")
        for row in rows:
            if row:
                indices.extend(row.keys())
                weights.extend(row.values())
            indptr.append(len(indices))
        return cls(n, indptr, indices, weights, loops)

    def neighbours(self, v: int) -> tuple[array, array]:
        a, b = self.indptr[v], self.indptr[v + 1]
        return self.indices[a:b], self.weights[a:b]

    @property
    def edge_count(self) -> int:
        return len(self.indices) // 2

    def nbytes(self) -> int:
        return sum(
            x.itemsize * len(x)
            for x in (self.indptr, self.indices, self.weights, self.loops, self.degree)
        )


def modularity(g: CSRGraph, membership: Sequence[int], resolution: float = 1.0) -> float:
    """Newman modularity of ``membership`` (with resolution ``gamma``)."""
    m = g.total_weight
    if m <= 0:
        return 0.0
    internal: dict[int, float] = {}
    tot: dict[int, float] = {}
    indptr, indices, weights = g.indptr, g.indices, g.weights
    for v in range(g.n):
        c = membership[v]
        tot[c] = tot.get(c, 0.0) + g.degree[v]
        w_in = 2.0 * g.loops[v]
        for k in range(indptr[v], indptr[v + 1]):
            if membership[indices[k]] == c:
                w_in += weights[k]
        internal[c] = internal.get(c, 0.0) + w_in
    return sum(internal[c] / (2 * m) - resolution * (tot[c] / (2 * m)) ** 2 for c in tot)


def _move_nodes(
    g: CSRGraph, comm: list[int], gamma: float, rng: random.Random, deadline: float | None
) -> bool:
    """Queue-based fast local moving; returns True when any node moved."""
    n, m2 = g.n, 2.0 * g.total_weight
    indptr, indices, weights, degree = g.indptr, g.indices, g.weights, g.degree
    tot = [0.0] * n
    size = [0] * n
    for v in range(n):
        tot[comm[v]] += degree[v]
        size[comm[v]] += 1
    empty = [c for c in range(n) if size[c] == 0]
    order = list(range(n))
    rng.shuffle(order)
    queue = deque(order)
    queued = bytearray(b"\x01" * n)
    moved = False
    steps = 0
    while queue:
        v = queue.popleft()
        queued[v] = 0
        steps += 1
        if deadline is not None and steps % 2048 == 0 and time.monotonic() > deadline:
            break
        cv = comm[v]
        kv = degree[v]
        links: dict[int, float] = {}
        a, b = indptr[v], indptr[v + 1]
        for k in range(a, b):
            c = comm[indices[k]]
            links[c] = links.get(c, 0.0) + weights[k]
        tot[cv] -= kv
        size[cv] -= 1
        scale = gamma * kv / m2
        best, best_gain = cv, links.get(cv, 0.0) - scale * tot[cv]
        for c, w in links.items():
            gain = w - scale * tot[c]
            if gain > best_gain:
                best, best_gain = c, gain
        if best_gain < 0.0:
            if size[cv] == 0:
                best = cv
            elif empty:
                best = empty.pop()
        tot[best] += kv
        size[best] += 1
        if best != cv:
            if size[cv] == 0:
                empty.append(cv)
            comm[v] = best
            moved = True
            for k in range(a, b):
                u = indices[k]
                if not queued[u] and comm[u] != best:
                    queued[u] = 1
                    queue.append(u)
    return moved


def _refine(
    g: CSRGraph, comm: list[int], gamma: float, theta: float, rng: random.Random
) -> list[int]:
    """Refined partition: well-connected sub-communities of each community of ``comm``."""
    n, m = g.n, g.total_weight
    m2 = 2.0 * m
    indptr, indices, weights, degree = g.indptr, g.indices, g.weights, g.degree
    refined = list(range(n))
    tot_c: dict[int, float] = {}
    for v in range(n):
        tot_c[comm[v]] = tot_c.get(comm[v], 0.0) + degree[v]
    # weight from each node to the rest of its community
    ext_v = [0.0] * n
    for v in range(n):
        cv = comm[v]
        s = 0.0
        for k in range(indptr[v], indptr[v + 1]):
            if comm[indices[k]] == cv:
                s += weights[k]
        ext_v[v] = s
    tot_r = list(degree)  # total degree of each refined sub-community
    ext_r = list(ext_v)  # weight from each sub-community to the rest of its community
    size_r = [1] * n
    order = list(range(n))
    rng.shuffle(order)
    for v in order:
        cv = comm[v]
        kv = degree[v]
        if size_r[refined[v]] != 1 or ext_v[v] < gamma * kv * (tot_c[cv] - kv) / m2:
            continue
        links: dict[int, float] = {}
        for k in range(indptr[v], indptr[v + 1]):
            u = indices[k]
            if comm[u] == cv:
                r = refined[u]
                links[r] = links.get(r, 0.0) + weights[k]
        rv = refined[v]
        choices: list[tuple[int, float]] = []
        for r, w in links.items():
            if r == rv or ext_r[r] < gamma * tot_r[r] * (tot_c[cv] - tot_r[r]) / m2:
                continue
            gain = (w - gamma * kv * tot_r[r] / m2) / m
            if gain >= 0.0:
                choices.append((r, gain))
        if not choices:
            continue
        top = max(gain for _, gain in choices)
        probs = [math.exp((gain - top) / theta) for _, gain in choices]
        pick = rng.random() * sum(probs)
        target = choices[-1][0]
        for (r, _), p in zip(choices, probs, strict=True):
            pick -= p
            if pick <= 0:
                target = r
                break
        w_to = links[target]
        refined[v] = target
        size_r[rv] -= 1
        tot_r[rv] = 0.0
        ext_r[rv] = 0.0
        size_r[target] += 1
        tot_r[target] += kv
        ext_r[target] = ext_r[target] + ext_v[v] - 2.0 * w_to
    return refined


def _aggregate(g: CSRGraph, refined: list[int]) -> tuple[CSRGraph, list[int]]:
    ids: dict[int, int] = {}
    node_of = [0] * g.n
    for v in range(g.n):
        node_of[v] = ids.setdefault(refined[v], len(ids))
    edges: dict[tuple[int, int], float] = {}
    indptr, indices, weights = g.indptr, g.indices, g.weights
    loops: dict[int, float] = {}
    for v in range(g.n):
        a = node_of[v]
        if g.loops[v]:
            loops[a] = loops.get(a, 0.0) + g.loops[v]
        for k in range(indptr[v], indptr[v + 1]):
            u = indices[k]
            if u < v:
                continue
            b = node_of[u]
            if a == b:
                loops[a] = loops.get(a, 0.0) + weights[k]
            else:
                key = (a, b) if a < b else (b, a)
                edges[key] = edges.get(key, 0.0) + weights[k]
    triples = [(a, b, w) for (a, b), w in edges.items()] + [(a, a, w) for a, w in loops.items()]
    return CSRGraph.from_edges(len(ids), triples), node_of


def _renumber(membership: Sequence[int]) -> list[int]:
    ids: dict[int, int] = {}
    return [ids.setdefault(c, len(ids)) for c in membership]


def leiden(
    g: CSRGraph,
    *,
    resolution: float = 1.0,
    seed: int = 7,
    max_levels: int = 3,
    theta: float = 0.01,
    initial: Sequence[int] | None = None,
    max_seconds: float | None = None,
    max_iterations: int = 10,
) -> list[list[int]]:
    """Membership per level for the nodes of ``g`` (finest first, last = converged)."""
    if g.n == 0:
        return [[]]
    if g.total_weight <= 0:
        return [list(range(g.n))]  # no edges: every node is its own community
    rng = random.Random(seed)
    deadline = time.monotonic() + max_seconds if max_seconds else None
    graph = g
    comm = _renumber(initial) if initial is not None and len(initial) == g.n else list(range(g.n))
    original_to_node = list(range(g.n))
    levels: list[list[int]] = []
    for _ in range(max_iterations):
        _move_nodes(graph, comm, resolution, rng, deadline)
        levels.append(_renumber([comm[original_to_node[v]] for v in range(g.n)]))
        if len(set(comm)) == graph.n or (deadline is not None and time.monotonic() > deadline):
            break
        refined = _refine(graph, comm, resolution, theta, rng)
        if len(set(refined)) == graph.n:
            break  # no sub-community formed: aggregation would give the same graph
        aggregated, node_of = _aggregate(graph, refined)
        next_comm = [0] * aggregated.n
        for v in range(graph.n):
            next_comm[node_of[v]] = comm[v]
        original_to_node = [node_of[original_to_node[v]] for v in range(g.n)]
        graph, comm = aggregated, _renumber(next_comm)
    distinct: list[list[int]] = []
    for level in levels:
        if not distinct or level != distinct[-1]:
            distinct.append(level)
    if len(distinct) > max_levels:
        distinct = [*distinct[: max_levels - 1], distinct[-1]]
    return distinct


def members_hash(member_ids: Iterable[str]) -> str:
    """Stable hash of a community's members (a stored summary is stale when it changes)."""
    digest = hashlib.sha256()
    for mid in sorted(member_ids):
        digest.update(mid.encode("utf-8"))
        digest.update(b"\x1f")
    return digest.hexdigest()


def community_label(member_names: Sequence[tuple[str, float]], k: int = 3) -> str:
    """A label from the ``k`` heaviest member names (``"Acme Corp · Globex · Initech"``)."""
    ranked = sorted(member_names, key=lambda nw: (-nw[1], nw[0]))
    names: list[str] = []
    for name, _ in ranked:
        if name and name not in names:
            names.append(name)
        if len(names) == k:
            break
    label = " · ".join(names)
    extra = len({n for n, _ in member_names}) - len(names)
    return f"{label} +{extra}" if extra > 0 else label


@dataclass(frozen=True, slots=True)
class CommunitySummaryInput:
    community: int
    size: int
    label: str
    members_hash: str
    top_members: tuple[tuple[int, str, str, float], ...]  # (node, name, type, weight)
    top_edges: tuple[tuple[int, int, float], ...]


def community_summary_inputs(
    membership: Sequence[int],
    nodes: Sequence[tuple[str, str, str]],
    g: CSRGraph,
    *,
    node_weight: Mapping[int, float] | Sequence[float] | None = None,
    min_size: int = 2,
    top_members: int = 20,
    top_edges: int = 20,
) -> list[CommunitySummaryInput]:
    """What a summariser needs per community: label, hash, heaviest members and edges.

    ``nodes[i]`` is ``(external_id, name, type)``; ``node_weight`` defaults to degree."""
    groups: dict[int, list[int]] = {}
    for v, c in enumerate(membership):
        groups.setdefault(c, []).append(v)

    def weight(v: int) -> float:
        if node_weight is None:
            return g.degree[v]
        return (
            float(node_weight[v])
            if not isinstance(node_weight, Mapping)
            else float(node_weight.get(v, 0.0))
        )

    out = []
    for c, members in groups.items():
        if len(members) < min_size:
            continue
        ranked = sorted(members, key=lambda v: (-weight(v), nodes[v][1]))
        names = [(nodes[v][1], weight(v)) for v in members]
        inside = set(members)
        edges = []
        for v in members:
            idx, ws = g.neighbours(v)
            for u, w in zip(idx, ws, strict=True):
                if u > v and u in inside:
                    edges.append((v, u, w))
        edges.sort(key=lambda e: -e[2])
        out.append(
            CommunitySummaryInput(
                c,
                len(members),
                community_label(names),
                members_hash(nodes[v][0] for v in members),
                tuple((v, nodes[v][1], nodes[v][2], weight(v)) for v in ranked[:top_members]),
                tuple(edges[:top_edges]),
            )
        )
    out.sort(key=lambda s: (-s.size, s.label))
    return out


COMMUNITY_SUMMARY_SYSTEM = (
    "You summarise one community of a knowledge graph for an enterprise knowledge base. Use only "
    "the entities, relations and passages given. Write 2-4 sentences: what connects these "
    "entities, the main relations, and anything notable in the passages. Cite passages as [n]. "
    "Do not invent facts, people or numbers."
)


def community_summary_prompt(
    summary: CommunitySummaryInput, passages: Sequence[str], *, max_chars: int = 6000
) -> str:
    """The user prompt for a community summary (pair it with ``COMMUNITY_SUMMARY_SYSTEM``):
    the label, the top members with their types, the heaviest internal relations by member
    name, and numbered evidence passages trimmed to ``max_chars`` in total."""
    names = {node: name for node, name, _, _ in summary.top_members}
    lines = [f"Community: {summary.label} ({summary.size} entities)", "Top entities:"]
    lines += [f"- {name} ({etype})" for _, name, etype, _ in summary.top_members]
    rel = [f"- {names[u]} <-> {names[v]} (weight {w:g})" for u, v, w in summary.top_edges
           if u in names and v in names]  # fmt: skip
    if rel:
        lines += ["Strongest relations:", *rel]
    budget = max_chars
    if passages:
        lines.append("Passages:")
    for i, passage in enumerate(passages, 1):
        text = " ".join(passage.split())[: max(0, budget)]
        if not text:
            break
        lines.append(f"[{i}] {text}")
        budget -= len(text)
    return "\n".join(lines)
