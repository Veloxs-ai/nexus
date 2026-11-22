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

"""Updates win over inserts, inputs are never mutated, times always compare."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime

from nexus_pipeline.batch import FileDropConnector
from nexus_pipeline.cdc import run_cdc
from nexus_pipeline.integrity import latest_checkpoint, parse_event_time, validate_records
from nexus_pipeline.models import IngestionMode


def _message(op: str, amount: int, ts: int) -> dict:
    return {"payload": {"op": op, "after": {"order_id": "o1", "amount": amount}, "ts_ms": ts}}


def test_cdc_keeps_the_update_not_the_stale_insert(make_source):
    source = make_source(
        mode=IngestionMode.CDC,
        connector="debezium",
        primary_key="order_id",
        event_time_field="source_ts_ms",
        required_fields=["order_id", "source_ts_ms"],
    )
    messages = [_message("c", 10, 1_000), _message("u", 25, 2_000), _message("c", 5, 3_000)]
    messages[2]["payload"]["after"]["order_id"] = "o2"
    original = copy.deepcopy(messages)
    events = run_cdc("orders", source, messages)
    assert messages == original  # the caller's dicts are untouched
    assert [(e.primary_key, e.payload["amount"]) for e in events] == [("o1", 25), ("o2", 5)]
    assert events[0].operation == "update"


def test_older_redelivery_does_not_replace_newer_record(make_source):
    source = make_source(primary_key="id", event_time_field="ts", required_fields=["id", "ts"])
    rows = [
        {"id": "a", "ts": "2026-05-06T02:00:00Z", "v": "new"},
        {"id": "a", "ts": "2026-05-06T01:00:00Z", "v": "old"},
    ]
    assert validate_records("s", source, rows).valid[0].payload["v"] == "new"


def test_event_times_are_aware_and_comparable():
    times = [
        parse_event_time(v)
        for v in (1_778_025_600_000, "2026-05-06T00:00:00", "2026-05-06T01:00:00Z")
    ]
    assert all(t.tzinfo is not None for t in times)
    assert times[0] == datetime.fromtimestamp(1_778_025_600, tz=UTC)
    assert times[0] == times[1] < times[2]  # naive ISO is read as UTC


def test_latest_checkpoint_on_mixed_inputs(make_source):
    source = make_source(primary_key="id", event_time_field="ts", required_fields=["id", "ts"])
    rows = [{"id": "a", "ts": 1_778_025_600_000}, {"id": "b", "ts": "2026-01-01T00:00:00Z"}]
    assert (
        latest_checkpoint(validate_records("s", source, rows).valid) == "2026-05-06T00:00:00+00:00"
    )


def test_file_drop_reads_only_records_after_the_checkpoint(tmp_path, make_source):
    path = tmp_path / "drop.jsonl"
    rows = [
        {"id": "1", "ts": "2026-05-06T00:00:00Z"},
        {"id": "2", "ts": "2026-05-06T02:00:00Z"},
        {"id": "3"},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    source = make_source(
        mode=IngestionMode.BATCH,
        connector="file_drop",
        primary_key="id",
        event_time_field="ts",
        connection={"source_uri": str(path), "file_format": "jsonl"},
    )
    connector = FileDropConnector(source)
    assert [r["id"] for r in connector.read()] == ["1", "2", "3"]
    assert [r["id"] for r in connector.read("2026-05-06T01:00:00+00:00")] == ["2", "3"]
