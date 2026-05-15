from nexus_observability.traces import TraceRecorder


def test_trace_recorder_writes_span(sample_config, tmp_path):
    recorder = TraceRecorder(sample_config.storage, tmp_path)

    span = recorder.record("experience-api-engagement", "ask", 55, "trace-1")

    records = recorder.read_all()
    assert records[0]["span_id"] == span.span_id
    assert records[0]["trace_id"] == "trace-1"

