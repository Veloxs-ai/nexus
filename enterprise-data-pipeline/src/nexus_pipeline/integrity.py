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

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import SourceConfig
from .models import DataEvent, ValidationResult


def validate_records(
    source_name: str,
    source: SourceConfig,
    records: Iterable[dict[str, Any]],
) -> ValidationResult:
    """Valid events, one per primary key, and the rejected records.

    When a key appears more than once, the newest record wins (latest event time; on a
    tie, the one that came later), so an update in the same batch as its insert is kept.
    Events keep the order in which their keys first appeared.
    """
    result = ValidationResult()
    latest: dict[Any, tuple[datetime, Any, dict[str, Any]]] = {}

    for record in records:
        missing = [
            field for field in source.data_schema.required_fields if record.get(field) is None
        ]
        if missing:
            result.invalid.append((record, f"missing required fields: {', '.join(missing)}"))
            continue

        primary_value = record.get(source.primary_key)
        event_time = parse_event_time(record[source.event_time_field])
        kept = latest.get(primary_value)
        if kept is not None and event_time < kept[0]:
            continue  # an older version of a record already seen
        latest[primary_value] = (event_time, primary_value, record)

    # Events are built for the surviving records only.
    result.valid.extend(
        DataEvent(
            source=source_name,
            destination=source.destination,
            primary_key=str(primary_value),
            event_time=event_time,
            payload=record,
        )
        for event_time, primary_value, record in latest.values()
    )
    return result


def parse_event_time(value: Any) -> datetime:
    """An event time as a timezone-aware datetime (UTC when the value names no zone), so
    epoch numbers, ISO strings with "Z" or an offset, and naive values always compare."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, int | float):
        return datetime.fromtimestamp(value / 1000 if value > 10_000_000_000 else value, tz=UTC)
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


class CheckpointStore:
    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def read(self, source_name: str) -> str | None:
        path = self.root / f"{source_name}.checkpoint"
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8").strip() or None

    def write(self, source_name: str, checkpoint: str) -> None:
        path = self.root / f"{source_name}.checkpoint"
        path.write_text(checkpoint, encoding="utf-8")


def latest_checkpoint(events: Iterable[DataEvent]) -> str | None:
    latest = max((event.event_time for event in events), default=None)
    return latest.isoformat() if latest else None
