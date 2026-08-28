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

from pathlib import Path

from nexus_processing.config import load_config
from nexus_processing.models import JobMode
from nexus_processing.pipeline import hydrate_job_defaults


def test_load_config_parses_jobs_and_integration():
    config = load_config(Path("configs/processing.json"))

    assert config.integration.upstream_project == "../enterprise-data-pipeline"
    assert config.integration.raw_landing_contract == "jsonl"
    assert set(config.jobs) == {"customer_profiles", "policy_documents"}
    assert config.jobs["policy_documents"].mode == JobMode.DOCUMENTS


def test_hydrate_job_defaults_applies_chunking_and_metadata():
    config = hydrate_job_defaults(load_config(Path("configs/processing.json")))

    assert config.jobs["policy_documents"].chunking is not None
    assert config.jobs["policy_documents"].chunking.max_tokens == 80
    assert "security" in config.jobs["customer_profiles"].metadata.keyword_tags
