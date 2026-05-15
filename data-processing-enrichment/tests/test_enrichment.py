from nexus_processing.enrichment import build_text, extract_metadata


def test_extract_metadata_finds_tags_entities_emails_dates_and_classification(make_metadata_config):
    metadata = extract_metadata(
        "Acme Corp requires MFA access review. Email security@example.com by 2026-07-01.",
        make_metadata_config(),
    )

    assert metadata["classification"] == "security"
    assert metadata["tags"] == ["security"]
    assert "security@example.com" in metadata["emails"]
    assert "2026-07-01" in metadata["dates"]
    assert "Acme Corp" in metadata["entities"]


def test_build_text_uses_existing_fields_only():
    text = build_text({"title": "Policy", "body": "Use encryption"}, ["title", "body", "missing"])

    assert text == "Policy Use encryption"

