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
nested paths into dot-notation (change streams: see nexus_processing.cdc).
"""

from __future__ import annotations

import json
from typing import Any



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
            return str(val["$numberDecimal"])
        if "$numberLong" in val:
            return int(val["$numberLong"])
        if "$numberInt" in val:
            return int(val["$numberInt"])
        if "$numberDouble" in val:
            return float(val["$numberDouble"])
        if "$binary" in val:
            bin_data = val["$binary"]
            if isinstance(bin_data, dict):
                sub = bin_data.get("subType", "00")
                b64 = bin_data.get("base64", "")
            else:
                sub = val.get("subType", "00")
                b64 = ""
            if sub == "04" and b64:  # UUID
                import base64
                import uuid as _uuid
                try:
                    raw = base64.b64decode(b64)
                    if len(raw) == 16:
                        return str(_uuid.UUID(bytes=raw))
                except Exception:
                    pass
            return f"<Binary:{sub}>"
        if "$regex" in val:
            return f"/{val['$regex']}/{val.get('$options', '')}"
        if "$timestamp" in val:
            ts = val["$timestamp"]
            return f"Timestamp({ts.get('t', 0)}, {ts.get('i', 0)})"
        if "$code" in val:
            return str(val["$code"])
        if "$minKey" in val:
            return "MinKey"
        if "$maxKey" in val:
            return "MaxKey"
        return {k: serialize_bson_value(v) for k, v in val.items()}
    if isinstance(val, list):
        return [serialize_bson_value(item) for item in val]
    if hasattr(val, "__str__") and type(val).__name__ in ("ObjectId", "Decimal128", "Timestamp"):
        return str(val)
    return val


def flatten_mongo_document(
    doc: dict[str, Any], prefix: str = "", _pre_cleaned: bool = False
) -> dict[str, Any]:
    """Flattens deeply nested MongoDB documents into dot-notation paths."""
    items: dict[str, Any] = {}
    cleaned_doc = doc if _pre_cleaned else serialize_bson_value(doc)

    for k, v in cleaned_doc.items():
        new_key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict) and v:
            items.update(flatten_mongo_document(v, prefix=new_key, _pre_cleaned=_pre_cleaned))
        elif isinstance(v, list):
            # If list of simple scalar elements, preserve as string array
            if v and all(isinstance(elem, str | int | float | bool) for elem in v):
                items[new_key] = json.dumps(v)
            elif v and all(isinstance(elem, dict) for elem in v):
                # Array of subdocuments: flatten first 10 elements
                for idx, subdoc in enumerate(v[:10]):
                    items.update(
                        flatten_mongo_document(
                            subdoc,
                            prefix=f"{new_key}[{idx}]",
                            _pre_cleaned=_pre_cleaned,
                        )
                    )
                if len(v) > 10:
                    items[f"{new_key}._truncated"] = f"{len(v) - 10} more items"
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
        flattened = flatten_mongo_document(cleaned, _pre_cleaned=True)
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


