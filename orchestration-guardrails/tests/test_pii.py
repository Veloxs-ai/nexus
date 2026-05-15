from nexus_guardrails.config import PiiConfig
from nexus_guardrails.pii import detect_pii, mask_pii


def test_detect_pii_finds_email_ssn_and_phone():
    config = PiiConfig(detectors=["email", "ssn", "phone"])

    findings = detect_pii("Email jane@example.com SSN 123-45-6789 phone 415-555-0100", config)

    assert [finding.message for finding in findings] == [
        "Detected email",
        "Detected ssn",
        "Detected phone",
    ]


def test_mask_pii_replaces_sensitive_values():
    config = PiiConfig(detectors=["email", "ssn"])

    masked = mask_pii("jane@example.com 123-45-6789", config)

    assert masked == "[EMAIL] [SSN]"

