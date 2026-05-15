from nexus_observability.logging import StructuredLogger
from nexus_observability.models import Severity


def test_structured_logger_writes_jsonl(sample_config, tmp_path):
    logger = StructuredLogger(sample_config.storage, tmp_path)

    event = logger.write("orchestration-guardrails", Severity.INFO, "allowed", tenant="default")

    records = logger.read_all()
    assert records[0]["event_id"] == event.event_id
    assert records[0]["severity"] == "info"
    assert records[0]["message"] == "allowed"

