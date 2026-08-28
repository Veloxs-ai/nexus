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

from nexus_pipeline.config import load_config
from nexus_pipeline.models import IngestionMode


def test_load_config_parses_platform_and_sources():
    config = load_config(Path("configs/sources.json"))

    assert config.platform.raw_landing_uri == "s3://enterprise-raw"
    assert set(config.sources) == {
        "crm_accounts",
        "customer_events",
        "erp_orders",
        "finance_transactions",
    }
    assert config.sources["crm_accounts"].mode == IngestionMode.API
    assert config.sources["crm_accounts"].data_schema.required_fields == [
        "account_id",
        "name",
        "updated_at",
    ]


def test_source_schema_alias_keeps_yaml_field_name(make_source):
    source = make_source(required_fields=["id", "updated_at", "status"])

    assert source.data_schema.required_fields == ["id", "updated_at", "status"]
