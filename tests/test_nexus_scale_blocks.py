# Copyright 2026 Veloxs AI Inc.
# SPDX-License-Identifier: Apache-2.0
"""Table-scale building blocks: the faster profile (same output), row hashes, the embedding
policy and a reusable document routing index."""

from __future__ import annotations

import json
import random
from typing import Any

from nexus.doc_routing import DocumentIndex, rank_documents
from nexus.record_values import ISO_DATE_RE, NUMBER_RE, WS, text_of
from nexus.table_profile import DISTINCT_CAP, MAX_VALUE_CHARS, key_like, profile_records
from nexus.table_records import embed_policy, needs_vector, row_hash


def _reference_profile(records: list[Any]) -> dict[str, Any]:
    """The 3.4.0 profile loop (one ``add`` per value, no caches), for equivalence."""
    columns: dict[tuple, dict] = {}

    def add(c: dict, value: Any) -> None:
        kind = type(value)
        if value is None or (kind is str and not value.strip(WS)):
            return
        c["present"] += 1
        if kind is bool:
            k = "boolean"
        elif kind is int or kind is float:
            k = "integer" if kind is int else "number"
            c["nums"].append(float(value))
        elif kind is str:
            if NUMBER_RE.match(value):
                k = "number" if "." in value else "integer"
                c["nums"].append(float(value))
            elif ISO_DATE_RE.match(value.strip(WS)):
                k = "date"
                c["days"].append(value.strip(WS))
            else:
                k = "text"
        elif kind is dict:
            k = "object"
        elif kind is list:
            k = "array"
        else:
            k = "text"
        c["kinds"][k] = c["kinds"].get(k, 0) + 1
        text = None if k in ("object", "array") else text_of(value)
        if text is None:
            return
        if text in c["values"]:
            c["values"][text] += 1
        elif len(c["values"]) < DISTINCT_CAP and len(text) <= MAX_VALUE_CHARS:
            c["values"][text] = 1
        else:
            c["overflow"] = True

    rows = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        rows += 1
        for key, value in record.items():
            for path, inner in [((str(key),), value)] + (
                [((str(key), str(s)), v) for s, v in value.items()] if type(value) is dict else []
            ):
                c = columns.setdefault(
                    path,
                    {
                        "present": 0,
                        "kinds": {},
                        "values": {},
                        "overflow": False,
                        "nums": [],
                        "days": [],
                    },
                )
                add(c, inner)
    return {"rows": rows, "columns": {p: c for p, c in columns.items()}}


def test_profile_is_unchanged_by_the_caches():
    rng = random.Random(9)
    pick = rng.choice
    rows = [
        {
            "id": i,
            "c": pick(
                [
                    "Acme",
                    "acme ",
                    " ",
                    "",
                    None,
                    "7",
                    "7.5",
                    "2026-01-02",
                    True,
                    3,
                    2.5,
                    {"x": 1},
                    [1],
                ]
            ),
            "amt": pick(
                [
                    round(rng.uniform(1, 900), 2),
                    str(rng.randrange(5, 60)),
                    " 7 ",
                    "n/a",
                    None,
                    0,
                    float("nan"),
                    float("inf"),
                ]
            ),
            "free": f"t{rng.randrange(0, 6000)}",
            "addr": {"city": pick(["Pune", "Delhi", None])},
            1: "number key",
            "long": "x" * pick([5, 200]),
        }
        for i in range(12000)
    ]
    got = profile_records(rows)
    ref = _reference_profile(rows)
    assert got["rows"] == ref["rows"]
    for column in got["columns"]:
        c = ref["columns"][tuple(column["path"])]
        assert column["nulls"] == ref["rows"] - c["present"], column["name"]
        assert column["distinct"] == len(c["values"]) and column["distinct_capped"] == c["overflow"]
        if column.get("values_complete"):
            assert dict(map(tuple, column["values"])) == c["values"]
        if column["type"] in ("integer", "number") and c["nums"]:
            assert json.dumps([column["min"], column["max"]]) == json.dumps(
                [min(c["nums"]), max(c["nums"])]
            )
        if column["type"] == "date":
            assert [column["min"], column["max"]] == [min(c["days"]), max(c["days"])]
    assert json.dumps(profile_records(rows)) == json.dumps(got)  # deterministic


def test_key_like_columns():
    rows = [{"id": f"K{i}", "region": "NS"[i % 2]} for i in range(3000)]
    profile = profile_records(rows)
    by_name = {c["name"]: c for c in profile["columns"]}
    assert key_like(by_name["id"], 3000) and not key_like(by_name["region"], 3000)
    assert key_like(profile_records(rows[:10])["columns"][0], 10)


def test_row_hash_ignores_key_order_and_excluded_keys():
    a = {"id": 1, "name": "Ä", "when": "2026-01-01", "n": 1.5}
    b = {"n": 1.5, "when": "2026-01-01", "name": "Ä", "id": 1, "_seen": 7}
    assert row_hash(a) == row_hash(b, exclude=["_seen"]) and len(row_hash(a)) == 40
    assert row_hash(a) != row_hash({**a, "n": 1.6})


def test_embed_policy_embeds_only_rows_with_free_text():
    orders = [
        {
            "order_no": f"SO-{i}",
            "region": "NESW"[i % 4],
            "amount": i * 1.5,
            "day": "2026-01-01",
            "sku": f"SKU-{i % 3000}",
        }
        for i in range(5000)
    ]
    policy = embed_policy(profile_records(orders), orders)
    assert policy["embed"] == "none" and not needs_vector(orders[0], policy)
    tickets = [
        {
            "id": i,
            "status": "open",
            "body": None
            if i % 3 == 0
            else f"Customer {i} reports the screen stays black after the latest update",
        }
        for i in range(300)
    ]
    policy = embed_policy(profile_records(tickets), tickets)
    assert policy["embed"] == "rows_with_text" and policy["text_columns"] == [["body"]]
    assert needs_vector(tickets[1], policy) and not needs_vector(tickets[0], policy)
    unsure = embed_policy(profile_records(tickets))  # no rows to look at: embed everything
    assert unsure["embed"] == "all" and needs_vector(tickets[0], unsure)


def test_document_index_ranks_like_rank_documents():
    rng = random.Random(5)
    words = [
        "invoice",
        "contract",
        "renewal",
        "pricing",
        "audit",
        "north",
        "Globex",
        "Orion",
        "warranty",
        "escalation",
        "policy",
        "travel",
    ]
    docs = [
        {
            "document_id": f"d{i % 1500}",
            "document_name": f"{rng.choice(words)}_{i}.pdf",
            "summary": " ".join(rng.choice(words) for _ in range(30)),
        }
        for i in range(1600)  # duplicate ids too
    ]
    index = DocumentIndex.build(docs, version=7)
    assert len(index) == 1600 and index.version == 7
    for question in ("Orion contract renewal pricing", "travel policy", "nothing matches", ""):
        kwargs = {"vector": ["d3", "d9"], "named": ["d5"], "limit": 25, "include_unmatched": True}
        expected = rank_documents(question, docs, **kwargs)
        assert index.rank(question, **kwargs) == expected
