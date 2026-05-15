from nexus_observability.metrics import MetricRecorder
from nexus_observability.models import MetricKind


def test_metric_recorder_writes_jsonl(sample_config, tmp_path):
    recorder = MetricRecorder(sample_config.storage, tmp_path)

    event = recorder.record(
        "experience-api-engagement",
        "request_latency_ms",
        42,
        MetricKind.HISTOGRAM,
        "default",
    )

    records = recorder.read_all()
    assert records[0]["event_id"] == event.event_id
    assert records[0]["kind"] == "histogram"

