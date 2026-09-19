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

from nexus_processing.mongodb import (
    MONGO_ATLAS_VECTOR_SEARCH_INDEX,
    chunk_mongo_collection,
    flatten_mongo_document,
    normalize_mongo_change_event,
    serialize_bson_value,
    serialize_mongo_document,
)


def test_serialize_bson_value():
    bson_dict = {
        "_id": {"$oid": "507f1f77bcf86cd799439011"},
        "created_at": {"$date": "2026-09-19T18:00:00Z"},
        "balance": {"$numberDecimal": "999.95"},
        "large_id": {"$numberLong": "98765432109876"},
        "payload": {"$binary": {"base64": "ABCD", "subType": "00"}},
    }
    cleaned = serialize_bson_value(bson_dict)
    assert cleaned["_id"] == "507f1f77bcf86cd799439011"
    assert cleaned["created_at"] == "2026-09-19T18:00:00Z"
    assert cleaned["balance"] == 999.95
    assert cleaned["large_id"] == 98765432109876
    assert cleaned["payload"] == "<Binary:00>"


def test_flatten_mongo_document():
    doc = {
        "_id": "user_123",
        "profile": {
            "name": "Jane Doe",
            "contact": {
                "email": "jane@example.com",
                "phone": "+1-555-0100",
            },
        },
        "roles": ["admin", "developer"],
        "metadata": {
            "tags": ["active", "internal"],
        },
    }
    flattened = flatten_mongo_document(doc)
    assert flattened["_id"] == "user_123"
    assert flattened["profile.name"] == "Jane Doe"
    assert flattened["profile.contact.email"] == "jane@example.com"
    assert flattened["profile.contact.phone"] == "+1-555-0100"
    assert "admin" in flattened["roles"]
    assert "active" in flattened["metadata.tags"]


def test_serialize_mongo_document():
    doc = {
        "_id": {"$oid": "60a8b9f1e1f3a245d8b45678"},
        "title": "Quantum Computing Paper",
        "meta": {"author": "Dr. Smith", "citations": 42},
    }
    # Flattened
    narrative = serialize_mongo_document(doc, collection_name="articles", flatten=True)
    assert narrative.startswith("[Collection: articles | ID: 60a8b9f1e1f3a245d8b45678]")
    assert "title: Quantum Computing Paper" in narrative
    assert "meta.author: Dr. Smith" in narrative
    assert "meta.citations: 42" in narrative

    # Unflattened (raw JSON)
    unflat = serialize_mongo_document(doc, collection_name="articles", flatten=False)
    assert unflat.startswith("[Collection: articles | ID: 60a8b9f1e1f3a245d8b45678]")
    assert '"title": "Quantum Computing Paper"' in unflat


def test_chunk_mongo_collection():
    docs = [
        {"_id": "doc1", "value": 10},
        {"_id": "doc2", "value": 20},
    ]
    chunks = chunk_mongo_collection(docs, collection_name="metrics")
    assert len(chunks) == 2
    assert "[Collection: metrics | ID: doc1]" in chunks[0]
    assert "[Collection: metrics | ID: doc2]" in chunks[1]


def test_normalize_mongo_change_event():
    change_stream_event = {
        "operationType": "insert",
        "ns": {"db": "analytics", "coll": "events"},
        "documentKey": {"_id": {"$oid": "60a8b9f1e1f3a245d8b45678"}},
        "fullDocument": {
            "_id": {"$oid": "60a8b9f1e1f3a245d8b45678"},
            "type": "pageview",
            "page": "/home",
        },
        "clusterTime": "Timestamp(1726765200, 1)",
    }
    normalized = normalize_mongo_change_event(change_stream_event)
    assert normalized["operation"] == "INSERT"
    assert normalized["database"] == "analytics"
    assert normalized["collection"] == "events"
    assert normalized["document_id"] == "60a8b9f1e1f3a245d8b45678"
    assert normalized["document"]["type"] == "pageview"


def test_mongo_atlas_vector_search_index():
    assert "fields" in MONGO_ATLAS_VECTOR_SEARCH_INDEX
    vector_field = next(
        f for f in MONGO_ATLAS_VECTOR_SEARCH_INDEX["fields"] if f["type"] == "vector"
    )
    assert vector_field["path"] == "embedding"
    assert vector_field["numDimensions"] == 3072
    assert vector_field["similarity"] == "cosine"
