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

import random

from nexus_processing.graph_structured import (
    EntityColumn,
    ForeignKey,
    RowEntitySpec,
    detect_foreign_keys,
    infer_entity_columns,
    infer_row_entity,
    is_masked,
    pk_index_for,
    structured_graph,
)


def _col(name, ctype="text", distinct=10, nulls=0, values=None, capped=False):
    c = {
        "name": name,
        "type": ctype,
        "distinct": distinct,
        "nulls": nulls,
        "distinct_capped": capped,
    }
    if values is not None:
        c["values"] = values
    return c


def _profile(rows, *cols):
    return {"v": 1, "rows": rows, "columns": list(cols)}


def test_infer_entity_columns_rules():
    profile = _profile(
        1000,
        _col("customer", distinct=20, values=[["Acme Corp", 60], ["Globex", 40]]),
        _col("assignee", distinct=30, values=[["Priya N.", 10]]),
        _col("status", distinct=3, values=[["open", 500]]),  # enum
        _col("order_no", distinct=1000),  # too unique
        _col("region", distinct=1),  # one value
        _col("amount", "number", distinct=900),
        _col("opened", "date", distinct=300),
        _col("email", distinct=200),  # PII by name
        _col("contact", distinct=200),  # PII by classifier
        _col("notes", distinct=500, values=[["word " * 20, 1]]),  # free text
        _col("sku", distinct=300, values=[["SKU-1", 3], ["SKU-2", 3]]),  # codes
        _col("vendor_ref", distinct=0),
    )
    cols = infer_entity_columns(profile, column_kinds={"contact": "phone"})
    assert [(c.name, c.type, c.relation) for c in cols] == [
        ("customer", "org", "customer"),
        ("assignee", "person", "assignee"),
    ]


def test_typed_columns_have_no_lower_distinct_ratio():
    profile = _profile(
        200_000,
        _col("customer", distinct=21, values=[["Acme Corp", 9000], ["Globex", 8000]]),
        _col("assignee", distinct=12, values=[["Priya N.", 20000]]),
        _col("region", distinct=4, values=[["North", 50000]]),
        _col("product", distinct=30, values=[["Widget", 7000]]),
        _col("channel", distinct=5, values=[["web", 90000]]),  # no type from its name: too few
    )
    cols = infer_entity_columns(profile)
    assert [(c.name, c.type) for c in cols] == [
        ("customer", "org"),
        ("assignee", "person"),
        ("region", "place"),
        ("product", "product"),
    ]
    records = [
        (f"o{i}", {"customer": ["Acme Corp", "Globex"][i % 2], "product": "Widget", "channel": "web"})
        for i in range(10)
    ]
    x = structured_graph(records, cols[:1] + cols[3:], table="orders")
    assert {(r.src_key, r.dst_key, r.type) for r in x.relations} >= {("acme corp", "widget", "product")}


def test_hints_override_and_capped_columns():
    profile = _profile(
        100_000,
        _col("owner", distinct=1000, capped=True),
        _col("code_x", distinct=1000, capped=True),
        _col("channel", distinct=8),
        _col("priority", distinct=4),
    )
    cols = infer_entity_columns(profile, hints={"priority": "attribute", "channel": "org"})
    assert [(c.name, c.type) for c in cols] == [("owner", "person"), ("channel", "org")]
    assert infer_entity_columns(profile, exclude=["owner"]) == []


def test_infer_row_entity():
    profile = _profile(
        20, _col("customer_id", distinct=20), _col("name", distinct=20), _col("segment", distinct=3)
    )
    spec = infer_row_entity(profile, primary_key="customer_id", table="public.customers")
    assert spec == RowEntitySpec("customer_id", "name", "org", True)
    dup = _profile(20, _col("id", "integer", distinct=20), _col("title", distinct=18))
    spec = infer_row_entity(dup, primary_key="id", table="documents")
    assert spec is not None and spec.type == "record" and not spec.unique_names
    assert infer_row_entity(profile, primary_key=None) is None
    assert (
        infer_row_entity(
            _profile(5, _col("id", "integer", 5), _col("amount", "number", 5)), primary_key="id"
        )
        is None
    )


def test_structured_graph_values_relations_and_masking():
    rows = [
        ("t1", {"customer": "Acme Corp", "assignee": "Priya N.", "status": "open"}),
        ("t2", {"customer": "ACME Corp.", "assignee": "[EMAIL]"}),
        ("t3", {"customer": None, "assignee": "Priya N."}),
        ("t4", {"customer": "Globex", "assignee": "Priya N."}),
    ]
    cols = [
        EntityColumn("customer", "org", "customer"),
        EntityColumn("assignee", "person", "assignee"),
    ]
    x = structured_graph(rows, cols, table="tickets")
    ents = {e.ref: e for e in x.entities}
    assert set(ents) == {("org", "acme corp"), ("person", "n priya"), ("org", "globex")}
    assert (
        ents[("org", "acme corp")].name in ("Acme Corp", "ACME Corp.")
        and ents[("org", "acme corp")].origin == "structured"
    )
    assert all(m.method == "field" and m.start == -1 for m in x.mentions)
    assert not any("EMAIL" in m.surface for m in x.mentions)  # masked values never become entities
    rels = {(r.src_key, r.dst_key, r.type, r.chunk_key) for r in x.relations}
    assert rels == {
        ("acme corp", "n priya", "assignee", "t1"),
        ("globex", "n priya", "assignee", "t4"),
    }
    assert ("priya n", "Priya N.", "n priya") in {
        (a.alias_key, a.alias, a.entity_key) for a in x.aliases
    }
    assert x.stats["rows"] == 4


def test_row_entities_foreign_keys_and_pk_aliases():
    customers = [
        {"customer_id": "CU-1", "name": "Acme Corp"},
        {"customer_id": "CU-2", "name": "Globex"},
    ]
    spec = RowEntitySpec("customer_id", "name", "org", True)
    cx = structured_graph(
        [(f"c:{r['customer_id']}", r) for r in customers], [], table="customers", row_entity=spec
    )
    assert {e.key for e in cx.entities} == {"acme corp", "globex"}
    assert dict(next(e for e in cx.entities if e.key == "acme corp").attributes) == {
        "table": "customers",
        "pk": "CU-1",
    }
    assert ("cu 1", "acme corp", "structured_id") in {
        (a.alias_key, a.entity_key, a.source) for a in cx.aliases
    }
    index = {"customers": pk_index_for(customers, spec)}
    orders = [
        ("o1", {"order_no": "SO-1", "customer_id": "CU-1", "city": "Pune"}),
        ("o2", {"order_no": "SO-2", "customer_id": "CU-9", "city": "Pune"}),
    ]
    ox = structured_graph(
        orders,
        [EntityColumn("city", "place", "city")],
        table="orders",
        foreign_keys=[ForeignKey("customer_id", "customers", "customer_id")],
        pk_index=index,
    )
    fk = [m for m in ox.mentions if m.method == "fk"]
    assert [(m.entity_key, m.surface, m.field) for m in fk] == [
        ("acme corp", "CU-1", "customer_id")
    ]
    assert ("pune", "acme corp", "customer") in {
        (r.src_key, r.dst_key, r.type) for r in ox.relations
    }


def test_row_entities_with_duplicate_names_keep_their_keys_apart():
    spec = RowEntitySpec("id", "name", "record", unique_names=False)
    rows = [("a", {"id": 1, "name": "Main"}), ("b", {"id": 2, "name": "Main"})]
    x = structured_graph(rows, [], table="sites", row_entity=spec)
    assert {e.key for e in x.entities} == {"main#1", "main#2"}


def test_detect_foreign_keys_by_containment():
    rng = random.Random(1)
    customers = [{"customer_id": f"CU-{i}", "name": f"Customer {i}"} for i in range(30)]
    orders = [
        {
            "id": i,
            "customer": rng.choice(customers)["name"],
            "cust_ref": rng.choice(customers)["customer_id"],
            "qty": rng.randrange(1, 30),
        }
        for i in range(200)
    ]
    profiles = {
        "customers": _profile(30, _col("customer_id", distinct=30), _col("name", distinct=30)),
        "orders": _profile(
            200,
            _col("id", "integer", 200),
            _col("customer", distinct=30),
            _col("cust_ref", distinct=30),
            _col("qty", "integer", 29),
        ),
    }
    fks = detect_foreign_keys(
        profiles, {"customers": customers, "orders": orders}, primary_keys={"orders": "id"}
    )
    got = {(f.column, f.ref_table, f.ref_column) for f in fks}
    assert ("customer", "customers", "name") in got
    assert ("cust_ref", "customers", "customer_id") in got
    assert not any(f.column == "qty" for f in fks)  # small integers need a key-like name


def test_is_masked():
    assert (
        is_masked("[EMAIL]")
        and is_masked("[EMAIL:0a1b2c3d4e]")
        and is_masked("<PERSON>")
        and is_masked("****")
    )
    assert not is_masked("Acme Corp") and not is_masked("[draft]")


def test_structured_throughput_smoke():
    rng = random.Random(2)
    rows = [
        (f"r{i}", {"customer": f"C{rng.randrange(300)}", "owner": f"P{rng.randrange(80)}"})
        for i in range(20_000)
    ]
    cols = [EntityColumn("customer", "org", "customer"), EntityColumn("owner", "person", "owner")]
    x = structured_graph(rows, cols, table="t")
    assert len(x.mentions) == 40_000 and len(x.relations) == 20_000
