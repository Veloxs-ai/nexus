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

from pathlib import Path
from typing import Any

from nexus_retrieval.config import CollectionConfig, RetrievalConfig
from nexus_retrieval.embeddings import HashingEmbedder
from nexus_retrieval.graph import KnowledgeGraph
from nexus_retrieval.io import get_path, read_jsonl
from nexus_retrieval.lexical import LexicalIndex
from nexus_retrieval.models import IndexedDocument, VectorEntry
from nexus_retrieval.vector_store import LocalVectorStore


def build_indexes(config: RetrievalConfig, base_dir: Path) -> int:
    embedder = HashingEmbedder(config.embedding.dimensions, config.embedding.normalize)
    vector_store = LocalVectorStore(config.stores.vector_index_uri, base_dir)
    lexical_index = LexicalIndex(config.stores.lexical_index_uri, base_dir)
    graph = KnowledgeGraph(config.stores.graph_index_uri, base_dir)

    count = 0
    for collection_name, collection in config.collections.items():
        for raw_record in read_jsonl(collection.input_uri, base_dir):
            document = build_document(collection_name, collection, raw_record)
            vector_store.add(
                VectorEntry(
                    id=document.id,
                    collection=document.collection,
                    text=document.text,
                    embedding=embedder.embed(document.text),
                    metadata=document.metadata,
                )
            )
            lexical_index.add(document)
            graph.add_document(document, collection.graph)
            count += 1

    vector_store.save()
    lexical_index.save()
    graph.save()
    return count


def build_document(
    collection_name: str,
    collection: CollectionConfig,
    record: dict[str, Any],
) -> IndexedDocument:
    doc_id = str(get_path(record, collection.id_field))
    text = extract_text(record, collection)
    metadata = get_path(record, collection.metadata_field, {}) or {}
    return IndexedDocument(
        id=doc_id,
        collection=collection_name,
        text=text,
        metadata=metadata,
        source=record,
    )


def extract_text(record: dict[str, Any], collection: CollectionConfig) -> str:
    if collection.text_field:
        return str(get_path(record, collection.text_field, ""))
    values = [str(get_path(record, field, "")) for field in collection.text_fields]
    return " ".join(value for value in values if value)

