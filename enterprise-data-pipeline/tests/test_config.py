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

