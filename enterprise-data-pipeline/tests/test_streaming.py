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
