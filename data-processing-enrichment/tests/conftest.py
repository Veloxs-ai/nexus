# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

from __future__ import annotations

import pytest

from nexus_processing.config import MetadataConfig, ProcessingJobConfig, TransformConfig
from nexus_processing.models import JobMode


def make_record_job() -> ProcessingJobConfig:
    return ProcessingJobConfig(
        mode=JobMode.RECORDS,
        input_uri="input.jsonl",
        output_uri="output.jsonl",
        primary_key="customer_id",
        text_fields=["notes"],
        transformations=TransformConfig(
            trim_strings=True,
            normalize_case_fields={"status": "lower"},
            rename_fields={"customer_name": "name"},
            default_values={"lifecycle_stage": "unknown"},
        ),
    )


@pytest.fixture
def make_metadata_config():
    def _make_metadata_config() -> MetadataConfig:
        return MetadataConfig(
            keyword_tags={
                "security": ["mfa", "access"],
                "finance": ["invoice", "payment"],
                "customer": ["renewal", "support"],
            }
        )

    return _make_metadata_config
