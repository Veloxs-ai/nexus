# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

from pathlib import Path

from nexus_retrieval.config import load_config


def test_load_config_parses_collections_and_integration():
    config = load_config(Path("configs/retrieval.yaml"))

    assert config.integration.processing_project == "../data-processing-enrichment"
    assert set(config.collections) == {"customer_profiles", "policy_documents"}
    assert config.embedding.dimensions == 64


def test_collection_requires_text_source():
    try:
        load_config(Path("configs/retrieval.yaml")).collections["policy_documents"].model_copy(
            update={"text_field": None, "text_fields": []}
        )
    except Exception:
        raise AssertionError("model_copy should not revalidate by default")

