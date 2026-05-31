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


def test_credit_card_detected_only_when_luhn_valid():
    config = PiiConfig(detectors=["credit_card"])

    valid = detect_pii("card 4111 1111 1111 1111", config)
    invalid = detect_pii("ticket 1234 5678 9012 3456", config)

    assert valid and valid[0].message == "Detected credit_card"
    assert invalid == []


def test_credit_card_mask_only_replaces_luhn_valid():
    config = PiiConfig(detectors=["credit_card"])

    masked = mask_pii("a 4111 1111 1111 1111 b 1234 5678 9012 3456", config)

    assert "[CREDIT_CARD]" in masked
    assert "1234 5678 9012 3456" in masked


def test_detect_pii_sees_through_zero_width_obfuscation():
    config = PiiConfig(detectors=["email"])

    findings = detect_pii("contact jane@​example.com please", config)

    assert findings and findings[0].message == "Detected email"


def test_detect_pii_sees_through_fullwidth_obfuscation():
    config = PiiConfig(detectors=["ssn"])

    findings = detect_pii("ssn １２３-４５-６７８９", config)

    assert findings and findings[0].message == "Detected ssn"
