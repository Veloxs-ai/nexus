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
