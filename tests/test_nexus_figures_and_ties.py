# Copyright 2026 Veloxs AI Inc.
# SPDX-License-Identifier: Apache-2.0
"""Grounding compares figures written in words or as long dates with digits; records SQL breaks
ties between groups like the Python engine (the empty group last); a bad limit says why."""

from __future__ import annotations

import json
import sqlite3

import pytest

from nexus.figure_text import spell_figures
from nexus.grounding import check_answer
from nexus.record_eval import evaluate
from nexus.record_spec import RecordQueryError, parse_spec
from nexus.record_sql import ChunkTable, compile_query, read_result
from nexus.table_profile import profile_records


@pytest.mark.parametrize(
    "text, spelled",
    [
        ("thirty days", "30 days"),
        ("one hundred and twenty stores", "120 stores"),
        ("twenty-one", "21"),
        ("two thousand five hundred", "2500"),
        ("two million", "2 million"),
        ("priority-one tickets", "priority-one tickets"),
        ("a one-off fee", "a one-off fee"),
        ("five three two", "five three two"),
        ("March 5, 2026", "2026-03-05"),
        ("5th of March 2026", "2026-03-05"),
        ("Sept. 30 2025", "2025-09-30"),
        ("February 30, 2026", "February 30, 2026"),
    ],
)
def test_spell_figures(text, spelled):
    assert spell_figures(text) == spelled


@pytest.mark.parametrize(
    "passage, claim",
    [
        ("Invoices are payable within thirty days of receipt.", "Invoices are due in 30 days [1]."),
        ("Employees receive twenty days of paid leave.", "Employees receive 20 days of leave [1]."),
        ("There are one hundred and twenty stores.", "There are 120 stores [1]."),
        ("The renewal date is 2026-03-05.", "The contract renews on 5 March 2026 [1]."),
        ("The renewal date is March 5, 2026.", "The contract renews on 2026-03-05 [1]."),
        ("The contract renews on 2026-03-05.", "The contract renews in March 2026 [1]."),
        ("Reviewed in fiscal year 2025 by compliance.", "Compliance reviewed it in FY2025 [1]."),
    ],
)
def test_correct_figures_written_another_way_are_not_unsupported(passage, claim):
    (check,) = check_answer(claim, {1: passage}).checks
    assert check.status != "unsupported", check.reason


@pytest.mark.parametrize(
    "passage, claim",
    [
        ("Invoices are payable within thirty days of receipt.", "Invoices are due in 60 days [1]."),
        ("The renewal date is March 5, 2026.", "The contract renews on 2026-03-06 [1]."),
        ("Reviewed in fiscal year 2025 by compliance.", "Compliance reviewed it in FY2024 [1]."),
    ],
)
def test_changed_figures_are_still_unsupported(passage, claim):
    (check,) = check_answer(claim, {1: passage}).checks
    assert check.status == "unsupported"


ROWS = [
    {"id": i, "s": s, "c": c}
    for i, (s, c) in enumerate(
        [("open", "a"), ("", "a"), (None, "b"), ("shipped", "b"), ("OPEN", "c"), ("", "c")]
    )
]


@pytest.mark.parametrize(
    "spec",
    [
        {"group_by": "s", "metric": "count", "limit": 2},
        {"group_by": ["c", "s"], "metric": "count", "limit": 3},
        {"group_by": "s", "metrics": [{"op": "max", "field": "c"}], "limit": 2},
    ],
)
def test_sql_ties_put_the_empty_group_last_like_python(spec):
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE ch (doc TEXT, chunk_index INT, metadata TEXT)")
    for i, row in enumerate(ROWS):
        db.execute("INSERT INTO ch VALUES ('o', ?, ?)", (i, json.dumps({"record": row})))
    q = parse_spec(spec, profile_records(ROWS))
    expected = evaluate(q, ROWS)
    compiled = compile_query(q, "sqlite", ChunkTable("ch", "c.doc = ?", ("o",), layout="record"))
    got = read_result(compiled, db.execute(compiled.sql, compiled.params).fetchall(), len(ROWS))
    assert (got.text, got.groups) == (expected.text, expected.groups)


@pytest.mark.parametrize("limit", ["5; DROP TABLE ch", "ten", [3]])
def test_a_limit_that_is_not_a_number_says_why(limit):
    with pytest.raises(RecordQueryError, match="limit must be a whole number"):
        parse_spec({"metric": "list", "limit": limit}, profile_records(ROWS))
    assert parse_spec({"metric": "list", "limit": "7"}, profile_records(ROWS)).limit == 7
