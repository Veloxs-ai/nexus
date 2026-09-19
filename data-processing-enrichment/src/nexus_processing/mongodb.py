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

"""Zero-dependency MongoDB document processor, BSON flattener, and Atlas index generator.

Processes semi-structured and hierarchical BSON/Extended-JSON documents, flattens
nested paths into dot-notation, normalizes Change Streams, and defines Atlas Vector Search indexes.
"""

from __future__ import annotations

import json
from typing import Any

MONGO_ATLAS_VECTOR_SEARCH_INDEX = {
    "fields": [
        {
            "type": "vector",
            "path": "embedding",
            "numDimensions": 3072,
            "similarity": "cosine",
        },
        {
            "type": "filter",
            "path": "collection_name",
        },
        {
            "type": "filter",
            "path": "document_id",
        },
    ]
}


def serialize_bson_value(val: Any) -> Any:
    """Recursively converts BSON and Extended-JSON representations into clean Python primitives."""
    if isinstance(val, dict):
        if "$oid" in val:
            return str(val["$oid"])
        if "$date" in val:
            date_val = val["$date"]
            if isinstance(date_val, dict) and "$numberLong" in date_val:
                return str(date_val["$numberLong"])
            return str(date_val)
        if "$numberDecimal" in val:
            return float(val["$numberDecimal"])
        if "$numberLong" in val:
            return int(val["$numberLong"])
        if "$binary" in val:
            return f"<Binary:{val.get('subType', '00')}>"
        return {k: serialize_bson_value(v) for k, v in val.items()}
    if isinstance(val, list):
        return [serialize_bson_value(item) for item in val]
    if hasattr(val, "__str__") and type(val).__name__ in ("ObjectId", "Decimal128", "Timestamp"):
        return str(val)
    return val


def flatten_mongo_document(doc: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flattens deeply nested MongoDB documents into dot-notation paths."""
    items: dict[str, Any] = {}
    cleaned_doc = serialize_bson_value(doc)

    for k, v in cleaned_doc.items():
        new_key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict) and v:
            items.update(flatten_mongo_document(v, prefix=new_key))
        elif isinstance(v, list):
            # If list of simple scalar elements, preserve as string array
            if v and all(isinstance(elem, str | int | float | bool) for elem in v):
                items[new_key] = json.dumps(v)
            elif v and all(isinstance(elem, dict) for elem in v):
                # Array of subdocuments: flatten first 5 elements
                for idx, subdoc in enumerate(v[:5]):
                    items.update(flatten_mongo_document(subdoc, prefix=f"{new_key}[{idx}]"))
            else:
                items[new_key] = json.dumps(v)
        else:
            items[new_key] = v

    return items


def serialize_mongo_document(
    doc: dict[str, Any], collection_name: str, flatten: bool = True
) -> str:
    """Transforms a MongoDB document into a structured, collection-grounded narrative chunk."""
    cleaned = serialize_bson_value(doc)
    doc_id = cleaned.get("_id", cleaned.get("id", "unknown_id"))

    header = f"[Collection: {collection_name} | ID: {doc_id}] "

    if flatten:
        flattened = flatten_mongo_document(cleaned)
        # Exclude redundant _id in body if present in header
        parts: list[str] = []
        for k, v in flattened.items():
            if k == "_id":
                continue
            if v is None:
                val_str = "NULL"
            else:
                val_str = str(v).replace("\r\n", " ").replace("\n", " ").strip()
            parts.append(f"{k}: {val_str}")
        return header + " | ".join(parts)

    body_json = json.dumps(cleaned, default=str)
    return header + body_json


def chunk_mongo_collection(
    documents: list[dict[str, Any]], collection_name: str, flatten: bool = True
) -> list[str]:
    """Transforms a list of MongoDB documents into structured contextual narratives."""
    return [
        serialize_mongo_document(d, collection_name=collection_name, flatten=flatten)
        for d in documents
    ]


def normalize_mongo_change_event(event: dict[str, Any]) -> dict[str, Any]:
    """Normalizes MongoDB Change Stream events (insert, update, replace, delete)."""
    op_type = event.get("operationType", event.get("op", "unknown")).lower()
    ns = event.get("ns", {})
    db_name = ns.get("db", event.get("db", "unknown_db"))
    coll_name = ns.get("coll", event.get("collection", "unknown_coll"))

    doc_key = event.get("documentKey", {})
    doc_id = serialize_bson_value(doc_key.get("_id", event.get("_id", "")))

    full_doc = serialize_bson_value(event.get("fullDocument", {}))
    update_desc = event.get("updateDescription", {})

    return {
        "operation": op_type.upper(),
        "database": db_name,
        "collection": coll_name,
        "document_id": str(doc_id),
        "document": full_doc,
        "updated_fields": update_desc.get("updatedFields", {}),
        "removed_fields": update_desc.get("removedFields", []),
        "timestamp_cluster": str(event.get("clusterTime", "")),
    }
