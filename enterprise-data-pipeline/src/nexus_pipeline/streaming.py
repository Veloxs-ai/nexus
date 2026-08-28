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

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .config import SourceConfig
from .integrity import validate_records
from .models import DataEvent


class KafkaStreamConnector:
    def __init__(self, source: SourceConfig) -> None:
        self.source = source

    def read(self, checkpoint: str | None = None) -> Iterable[dict[str, Any]]:
        source_uri = self.source.connection.get("source_uri")
        if source_uri:
            with Path(source_uri).open("r", encoding="utf-8") as input_file:
                for line in input_file:
                    if line.strip():
                        yield json.loads(line)
            return

        events = self.source.connection.get("events", [])
        if events:
            yield from events
            return

        raise NotImplementedError("Kafka consumption requires a production Kafka adapter")


def run_stream(source_name: str, source: SourceConfig) -> list[DataEvent]:
    connector = KafkaStreamConnector(source)
    return validate_records(source_name, source, connector.read()).valid
