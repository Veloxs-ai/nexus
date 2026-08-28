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
