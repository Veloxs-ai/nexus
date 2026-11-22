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
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import GraphMappingConfig
from .embeddings import tokenize
from .io import get_path, read_json, write_json
from .lexical import STOPWORDS
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
        """Share of the document's graph neighbours (entities, tags, parent) named by the query.

        A neighbour matches when one of its values contains a query word as a whole token
        (so "an" does not match "parent"). Stopwords in ``query_terms`` are ignored.
        """
        document_node = f"document:{document_id}"
        with self._lock:
            neighbors = list(self.adjacency.get(document_node, ()))
            values = [_node_text(self.nodes.get(n)) for n in neighbors]

        if not neighbors:
            return 0.0

        terms = {
            token for term in query_terms for token in tokenize(str(term)) if token not in STOPWORDS
        }
        if not terms:
            return 0.0
        matches = sum(1 for text in values if text and not terms.isdisjoint(_tokens_of(text)))
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


def _node_text(node: dict[str, Any] | None) -> str:
    """The searchable values of a graph node (its ``type`` label is not content)."""
    if not node:
        return ""
    return " ".join(str(value) for key, value in node.items() if key != "type")


@lru_cache(maxsize=65536)
def _tokens_of(text: str) -> frozenset[str]:
    """Words of a node value; hyphenated names also match their parts ("invoice-guide")."""
    tokens = set(tokenize(text))
    tokens.update(part for token in list(tokens) if "-" in token for part in token.split("-"))
    tokens.discard("")
    return frozenset(tokens)


def ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
