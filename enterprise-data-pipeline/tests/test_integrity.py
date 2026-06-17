# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

from nexus_pipeline.config import SourceConfig, SourceSchema
from nexus_pipeline.integrity import latest_checkpoint, validate_records
from nexus_pipeline.models import IngestionMode


def test_validate_records_deduplicates_and_rejects_missing_fields():
    source = SourceConfig(
        mode=IngestionMode.API,
        connector="rest_api",
        destination="core.accounts",
        primary_key="account_id",
        event_time_field="updated_at",
        connection={},
        schema=SourceSchema(required_fields=["account_id", "updated_at"]),
    )

    result = validate_records(
        "accounts",
        source,
        [
            {"account_id": "a1", "updated_at": "2026-05-06T00:00:00Z"},
            {"account_id": "a1", "updated_at": "2026-05-06T00:01:00Z"},
            {"account_id": "a2"},
        ],
    )

    assert len(result.valid) == 1
    assert len(result.invalid) == 1
    assert result.valid[0].primary_key == "a1"


def test_latest_checkpoint_uses_latest_event_time():
    source = SourceConfig(
        mode=IngestionMode.BATCH,
        connector="file_drop",
        destination="core.transactions",
        primary_key="transaction_id",
        event_time_field="posted_at",
        connection={},
    )

    result = validate_records(
        "transactions",
        source,
        [
            {"transaction_id": "t1", "posted_at": "2026-05-06T00:00:00Z"},
            {"transaction_id": "t2", "posted_at": "2026-05-06T01:00:00Z"},
        ],
    )

    assert latest_checkpoint(result.valid) == "2026-05-06T01:00:00+00:00"

