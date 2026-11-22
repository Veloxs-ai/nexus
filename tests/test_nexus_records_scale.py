# Copyright 2026 Veloxs AI Inc.
# SPDX-License-Identifier: Apache-2.0
"""Records at table scale: one row per record with typed slots, rollups, index advice and
pgvector helpers. Every engine must give the Python engine's answer exactly."""

from __future__ import annotations

import json
import math
import random
import re
import sqlite3

import pytest
from test_nexus_records_query import PEOPLE, SPECS, _random_rows, _store

from nexus.index_advice import expression_index_sql, recommend_indexes, sql_literal
from nexus.record_eval import evaluate
from nexus.record_slots import (
    date_slot,
    number_slot,
    plan_slots,
    slot_columns,
    slot_values,
    text_slot,
)
from nexus.record_spec import RecordQueryError, parse_spec
from nexus.record_sql import ChunkTable, compile_query, read_result, unicode_lower
from nexus.table_profile import profile_records
from nexus.table_rollups import answer_from_rollups, apply_row_change, build_rollups
from nexus.vector_sql import choose_strategy, knn_sql, vector_index_ddl

SLOT_COLUMNS = (
    [f"t{i} TEXT" for i in range(1, 9)]
    + [f"n{i} NUMERIC" for i in range(1, 9)]
    + [f"d{i} TEXT" for i in range(1, 5)]
)


def _row_table(db: sqlite3.Connection, rows: list[dict], slot_map: dict | None, doc: str) -> None:
    db.execute(
        "CREATE TABLE IF NOT EXISTS rec (doc TEXT, row_no INT, record TEXT, "
        + ", ".join(SLOT_COLUMNS)
        + ")"
    )
    for i, row in enumerate(rows):
        values = slot_values(row, slot_map) if slot_map else {}
        cols = ["doc", "row_no", "record", *values]
        db.execute(
            f"INSERT INTO rec ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
            (doc, i, json.dumps(row), *values.values()),
        )


def _close(a, b) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        return a is not None and b is not None and math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)
    return a == b


def _same_rows(got, expected, spec):
    """Rows equal up to float summation order (an exact decimal sum vs a running float sum
    can round a last digit differently, e.g. an average of 369.465 shown as .46 or .47)."""
    assert (got.kind, got.matched, got.listed, got.groups) == (
        expected.kind,
        expected.matched,
        expected.listed,
        expected.groups,
    ), spec
    assert len(got.rows) == len(expected.rows), spec
    for a, b in zip(got.rows, expected.rows, strict=True):
        assert all(_close(x, y) for x, y in zip(a, b, strict=True)), (spec, a, b)


def _same(got, expected, spec):
    assert (got.text, got.matched, got.listed, got.groups) == (
        expected.text,
        expected.matched,
        expected.listed,
        expected.groups,
    ), spec


def _extra_rows(rng: random.Random, n: int) -> list[dict]:
    """Values that a slot can and cannot hold exactly, side by side."""
    pick = rng.choice
    return [
        {
            "id": i,
            "n": pick(
                [
                    7, "7", " 7 ", 7.25, "7.50", "007", 1234567.891234, -0.5, "-0", 0.0001,
                    None, "x",
                    "0.12345678901234567", 123456.78901234, "98765432109876.5",
                ]
            ),
            "w": pick(
                [
                    "2026-03-04",
                    "2026-03-04T09:30:00Z",
                    "2026-03-04T00:00:00Z",
                    "2026-02-30",
                    " 2026-01-01",
                    "2026-05-06T10:00:00+02:00",
                    None,
                    "later",
                ]
            ),
            "k": pick(["A-1", "a-1 ", True, False, 3, 2.5, {"o": 1}, [1], "", None]),
            # a number slot column: mostly short numbers, a few that only the JSON holds exactly
            "m": pick([7, 2.5, "12.25", -4, 1000, 0.125] * 6
                      + ["0.12345678901234567", 0.30000000000000004, 12345678.9012345]),
        }
        for i in range(n)
    ]


EXTRA_SPECS = [
    {"metric": "sum", "field": "n"},
    {"metric": "count", "where": {"field": "n", "op": "eq", "value": 7}},
    {"metric": "count", "where": {"field": "n", "op": "in", "value": ["7.5", "x"]}},
    {"group_by": "n", "metric": "count", "limit": 20},
    {"group_by": [{"field": "w", "date_trunc": "month"}], "metric": "count"},
    {"group_by": "w", "metric": "count", "limit": 20},
    {"metric": "count", "where": {"field": "w", "op": "gte", "value": "2026-03-04"}},
    {"metrics": [{"op": "min", "field": "w"}, {"op": "max", "field": "w"}]},
    {"group_by": "k", "metric": "count", "limit": 20},
    {"metric": "count", "where": {"field": "k", "op": "eq", "value": "a-1"}},
    {"metric": "count", "where": {"field": "k", "op": "eq", "value": "[1]"}},
    {"metric": "count", "where": {"field": "k", "op": "in", "value": ['{"o":1}', "a-1"]}},
    {"metric": "count", "where": {"field": "n", "op": "eq", "value": "0.12345678901234567"}},
    {
        "group_by": "k",
        "metric": "count",
        "where": {"field": "k", "op": "ne", "value": "x"},
        "limit": 20,
    },
    {"metric": "list", "fields": ["id", "n", "w", "k"], "order_by": [{"by": "n"}], "limit": 30},
    {"group_by": "m", "metric": "count", "limit": 20},
    {"metric": "list", "fields": ["id", "m"], "order_by": [{"by": "m"}], "limit": 400},
    {"metric": "count", "where": {"field": "m", "op": "eq", "value": 0.30000000000000004}},
]


@pytest.mark.parametrize("slots", [None, (8, 8, 4), (1, 1, 1)])
def test_row_layout_equals_the_python_engine(slots):
    rng = random.Random(f"rows-{slots}")
    rows, extra = _random_rows(rng, 600), _extra_rows(rng, 400)
    db = sqlite3.connect(":memory:")
    unicode_lower(db)
    db.execute("CREATE TABLE ch (doc TEXT, chunk_index INT, metadata TEXT)")
    _store(PEOPLE, "mixed", "p", db)
    join = ChunkTable("ch", "c.doc = ? AND c.chunk_index >= 0", ("p",))
    for doc, data, specs in (("o", rows, SPECS), ("x", extra, EXTRA_SPECS)):
        profile = profile_records(data)
        slot_map = plan_slots(profile, *slots, sample=data) if slots else None
        _row_table(db, data, slot_map, doc)
        src = ChunkTable(
            "rec",
            "c.doc = ?",
            (doc,),
            metadata="record",
            order="row_no",
            layout="row",
            columns=slot_columns(slot_map) if slot_map else None,
        )
        for spec in specs:
            q = parse_spec(spec, profile, profile_records(PEOPLE) if spec.get("join") else None)
            expected = evaluate(q, data, PEOPLE)
            if q.impossible:
                continue
            compiled = compile_query(q, "sqlite", src, join)
            got = db.execute(compiled.sql, compiled.params).fetchall()
            _same(read_result(compiled, got, len(data)), expected, spec)


def test_slot_values_hold_only_what_reads_back_exactly():
    assert [text_slot(v) for v in ("a ", True, 3, 2.5, 1e20, None, {"x": 1})] == [
        "a ",
        "true",
        "3",
        "2.5",
        None,
        None,
        None,
    ]
    assert [
        number_slot(v)
        for v in (
            3,
            "3",
            "12.5",
            12.5,
            "12.50",
            "007",
            "-0",
            1e20,
            0.0001,
            "0.001",
            True,
            2**60,
            1234567.891234,
        )
    ] == [
        3,
        3,
        12.5,
        12.5,
        None,
        None,
        None,
        None,
        None,
        0.001,
        None,
        None,
        1234567.891234,
    ]
    assert date_slot("2026-03-04") == "2026-03-04T00:00:00Z"
    assert date_slot("2026-03-04T09:30:00Z") == "2026-03-04T09:30:00Z"
    assert [date_slot(v) for v in ("2026-03-04T00:00:00Z", "2026-02-30", " 2026-03-04", 5)] == [
        None,
        None,
        None,
        None,
    ]


def test_plan_slots_keys_and_categories_first():
    rows = [
        {
            "note": f"free text {i % 7}" if i % 3 else None,
            "id": f"SO-{i}",
            "region": "NESW"[i % 4],
            "amount": round(i * 1.5 + 0.25, 2),
            "day": f"2026-01-{i % 28 + 1:02d}",
            "meta": {"a": i},
        }
        for i in range(200)
    ]
    plan = plan_slots(
        profile_records(rows), text=2, number=1, date=1, sample=rows, exclude=["meta.a"]
    )
    got = [(s["name"], s["kind"], s["column"]) for s in plan["slots"]]
    assert got[:2] == [("id", "text", "t1"), ("amount", "number", "n1")]
    assert ("region", "text", "t2") in got and ("day", "date", "d1") in got
    assert all(s["name"] not in ("meta", "note") for s in plan["slots"])  # object, slots full
    assert slot_values(rows[3], plan) == {
        "t1": "SO-3",
        "n1": 4.75,
        "t2": "W",
        "d1": "2026-01-04T00:00:00Z",
    }
    renamed = plan_slots(profile_records(rows), 1, 0, 0, names={"text": "s_"})
    assert renamed["slots"] == [{"path": ["id"], "name": "id", "kind": "text", "column": "s_1"}]


def test_row_source_sql_is_parameterised_and_index_friendly():
    rows = _random_rows(random.Random(3), 80)
    profile = profile_records(rows)
    plan = plan_slots(profile, 0, 1, 1, sample=rows)  # id in a number slot, texts in JSON
    src = ChunkTable(
        "rec",
        "c.doc = ?",
        ("o",),
        metadata="record",
        order="row_no",
        layout="row",
        columns=slot_columns(plan),
    )
    spec = {
        "metric": "count",
        "where": {
            "and": [
                {"field": "id", "op": "eq", "value": 12},
                {"field": "c", "op": "in", "value": ["Acme", "Hooli"]},
                {"field": "addr.city", "op": "eq", "value": "Pune"},
                {"field": "s", "op": "contains", "value": "x'); DROP TABLE rec; --"},
            ]
        },
    }
    q = parse_spec(spec, profile)
    for dialect, mark in (("postgresql", "%s"), ("sqlite", "?")):
        compiled = compile_query(q, dialect, src, placeholder=mark)
        assert "DROP" not in compiled.sql and compiled.sql.count(mark) == len(compiled.params)
        assert " OR c." in compiled.sql  # slot hints keep rows that read the JSON
        if dialect == "postgresql":
            assert not re.search(r"(?<!:):\w", compiled.sql) and "?" not in compiled.sql
            assert "(c.record #>> %s)" in compiled.sql  # an unslotted field: folded JSON hint
    with pytest.raises(RecordQueryError):
        compile_query(q, "sqlite", ChunkTable("ch", "TRUE", columns={"id": ("t1", "text")}))
    with pytest.raises(RecordQueryError):
        bad = ChunkTable("rec", "TRUE", layout="row", columns={"id": ("t1; DROP", "text")})
        compile_query(q, "sqlite", bad)


# -- rollups ---------------------------------------------------------------------------------
def _rollup_rows(rng: random.Random, n: int) -> list[dict]:
    return [
        {
            "region": rng.choice(["North", "north ", "South", "East", "", None]),
            "status": rng.choice(["open", "OPEN", "closed", "pending"]),
            "qty": rng.choice([1, 2, 3, "3", 4.0, None]),
            "amount": rng.choice([round(rng.uniform(1, 999), 2), str(rng.randrange(1, 90)), None]),
            "day": rng.choice(
                [
                    f"2025-{rng.randrange(1, 13):02d}-{rng.randrange(1, 28):02d}",
                    "2026-01-05T10:00:00Z",
                    None,
                ]
            ),
            "flag": rng.choice([True, False, None]),
        }
        for _ in range(n)
    ]


def _random_spec(rng: random.Random) -> dict:
    metric = rng.choice(
        [
            {"op": "count"},
            {"op": "sum", "field": "amount"},
            {"op": "avg", "field": "amount"},
            {"op": "min", "field": "amount"},
            {"op": "max", "field": "qty"},
            {"op": "count_distinct", "field": "region"},
        ]
    )
    column = rng.choice(["region", "status", "qty", "flag"])
    value = {
        "region": ["north", "South", ""],
        "status": ["open", "closed"],
        "qty": [3, 1],
        "flag": [True, False],
    }[column]
    where = rng.choice(
        [
            None,
            {"field": column, "op": "eq", "value": rng.choice(value)},
            {"field": column, "op": "in", "value": value},
            {"field": column, "op": "ne", "value": value[0]},
            {"field": column, "op": "is_null", "value": rng.choice([True, False])},
            {"not": {"field": column, "op": "contains", "value": "o"}},
        ]
    )
    spec: dict = {"metrics": [metric, {"op": "count"}]}
    if where:
        spec["where"] = where
    shape = rng.random()
    if shape < 0.4:
        spec["group_by"] = column
    elif shape < 0.6:
        spec["group_by"] = [{"field": "day", "date_trunc": "month"}]
        spec.pop("where", None)
    if "group_by" in spec and rng.random() < 0.5:
        spec["having"] = [{"field": "count", "op": "gte", "value": rng.randrange(1, 40)}]
        spec["order_by"] = [{"by": "count", "dir": rng.choice(["asc", "desc"])}]
        spec["limit"] = rng.randrange(1, 6)
    return spec


def test_rollups_equal_the_engines_on_random_specs():
    rng = random.Random("rollups")
    rows = _rollup_rows(rng, 900)
    profile = profile_records(rows)
    rollups = json.loads(json.dumps(build_rollups(rows, profile)))  # survives JSON storage
    db = sqlite3.connect(":memory:")
    unicode_lower(db)
    _row_table(db, rows, None, "r")
    src = ChunkTable("rec", "c.doc = ?", ("r",), metadata="record", order="row_no", layout="row")
    answered = 0
    for _ in range(1500):
        spec = _random_spec(rng)
        q = parse_spec(spec, profile)
        got = answer_from_rollups(q, rollups)
        if got is None:
            continue
        answered += 1
        _same_rows(got, evaluate(q, rows), spec)
        if not q.impossible:
            compiled = compile_query(q, "sqlite", src)
            sql = read_result(compiled, db.execute(compiled.sql, compiled.params).fetchall(), 900)
            _same_rows(sql, got, spec)
    assert answered > 1000
    unsupported = parse_spec(
        {
            "metric": "count",
            "where": {
                "and": [
                    {"field": "region", "op": "eq", "value": "south"},
                    {"field": "status", "op": "eq", "value": "open"},
                ]
            },
        },
        profile,
    )
    assert answer_from_rollups(unsupported, rollups) is None  # two columns: scan instead


def test_rollups_follow_row_changes():
    rng = random.Random("changes")
    rows = _rollup_rows(rng, 300)
    profile = profile_records(rows)
    rollups = build_rollups(rows, profile)
    current = list(rows)
    for step in range(400):
        action = rng.random()
        if action < 0.3 and current:
            old = current.pop(rng.randrange(len(current)))
            apply_row_change(rollups, old, None)
        elif action < 0.6:
            new = _rollup_rows(rng, 1)[0]
            current.append(new)
            apply_row_change(rollups, None, new)
        elif current:
            at = rng.randrange(len(current))
            new = _rollup_rows(rng, 1)[0]
            apply_row_change(rollups, current[at], new)
            current[at] = new
        if step % 40 == 0:
            for _ in range(30):
                spec = _random_spec(rng)
                q = parse_spec(spec, profile)
                got = answer_from_rollups(q, rollups)
                if got is not None:
                    _same_rows(got, evaluate(q, current), spec)
    assert rollups["rows"] == len(current)


# -- index advice and DDL --------------------------------------------------------------------
def test_recommend_indexes_and_expression_sql():
    rows = [
        {
            "order_no": f"SO-{i}",
            "region": "NESW"[i % 4],
            "amount": i,
            "day": "2026-01-01",
            "customer": f"C{i % 900}",
        }
        for i in range(5000)
    ]
    profile = profile_records(rows)
    asked = [{"metric": "count", "where": {"field": "customer", "op": "eq", "value": "C1"}}] * 3
    asked += [
        {
            "metric": "count",
            "where": {
                "and": [
                    {"field": "region", "op": "eq", "value": "N"},
                    {"field": "amount", "op": "gt", "value": 5},
                ]
            },
        }
    ]
    advice = recommend_indexes(profile, asked, max_indexes=5)
    assert [(a.name, a.reason) for a in advice] == [
        ("customer", "lookup"),
        ("amount", "range"),
        ("order_no", "key"),
    ]
    assert recommend_indexes(profile, asked, exclude=["customer"])[0].name == "amount"
    ddl = expression_index_sql(
        "store.records",
        "record",
        "customer",
        lead=["document_id"],
        where_sql="document_id = " + sql_literal("d'1"),
        concurrently=True,
    )
    assert ddl.startswith("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_records_")
    assert "(document_id, (lower(btrim((record #>> '{\"customer\"}'), E' \\t\\r\\n'))))" in ddl
    assert ddl.endswith("WHERE document_id = 'd''1'")
    slot = expression_index_sql("rec", "t1", None, "sqlite", name="ix_t1")
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE rec (t1 TEXT, record TEXT)")
    db.execute(slot)
    db.execute(expression_index_sql("rec", "record", ["a", "b"], "sqlite"))
    with pytest.raises(ValueError):
        expression_index_sql("rec; DROP TABLE x", "record", "a")


def test_vector_helpers():
    assert choose_strategy(30_000, 10_000_000).kind == "exact"
    big = choose_strategy(60_000, 10_000_000, k=40)
    assert big.kind == "hnsw" and big.max_scan_tuples == 26_666 and big.ef_search == 100
    assert choose_strategy(5_000_000, 10_000_000).max_scan_tuples == 20_000
    ddl = vector_index_ddl(
        "kc", "embedding", 384, quantize="halfvec", where_sql="kind <> 1", concurrently=True
    )
    assert ddl == (
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_kc_embedding_hnsw ON kc USING hnsw "
        "((CAST(embedding AS halfvec(384))) halfvec_cosine_ops) WITH (m = 16, "
        "ef_construction = 64) WHERE kind <> 1"
    )
    hnsw = knn_sql(
        "kc", "embedding", 384, quantize="halfvec", where_sql="ws = %s", select="id", strategy=big
    )
    assert (
        "CAST(embedding AS halfvec(384)) <=> CAST(CAST(%s AS vector(384)) AS halfvec(384))"
        in hnsw.sql
    )
    assert hnsw.sql.endswith("WHERE (ws = %s) ORDER BY distance LIMIT 40")
    assert hnsw.settings[-1] == "SET LOCAL hnsw.max_scan_tuples = 26666"
    exact = knn_sql("kc", "embedding", 384, select="id", strategy=choose_strategy(10, 20))
    assert "((embedding <=> CAST(%s AS vector(384))) + 0)" in exact.sql and not exact.settings
    with pytest.raises(ValueError):
        knn_sql("kc", "embedding", 384, quantize="int8")
