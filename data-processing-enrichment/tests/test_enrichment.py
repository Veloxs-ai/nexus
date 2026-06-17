# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

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

