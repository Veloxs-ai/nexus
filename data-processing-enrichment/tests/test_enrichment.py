# Copyright 2026 Veloxs AI Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

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
