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

from pathlib import Path
from typing import Any

from .config import CollectionConfig, RetrievalConfig
from .embeddings import HashingEmbedder
from .graph import KnowledgeGraph
from .io import get_path, read_jsonl
from .lexical import LexicalIndex
from .models import IndexedDocument, VectorEntry
from .vector_store import LocalVectorStore


def build_indexes(config: RetrievalConfig, base_dir: Path) -> int:
    embedder = HashingEmbedder(config.embedding.dimensions, config.embedding.normalize)
    # These stores are the file-backed build path: persistence is the whole
    # point of `build-index`, so opt out of the in-memory default that makes
    # save()/load() no-ops.
    vector_store = LocalVectorStore(config.stores.vector_index_uri, base_dir, in_memory_only=False)
    lexical_index = LexicalIndex(config.stores.lexical_index_uri, base_dir, in_memory_only=False)
    graph = KnowledgeGraph(config.stores.graph_index_uri, base_dir, in_memory_only=False)

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
