# Copyright 2026 Veloxs AI Inc.
# SPDX-License-Identifier: Apache-2.0
"""Records queries: profiles, spec v2 resolution, the Python engine and SQL parity (SQLite)."""

from __future__ import annotations

import json
import random
import re
import sqlite3

import pytest

from nexus.record_eval import bucket, evaluate, query_records
from nexus.record_spec import (
    RecordQueryError,
    key_text,
    normalize_value,
    number_of,
    parse_spec,
    text_of,
)
from nexus.record_sql import ChunkTable, compile_query, read_result, unicode_lower
from nexus.table_profile import DISTINCT_CAP, link_columns, profile_records, profile_text

TICKETS = [
    {"id": 101, "customer": "Asha", "status": "open", "amount": 300},
    {"id": 102, "customer": "Meera", "status": "closed", "amount": 120},
    {"id": 103, "customer": "Vikram", "status": "open", "amount": 1000},
    {"id": 104, "customer": "Neha", "status": "OPEN", "amount": 80},
]


# -- value semantics -------------------------------------------------------------------------
def test_value_semantics():
    assert text_of(True) == "true" and text_of(1.5) == "1.5" and text_of(None) is None
    assert number_of(" 12.50 ") == 12.5 and number_of(True) is None and number_of("1e5") is None
    assert number_of("5.") is None and number_of("-3") == -3.0
    assert key_text(1.0) == "1" == key_text(" 1 ") and key_text("ACME ") == "acme"
    assert normalize_value("MID_MARKET ") == normalize_value("Mid-Market") == "mid market"
    assert (
        bucket("2026-02-11T10:00:00Z", "week") == "2026-02-09"
        and bucket("2026-11-30", "quarter") == "2026-Q4"
    )
    assert bucket("2025-02-30", "week") is None and bucket("11/02/2026", "month") is None


# -- profiles ----------------------------------------------------------------------------------
def test_profile_types_values_and_ranges():
    rows = [
        {
            "id": i,
            "amount": f"{i}.5",
            "day": f"2026-01-{1 + i % 28:02d}",
            "plan": ["Gold", "Silver"][i % 2],
            "ok": i % 2 == 0,
            "addr": {"city": "Pune"},
            "note": None if i % 4 else "x",
        }
        for i in range(100)
    ]
    profile = profile_records(rows)
    cols = {c["name"]: c for c in profile["columns"]}
    assert profile["rows"] == 100
    assert cols["id"]["type"] == "integer" and cols["id"]["min"] == 0 and cols["id"]["max"] == 99
    assert cols["amount"]["type"] == "number" and cols["day"]["type"] == "date"
    assert cols["day"]["min"] == "2026-01-01" and cols["ok"]["type"] == "boolean"
    assert cols["plan"]["values_complete"] and [v for v, _ in cols["plan"]["values"]] == [
        "Gold",
        "Silver",
    ]
    assert cols["addr.city"]["path"] == ["addr", "city"] and cols["addr"]["type"] == "object"
    assert cols["note"]["nulls"] == 75 and cols["note"]["null_pct"] == 75.0
    assert not cols["id"]["values_complete"] and len(cols["id"]["top"]) <= 10
    text = profile_text(profile)
    assert "id (integer; 0 to 99; unique)" in text and "plan (text; 2 values: Gold, Silver)" in text
    assert "note (text; 1 value: x; 75% empty)" in text


def test_profile_memory_is_bounded():
    profile = profile_records([{"k": f"v{i}"} for i in range(DISTINCT_CAP + 500)])
    col = profile["columns"][0]
    assert col["distinct"] == DISTINCT_CAP and col["distinct_capped"] and not col["values_complete"]


def test_column_linking_only_when_many_columns():
    small = {"t": profile_records([{"region": "North", "amount": 1}])}
    assert link_columns("total amount by region", small) is None
    wide = {
        f"t{i}": profile_records([{f"c{j}": "x" for j in range(10)} | {"region": "North"}])
        for i in range(6)
    }
    linked = link_columns("orders in the North region", wide, max_columns=12)
    assert (
        all("region" in cols for cols in linked.values()) and sum(map(len, linked.values())) <= 12
    )


# -- the spec ------------------------------------------------------------------------------------
def test_v1_specs_still_work():
    count = query_records(
        TICKETS, {"metric": "count", "filters": [{"field": "Status", "op": "eq", "value": "open"}]}
    )
    assert count.matched == 3 and count.text == "Result: 3"
    total = query_records(
        TICKETS,
        {
            "metric": "sum",
            "field": "amount",
            "filters": [{"field": "amount", "op": "gte", "value": "100"}],
        },
    )
    assert total.text == "Result: 1,420 (over 3 matching record(s))"
    grouped = query_records(TICKETS, {"metric": "count", "group_by": "status"})
    assert "| open | 3 |" in grouped.text and "| closed | 1 |" in grouped.text
    listed = query_records(
        TICKETS,
        {
            "metric": "list",
            "filters": [{"field": "customer", "op": "in", "value": ["Asha", "Neha"]}],
        },
    )
    assert listed.matched == 2 and listed.listed == 2 and "Vikram" not in listed.text


@pytest.mark.parametrize(
    "spec, message",
    [
        (
            {"metric": "count", "filters": [{"field": "priority", "op": "eq", "value": "x"}]},
            "unknown filter field",
        ),
        (
            {"metric": "count", "filters": [{"field": "status", "op": "like", "value": "x"}]},
            "unknown operator",
        ),
        ({"metric": "median", "field": "amount"}, "unknown metric"),
        (
            {"metric": "count", "having": [{"field": "count", "op": "gt", "value": 1}]},
            "having needs group_by",
        ),
        (
            {
                "group_by": "status",
                "metric": "count",
                "having": [{"field": "total", "op": "gt", "value": 1}],
            },
            "not a metric",
        ),
        (
            {
                "group_by": "status",
                "metric": "count",
                "having": [{"field": "count", "op": "gt", "value": "x"}],
            },
            "compares",
        ),
        ({"group_by": [{"field": "status", "date_trunc": "decade"}]}, "unknown date_trunc"),
        (
            {"metric": "count", "join": {"document": "x", "on": {"customer": "name"}}},
            "has no profiled fields",
        ),
    ],
)
def test_bad_specs_say_why(spec, message):
    with pytest.raises(RecordQueryError, match=message):
        parse_spec(spec, profile_records(TICKETS))


def test_values_match_stored_spellings_and_missing_values_say_closest():
    rows = [{"seg": s} for s in ["Mid-Market", "mid market", "MID_MARKET ", "Enterprise", "SMB"]]
    hit = query_records(
        rows, {"metric": "count", "where": {"field": "seg", "op": "eq", "value": "mid market"}}
    )
    assert hit.matched == 3 and "matched the stored value(s)" not in hit.text
    typo = query_records(
        rows, {"metric": "count", "where": {"field": "seg", "op": "eq", "value": "Enterprize"}}
    )
    assert (
        typo.kind == "not_found"
        and "'Enterprise' (1 rows)" in typo.text
        and "Result" not in typo.text
    )
    either = query_records(
        rows, {"metric": "count", "where": {"field": "seg", "op": "in", "value": ["SMB", "Nope"]}}
    )
    assert either.matched == 1 and "No record has seg has no value 'Nope'" in either.text
    stale = parse_spec(
        {"metric": "count", "where": {"field": "seg", "op": "eq", "value": "Nope"}},
        profile_records(rows),
        current=False,
    )
    assert not stale.impossible  # a stale profile never claims a value is missing


def test_v2_features_in_the_python_engine():
    rows = [
        {
            "id": i,
            "c": ["A", "B", "C"][i % 3],
            "amt": i * 10,
            "day": f"2026-{1 + i % 4:02d}-15",
            "tag": None if i % 5 == 0 else "t",
            "addr": {"city": ["Pune", "Delhi"][i % 2]},
        }
        for i in range(1, 31)
    ]
    top = query_records(
        rows,
        {
            "group_by": ["c"],
            "metrics": [{"op": "sum", "field": "amt", "as": "total"}],
            "order_by": [{"by": "total", "dir": "desc"}],
            "limit": 2,
        },
    )
    assert (
        [r[0] for r in top.rows] == ["A", "C"] and top.groups == 3 and "1 more group" in top.text
    )  # 1650, 1550
    months = query_records(
        rows,
        {
            "group_by": [{"field": "day", "date_trunc": "month"}],
            "metric": "count",
            "having": [{"field": "count", "op": "gte", "value": 8}],
            "order_by": [{"by": "day", "dir": "asc"}],
        },
    )
    assert [r[0] for r in months.rows] == ["2026-02", "2026-03"] and months.matched == 16
    logic = query_records(
        rows,
        {
            "metric": "count",
            "where": {
                "or": [
                    {"field": "tag", "op": "is_null"},
                    {"not": {"field": "amt", "op": "lt", "value": 290}},
                ]
            },
        },
    )
    assert logic.matched == 6 + 1  # ids 5..30 step 5, plus id 29
    multi = query_records(
        rows,
        {
            "metrics": [
                {"op": "count_distinct", "field": "c"},
                {"op": "max", "field": "day"},
                {"op": "avg", "field": "amt"},
            ]
        },
    )
    assert multi.rows == [[3, "2026-04-15", 155.0]]
    listed = query_records(
        rows,
        {
            "metric": "list",
            "fields": ["id", "addr.city"],
            "limit": 3,
            "where": {"field": "addr.city", "op": "eq", "value": "pune"},
            "order_by": [{"by": "amt", "dir": "desc"}],
        },
    )
    assert listed.rows == [["30", "Pune"], ["28", "Pune"], ["26", "Pune"]] and listed.matched == 15


def test_joins_on_declared_keys():
    orders = [
        {"id": i, "cust": c, "amt": a}
        for i, (c, a) in enumerate([("acme", 10), ("ACME ", 5), ("Hooli", 7), ("Nobody", 1)])
    ]
    people = [{"name": "Acme", "seg": "Ent"}, {"name": "hooli", "seg": "SMB"}]
    inner = query_records(
        orders,
        {
            "metric": "sum",
            "field": "amt",
            "join": {"document": "people", "as": "p", "on": {"cust": "name"}},
            "where": {"field": "p.seg", "op": "eq", "value": "ent"},
        },
        join_records=people,
    )
    assert inner.text.startswith("Result: 15")
    left = query_records(
        orders,
        {
            "group_by": ["p.seg"],
            "metric": "count",
            "join": {"document": "people", "as": "p", "on": {"cust": "name"}, "type": "left"},
        },
        join_records=people,
    )
    assert sorted(map(tuple, left.rows), key=str) == sorted(
        [("Ent", 2), ("SMB", 1), ("(empty)", 1)], key=str
    )


# -- SQL: parity with the Python engine on SQLite --------------------------------------------------
def _store(rows: list[dict], layout: str, doc: str, db: sqlite3.Connection) -> None:
    for i, row in enumerate(rows):
        if layout == "records" or (layout == "mixed" and i % 2):
            meta = {"records": [row], "other": 1}
        else:
            meta = {"record": row}
        db.execute("INSERT INTO ch VALUES (?, ?, ?)", (doc, i, json.dumps(meta)))
    db.execute(
        "INSERT INTO ch VALUES (?, -1, ?)", (doc, json.dumps({"node": "section"}))
    )  # outline: no rows


def _random_rows(rng: random.Random, n: int) -> list[dict]:
    return [
        {
            "id": i,
            "c": rng.choice(["Acme", "acme ", "Hooli", "Initech", None]),
            "s": rng.choice(["open", "shipped", "OPEN", "", None]),
            "amt": rng.choice(
                [round(rng.uniform(1, 900), 2), str(rng.randrange(5, 60)), " 7 ", "n/a", None, 0]
            ),
            "day": rng.choice(
                [
                    f"202{rng.randrange(5, 7)}-{rng.randrange(1, 13):02d}-"
                    f"{rng.randrange(1, 29):02d}",
                    "2026-03-04T09:00:00Z",
                    " 2026-05-06",
                    "soon",
                    None,
                ]
            ),
            "ok": rng.choice([True, False, 1, None]),
            "addr": {"city": rng.choice(["Pune", "Delhi", "pune"])},
        }
        for i in range(n)
    ]


SPECS = [
    {"metric": "count"},
    {"metric": "count", "where": {"field": "c", "op": "eq", "value": "acme"}},
    {"metric": "count", "where": {"field": "amt", "op": "in", "value": [7, "n/a", 0]}},
    {
        "metric": "sum",
        "field": "amt",
        "where": {
            "or": [
                {"field": "s", "op": "eq", "value": "open"},
                {"not": {"field": "amt", "op": "gt", "value": 500}},
            ]
        },
    },
    {
        "metrics": [
            {"op": "count"},
            {"op": "avg", "field": "amt"},
            {"op": "min", "field": "day"},
            {"op": "max", "field": "amt"},
            {"op": "count_distinct", "field": "c"},
            {"op": "min", "field": "c"},
        ]
    },
    {
        "metric": "count",
        "where": {
            "and": [{"field": "s", "op": "is_null"}, {"field": "ok", "op": "eq", "value": True}]
        },
    },
    {"metric": "count", "where": {"field": "s", "op": "is_null", "value": False}},
    {"metric": "count", "where": {"field": "c", "op": "contains", "value": "CM"}},
    {"metric": "count", "where": {"field": "day", "op": "gte", "value": "2026-01-01"}},
    {"metric": "count", "where": {"field": "amt", "op": "lt", "value": "100"}},
    {"metric": "count", "where": {"field": "s", "op": "ne", "value": "open"}},
    {"group_by": "c", "metric": "count"},
    {
        "group_by": ["s", "c"],
        "metrics": [{"op": "sum", "field": "amt", "as": "t"}],
        "order_by": [{"by": "t"}],
        "limit": 4,
    },
    {
        "group_by": [{"field": "day", "date_trunc": "month"}],
        "metric": "count",
        "order_by": [{"by": "day", "dir": "asc"}],
    },
    {
        "group_by": [{"field": "day", "date_trunc": "week"}],
        "metric": "count",
        "having": [{"field": "count", "op": "gte", "value": 2}],
        "limit": 5,
    },
    {
        "group_by": [
            {"field": "day", "date_trunc": "quarter"},
            {"field": "day", "date_trunc": "year"},
        ],
        "metric": "count",
    },
    {
        "group_by": [{"field": "day", "date_trunc": "day"}],
        "metrics": [{"op": "max", "field": "c", "as": "m"}],
        "order_by": [{"by": "m", "dir": "asc"}],
        "limit": 6,
    },
    {
        "group_by": "addr.city",
        "metrics": [{"op": "avg", "field": "amt"}],
        "having": [{"field": "avg", "op": "gt", "value": 10}],
    },
    {"metric": "list", "limit": 7},
    {
        "metric": "list",
        "fields": ["id", "amt"],
        "order_by": [{"by": "amt", "dir": "desc"}],
        "limit": 9,
    },
    {
        "metric": "list",
        "fields": ["id", "day"],
        "order_by": [{"by": "day"}, {"by": "id", "dir": "asc"}],
        "limit": 9,
    },
    {"metric": "count", "where": {"field": "c", "op": "eq", "value": "Acmee"}},
    {
        "metric": "sum",
        "field": "amt",
        "join": {"document": "p", "as": "p", "on": {"c": "name"}},
        "where": {"field": "p.seg", "op": "eq", "value": "mid market"},
    },
    {
        "group_by": ["p.seg"],
        "metric": "count",
        "join": {"document": "p", "as": "p", "on": {"c": "name"}, "type": "left"},
    },
    {
        "metric": "list",
        "fields": ["id", "p.seg"],
        "limit": 5,
        "join": {"document": "p", "as": "p", "on": {"id": "code"}},
    },
]
PEOPLE = [
    {"name": "ACME", "seg": "Mid-Market", "code": "3"},
    {"name": "hooli", "seg": "mid market", "code": 5.0},
    {"name": "Initech", "seg": "SMB", "code": 7},
    {"name": "acme", "seg": "MID_MARKET", "code": None},
]


@pytest.mark.parametrize("layout", ["record", "records", "mixed"])
def test_sql_equals_the_python_engine(layout):
    rng = random.Random(f"records-{layout}")
    rows = _random_rows(rng, 600)
    db = sqlite3.connect(":memory:")
    unicode_lower(db)
    db.execute("CREATE TABLE ch (doc TEXT, chunk_index INT, metadata TEXT)")
    _store(rows, layout, "o", db)
    _store(PEOPLE, "mixed", "p", db)
    profile, people = profile_records(rows), profile_records(PEOPLE)
    src = ChunkTable(
        "ch",
        "c.doc = ? AND c.chunk_index >= 0",
        ("o",),
        layout=layout if layout != "mixed" else "mixed",
    )
    join = ChunkTable("ch", "c.doc = ? AND c.chunk_index >= 0", ("p",))
    for spec in SPECS:
        q = parse_spec(spec, profile, people if spec.get("join") else None)
        expected = evaluate(q, rows, PEOPLE)
        if q.impossible:
            assert expected.kind == "not_found"
            continue
        compiled = compile_query(q, "sqlite", src, join)
        got = read_result(compiled, db.execute(compiled.sql, compiled.params).fetchall(), len(rows))
        assert (got.text, got.matched, got.listed, got.groups) == (
            expected.text,
            expected.matched,
            expected.listed,
            expected.groups,
        ), spec


def test_sql_is_parameterised_for_both_dialects():
    nasty = "x'); DROP TABLE ch; --"
    q = parse_spec(
        {
            "metric": "count",
            "where": {
                "or": [
                    {"field": "c", "op": "eq", "value": nasty},
                    {"field": "c", "op": "contains", "value": "?:p0%"},
                ]
            },
            "group_by": [{"field": "day", "date_trunc": "week"}],
        },
        profile_records(_random_rows(random.Random(1), 50)),
    )
    src = ChunkTable('"t"', "c.doc = ?", ("o",))
    for dialect, mark in (("postgresql", "%s"), ("sqlite", "?")):
        compiled = compile_query(q, dialect, src, placeholder=mark)
        assert nasty not in compiled.sql and "DROP" not in compiled.sql
        assert compiled.sql.count(mark) == len(compiled.params)
        assert (
            "x'); drop table ch; --" in compiled.params
        )  # the value travels folded, as a parameter
        if dialect == "postgresql":
            assert "?" not in compiled.sql and "%" not in compiled.sql.replace("%s", "")
            assert not re.search(
                r"(?<!:):\w", compiled.sql
            )  # no bind-like ":name" for SQLAlchemy text()
            assert "jsonb_array_elements" in compiled.sql and 'COLLATE "C"' in compiled.sql


def test_unicode_lower_folds_like_python():
    db = sqlite3.connect(":memory:")
    assert db.execute("SELECT lower('ÄRGER')").fetchone()[0] == "Ärger"
    unicode_lower(db)
    assert db.execute("SELECT lower('ÄRGER')").fetchone()[0] == "ärger"
