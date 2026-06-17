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

import json
from pathlib import Path
from typing import Any, Iterable

from nexus_pipeline.config import SourceConfig
from nexus_pipeline.integrity import validate_records
from nexus_pipeline.models import DataEvent


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
