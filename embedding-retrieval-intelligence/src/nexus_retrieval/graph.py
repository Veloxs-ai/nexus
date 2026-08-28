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

import threading
from collections import defaultdict
from pathlib import Path
from typing import Any

from .config import GraphMappingConfig
from .io import get_path, read_json, write_json
from .models import IndexedDocument


class KnowledgeGraph:
    def __init__(
        self,
        uri: str = "data/indexes/graph_index.json",
        base_dir: Path | None = None,
        in_memory_only: bool = True,
    ) -> None:
        self.uri = uri
        self.base_dir = base_dir or Path.cwd()
        self.in_memory_only = in_memory_only
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: list[dict[str, str]] = []
        self.adjacency: dict[str, set[str]] = defaultdict(set)
        self._lock = threading.Lock()

    def add_document(self, document: IndexedDocument, mapping: GraphMappingConfig) -> None:
        document_node = f"document:{document.id}"
        with self._lock:
            self.nodes[document_node] = {"type": "document", "id": document.id}

            if mapping.parent_field:
                parent = get_path(document.source, mapping.parent_field)
                if parent:
                    parent_node = f"parent:{parent}"
                    self.nodes[parent_node] = {"type": "parent", "id": str(parent)}
                    self._add_edge_unlocked(document_node, "PART_OF", parent_node)

            for field in mapping.entity_fields:
                for value in ensure_list(get_path(document.source, field, [])):
                    entity_node = f"entity:{value}"
                    self.nodes[entity_node] = {"type": "entity", "value": str(value)}
                    self._add_edge_unlocked(document_node, "MENTIONS", entity_node)

            for field in mapping.tag_fields:
                for value in ensure_list(get_path(document.source, field, [])):
                    tag_node = f"tag:{value}"
                    self.nodes[tag_node] = {"type": "tag", "value": str(value)}
                    self._add_edge_unlocked(document_node, "TAGGED_AS", tag_node)

    def _add_edge_unlocked(self, source: str, relationship: str, target: str) -> None:
        self.edges.append({"source": source, "relationship": relationship, "target": target})
        self.adjacency[source].add(target)
        self.adjacency[target].add(source)

    def add_edge(self, source: str, relationship: str, target: str) -> None:
        with self._lock:
            self._add_edge_unlocked(source, relationship, target)

    def score(self, document_id: str, query_terms: list[str]) -> float:
        document_node = f"document:{document_id}"
        with self._lock:
            neighbors = set(self.adjacency.get(document_node, set()))
            nodes_snapshot = {n: dict(self.nodes[n]) for n in neighbors if n in self.nodes}

        if not neighbors:
            return 0.0

        normalized_terms = [term.lower() for term in query_terms]
        matches = 0
        for neighbor in neighbors:
            node = nodes_snapshot.get(neighbor, {})
            haystack = " ".join(str(value).lower() for value in node.values())
            if any(term in haystack for term in normalized_terms):
                matches += 1
        return matches / len(neighbors)

    def save(self) -> None:
        if self.in_memory_only:
            return  # Pure in-memory bypass
        with self._lock:
            payload = {"nodes": self.nodes, "edges": self.edges}
        write_json(self.uri, self.base_dir, payload)

    def load(self) -> None:
        if self.in_memory_only:
            return
        try:
            payload = read_json(self.uri, self.base_dir)
            with self._lock:
                self.nodes = payload.get("nodes", {})
                self.edges = payload.get("edges", [])
                self.adjacency = defaultdict(set)
                for edge in self.edges:
                    self.adjacency[edge["source"]].add(edge["target"])
                    self.adjacency[edge["target"]].add(edge["source"])
        except Exception:
            pass


def ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
