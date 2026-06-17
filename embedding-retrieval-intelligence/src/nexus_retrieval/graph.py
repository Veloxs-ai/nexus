# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from nexus_retrieval.config import GraphMappingConfig
from nexus_retrieval.io import get_path, read_json, write_json
from nexus_retrieval.models import IndexedDocument


class KnowledgeGraph:
    def __init__(self, uri: str, base_dir: Path) -> None:
        self.uri = uri
        self.base_dir = base_dir
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: list[dict[str, str]] = []
        self.adjacency: dict[str, set[str]] = defaultdict(set)

    def add_document(self, document: IndexedDocument, mapping: GraphMappingConfig) -> None:
        document_node = f"document:{document.id}"
        self.nodes[document_node] = {"type": "document", "id": document.id}

        if mapping.parent_field:
            parent = get_path(document.source, mapping.parent_field)
            if parent:
                parent_node = f"parent:{parent}"
                self.nodes[parent_node] = {"type": "parent", "id": str(parent)}
                self.add_edge(document_node, "PART_OF", parent_node)

        for field in mapping.entity_fields:
            for value in ensure_list(get_path(document.source, field, [])):
                entity_node = f"entity:{value}"
                self.nodes[entity_node] = {"type": "entity", "value": str(value)}
                self.add_edge(document_node, "MENTIONS", entity_node)

        for field in mapping.tag_fields:
            for value in ensure_list(get_path(document.source, field, [])):
                tag_node = f"tag:{value}"
                self.nodes[tag_node] = {"type": "tag", "value": str(value)}
                self.add_edge(document_node, "TAGGED_AS", tag_node)

    def add_edge(self, source: str, relationship: str, target: str) -> None:
        self.edges.append({"source": source, "relationship": relationship, "target": target})
        self.adjacency[source].add(target)
        self.adjacency[target].add(source)

    def score(self, document_id: str, query_terms: list[str]) -> float:
        document_node = f"document:{document_id}"
        neighbors = self.adjacency.get(document_node, set())
        if not neighbors:
            return 0.0

        normalized_terms = [term.lower() for term in query_terms]
        matches = 0
        for neighbor in neighbors:
            node = self.nodes.get(neighbor, {})
            haystack = " ".join(str(value).lower() for value in node.values())
            if any(term in haystack for term in normalized_terms):
                matches += 1
        return matches / len(neighbors)

    def save(self) -> None:
        write_json(self.uri, self.base_dir, {"nodes": self.nodes, "edges": self.edges})

    def load(self) -> None:
        payload = read_json(self.uri, self.base_dir)
        self.nodes = payload.get("nodes", {})
        self.edges = payload.get("edges", [])
        self.adjacency = defaultdict(set)
        for edge in self.edges:
            self.adjacency[edge["source"]].add(edge["target"])
            self.adjacency[edge["target"]].add(edge["source"])


def ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]

