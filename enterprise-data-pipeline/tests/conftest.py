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

from typing import Any

import pytest

from nexus_pipeline.config import SourceConfig, SourceSchema
from nexus_pipeline.models import IngestionMode


@pytest.fixture
def make_source():
    def _make_source(
        *,
        mode: IngestionMode = IngestionMode.API,
        connector: str = "rest_api",
        destination: str = "core.records",
        primary_key: str = "id",
        event_time_field: str = "updated_at",
        required_fields: list[str] | None = None,
        connection: dict[str, Any] | None = None,
    ) -> SourceConfig:
        return SourceConfig(
            mode=mode,
            connector=connector,
            destination=destination,
            primary_key=primary_key,
            event_time_field=event_time_field,
            connection=connection or {},
            schema=SourceSchema(required_fields=required_fields or [primary_key, event_time_field]),
        )

    return _make_source
