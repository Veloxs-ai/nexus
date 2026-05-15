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
