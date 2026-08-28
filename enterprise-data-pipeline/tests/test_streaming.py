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

from nexus_pipeline.models import IngestionMode
from nexus_pipeline.streaming import KafkaStreamConnector, run_stream


class FakeKafkaStreamConnector:
    def __init__(self, source):
        self.source = source

    def read(self, checkpoint=None):
        return [
            {"event_id": "e1", "occurred_at": "2026-05-06T00:00:00Z"},
            {"event_id": "e2", "occurred_at": "2026-05-06T00:01:00Z"},
        ]


def test_run_stream_validates_connector_records(monkeypatch, make_source):
    monkeypatch.setattr("nexus_pipeline.streaming.KafkaStreamConnector", FakeKafkaStreamConnector)
    source = make_source(
        mode=IngestionMode.STREAMING,
        connector="kafka",
        primary_key="event_id",
        event_time_field="occurred_at",
    )

    events = run_stream("customer_events", source)

    assert [event.primary_key for event in events] == ["e1", "e2"]
    assert {event.source for event in events} == {"customer_events"}


def test_streaming_connector_reads_jsonl_source(tmp_path, make_source):
    input_path = tmp_path / "customer_events.jsonl"
    input_path.write_text(
        '{"event_id":"e1","customer_id":"c1","event_type":"login","occurred_at":"2026-05-06T00:00:00Z"}\n',
        encoding="utf-8",
    )
    source = make_source(
        mode=IngestionMode.STREAMING,
        connector="kafka",
        primary_key="event_id",
        event_time_field="occurred_at",
        required_fields=["event_id", "customer_id", "event_type", "occurred_at"],
        connection={"source_uri": str(input_path)},
    )

    records = list(KafkaStreamConnector(source).read())

    assert records[0]["event_type"] == "login"
