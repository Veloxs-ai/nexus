from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from nexus_pipeline.config import SourceConfig
from nexus_pipeline.models import DataEvent, ValidationResult


def validate_records(
    source_name: str,
    source: SourceConfig,
    records: Iterable[dict[str, Any]],
) -> ValidationResult:
    result = ValidationResult()
    seen_keys: set[Any] = set()

    for record in records:
        missing = [field for field in source.data_schema.required_fields if record.get(field) is None]
        if missing:
            result.invalid.append((record, f"missing required fields: {', '.join(missing)}"))
            continue

        primary_value = record.get(source.primary_key)
        if primary_value in seen_keys:
            continue
        seen_keys.add(primary_value)

        event_time = parse_event_time(record[source.event_time_field])
        result.valid.append(
            DataEvent(
                source=source_name,
                destination=source.destination,
                primary_key=str(primary_value),
                event_time=event_time,
                payload=record,
            )
        )

    return result


def parse_event_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value / 1000 if value > 10_000_000_000 else value)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


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
