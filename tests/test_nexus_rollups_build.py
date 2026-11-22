# Copyright 2026 Veloxs AI Inc.
# SPDX-License-Identifier: Apache-2.0
"""3.4.2 fast paths: the block-wise ``build_rollups``, ``apply_row_changes``, and the shortcuts of
``row_hash`` and ``cap_record_values`` give exactly what the row-at-a-time forms give."""

from __future__ import annotations

import hashlib
import json
import random

import pytest

from nexus import table_rollups_build
from nexus.record_eval import evaluate
from nexus.record_spec import parse_spec
from nexus.table_profile import profile_records
from nexus.table_records import row_hash, row_hash_json
from nexus.table_rollups import (
    _as_json,
    _change,
    _indexes,
    answer_from_rollups,
    apply_row_change,
    apply_row_changes,
    build_rollups,
)
from nexus_processing.record_caps import TRUNCATED_KEY, _cap, cap_record_values

VALUES = [
    None,
    "",
    " x ",
    "X",
    "x",
    1,
    1.0,
    True,
    False,
    "1e3",
    1000.0,
    "1000",
    3.25,
    "3.25",
    -0.5,
    "2025-03-04",
    "2025-03-04T10:00:00Z",
    "2024-12-31",
    "bad-date",
    0,
    "0",
    {"a": 1},
    [1, 2],
    float("nan"),
    float("inf"),
    "  12 ",
    10**20,
    "1E2",
    "abc",
    "-0",
    2**60,
    "y" * 50,
]


def _one_by_one(rows, profile, max_groups=50):
    """The rollups of ``rows`` added one at a time (the 3.4.1 build)."""
    out = build_rollups([], profile, max_groups=max_groups)
    indexes = _indexes(out)
    for row in rows:
        if isinstance(row, dict):
            _change(out, row, 1, indexes)
    return _as_json(out)


def _rows(rng: random.Random, n: int, columns: int) -> list:
    out: list = []
    for _ in range(n):
        if rng.random() < 0.01:
            out.append("not a row")
            continue
        row = {}
        for c in range(columns):
            pool = VALUES if c % 2 else VALUES[: rng.randint(2, len(VALUES))]
            if rng.random() < 0.9:
                row[f"c{c}"] = (
                    rng.choice(pool)
                    if c != 4
                    else rng.choice([rng.uniform(-5, 5), rng.randint(0, 80)])
                )
        if rng.random() < 0.3:
            row["nest"] = {"k": rng.choice(["a", "b", 2, None, 2.5])}
        out.append(row)
    return out


@pytest.mark.parametrize("block", [1, 7, 8192])
def test_block_build_equals_adding_rows_one_by_one(monkeypatch, block):
    monkeypatch.setattr(table_rollups_build, "BLOCK_ROWS", block)
    rng = random.Random(f"build-{block}")
    for _ in range(60 if block > 1 else 15):
        rows = _rows(rng, rng.choice([0, 1, 40, 700, 2500]), rng.randint(1, 6))
        dicts = [r for r in rows if isinstance(r, dict)]
        profile = profile_records(dicts[: rng.choice([5, 100, 5000])])
        groups = rng.choice([3, 50])
        expected = _one_by_one(rows, profile, groups)
        got = build_rollups(iter(rows), profile, max_groups=groups)  # any iterable, read once
        assert json.dumps(got) == json.dumps(expected)  # same groups, order, labels and decimals


def test_a_column_past_its_group_cap_stops_where_one_by_one_does():
    rows = [{"k": str(i % 9), "v": i} for i in range(100)] + [
        {"k": f"new{i}", "v": i} for i in range(6)
    ]
    rows += [{"k": "0", "v": 5}]  # after the column stopped: not counted in its groups
    profile = profile_records(rows[:40])
    for groups in (10, 50):
        assert build_rollups(rows, profile, max_groups=groups) == _one_by_one(rows, profile, groups)
    stopped = build_rollups(rows, profile, max_groups=10)["columns"][0]
    assert not stopped["exact"] and sum(g["rows"] for g in stopped["groups"]) == 101


def test_apply_row_changes_equals_one_change_at_a_time():
    rng = random.Random("batch")
    rows = [r for r in _rows(rng, 400, 5) if isinstance(r, dict)]
    profile = profile_records(rows)
    one, many = build_rollups(rows, profile), build_rollups(rows, profile)
    current, changes = list(rows), []
    for _ in range(300):
        new = [r for r in _rows(rng, 3, 5) if isinstance(r, dict)][:1] or [{}]
        if current and rng.random() < 0.4:
            changes.append((current.pop(rng.randrange(len(current))), None))
        elif current and rng.random() < 0.5:
            at = rng.randrange(len(current))
            changes.append((current[at], new[0]))
            current[at] = new[0]
        else:
            changes.append((None, new[0]))
            current.append(new[0])
    for old, new in changes:
        apply_row_change(one, old, new)
    assert apply_row_changes(many, changes) is many
    assert json.dumps(one) == json.dumps(many) and many["rows"] == len(current)
    q = parse_spec({"metric": "count", "group_by": "c0"}, profile)
    got = answer_from_rollups(q, many)
    if got is not None:
        expected = evaluate(q, current)
        assert (got.kind, got.matched, got.groups) == (
            expected.kind,
            expected.matched,
            expected.groups,
        )


def test_row_hash_shortcut_gives_the_same_digest():
    def reference(record, exclude=()):
        body = {str(k): v for k, v in record.items() if k not in set(exclude)}
        text = json.dumps(
            body, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
        )
        return hashlib.sha1(text.encode("utf-8"), usedforsecurity=False).hexdigest()

    rng = random.Random("hash")
    for row in [r for r in _rows(rng, 300, 6) if isinstance(r, dict)] + [
        {1: "a", "1": "b"},
        {"é": "ü"},
    ]:
        try:
            expected = reference(row)
        except (TypeError, ValueError):
            continue
        assert row_hash(row) == expected and row_hash(row, exclude=["c1"]) == reference(row, ["c1"])
        digest, text = row_hash_json(row)
        assert digest == expected and json.loads(text) == json.loads(json.dumps(row, default=str))


def test_cap_record_values_shortcut_returns_the_row_itself_only_when_nothing_is_cut():
    rng = random.Random("caps")
    for row in [r for r in _rows(rng, 300, 6) if isinstance(r, dict)]:
        for limit in (0, 2, 10, 4000):
            cut: dict = {}
            expected = _cap(row, limit, "", cut)
            if cut:
                expected[TRUNCATED_KEY] = dict(cut)
            got = cap_record_values(row, limit)
            assert (got is row) == (not cut)
            assert json.dumps(got, default=str, sort_keys=True) == json.dumps(
                expected if cut else row, default=str, sort_keys=True
            )
