from nexus_security.audit import AuditLogger
from nexus_security.config import AuditConfig
from nexus_security.models import AuditEvent, Decision


def test_audit_logger_writes_jsonl(tmp_path):
    logger = AuditLogger(AuditConfig(output_uri="audit.jsonl"), tmp_path)

    logger.record(
        AuditEvent(
            event_type="user.login",
            actor_id="u1",
            tenant_id="tenant-a",
            decision=Decision.ALLOWED,
        )
    )

    records = logger.read_all()
    assert records[0]["event_type"] == "user.login"


def test_audit_logger_can_skip_denied_events(tmp_path):
    logger = AuditLogger(
        AuditConfig(output_uri="audit.jsonl", include_denied_events=False),
        tmp_path,
    )

    logger.record(
        AuditEvent(
            event_type="access.check",
            actor_id="u1",
            tenant_id="tenant-a",
            decision=Decision.DENIED,
        )
    )

    assert logger.read_all() == []

