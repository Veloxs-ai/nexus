from nexus_security.models import AccessRequest, Decision
from nexus_security.service import SecurityGovernanceService


def test_service_check_access_records_audit_and_telemetry(sample_config, tmp_path):
    service = SecurityGovernanceService(sample_config, tmp_path)

    decision = service.check_access(
        AccessRequest(
            role="analyst",
            permission="read:data",
            user_tenant="tenant-a",
            resource_tenant="tenant-a",
            data_scope="customer",
            subject_id="u1",
        )
    )

    assert decision.decision == Decision.ALLOWED
    assert service.audit.read_all()[0]["actor_id"] == "u1"
    assert service.observability.read_all()[0]["metric_name"] == "access_check"


def test_service_encrypt_decrypt_and_tls(sample_config, tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_SECURITY_TEST_KEY", "secret")
    service = SecurityGovernanceService(sample_config, tmp_path)

    encrypted = service.encrypt("hello")

    assert service.decrypt(encrypted) == "hello"
    assert service.tls_allowed("TLSv1.3") is True


def test_service_record_event_writes_audit(sample_config, tmp_path):
    service = SecurityGovernanceService(sample_config, tmp_path)

    service.record_event("ai.ask", "u1", "tenant-a", Decision.ALLOWED)

    assert service.audit.read_all()[0]["event_type"] == "ai.ask"

