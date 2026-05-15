from nexus_security.config import ObservabilityConfig
from nexus_security.observability import ObservabilityRecorder


def test_observability_recorder_writes_event(tmp_path):
    recorder = ObservabilityRecorder(
        ObservabilityConfig(output_uri="events.jsonl", service_name="security"),
        tmp_path,
    )

    recorder.emit("access_check", 1, {"decision": "allowed"})

    records = recorder.read_all()
    assert records[0]["metric_name"] == "access_check"
    assert records[0]["attributes"] == {"decision": "allowed"}


def test_observability_disabled_skips_event(tmp_path):
    recorder = ObservabilityRecorder(ObservabilityConfig(enabled=False), tmp_path)

    recorder.emit("access_check", 1)

    assert recorder.read_all() == []

