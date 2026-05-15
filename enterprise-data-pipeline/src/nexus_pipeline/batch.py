from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from nexus_pipeline.config import SourceConfig
from nexus_pipeline.integrity import CheckpointStore, latest_checkpoint, validate_records


class FileDropConnector:
    def __init__(self, source: SourceConfig) -> None:
        self.source = source

    def read(self, checkpoint: str | None = None) -> list[dict[str, Any]]:
        source_uri = self.source.connection["source_uri"]
        if source_uri.startswith("s3://"):
            raise NotImplementedError("S3 file-drop reading requires a production object-store adapter")

        path = Path(source_uri)
        files = sorted(path.glob("*")) if path.is_dir() else [path]
        records: list[dict[str, Any]] = []
        for file_path in files:
            records.extend(read_file(file_path, self.source.connection.get("file_format")))
        return records


def read_file(path: Path, file_format: str | None = None) -> list[dict[str, Any]]:
    detected_format = (file_format or path.suffix.removeprefix(".")).lower()
    if detected_format == "jsonl":
        with path.open("r", encoding="utf-8") as input_file:
            return [json.loads(line) for line in input_file if line.strip()]
    if detected_format == "json":
        with path.open("r", encoding="utf-8") as input_file:
            payload = json.load(input_file)
        return payload if isinstance(payload, list) else [payload]
    if detected_format == "csv":
        with path.open("r", encoding="utf-8", newline="") as input_file:
            return list(csv.DictReader(input_file))
    raise ValueError(f"Unsupported batch file format: {detected_format}")


def run_batch(source_name: str, source: SourceConfig, checkpoint_store: CheckpointStore) -> int:
    checkpoint = checkpoint_store.read(source_name)
    connector = FileDropConnector(source)
    result = validate_records(source_name, source, connector.read(checkpoint))
    checkpoint = latest_checkpoint(result.valid)
    if checkpoint:
        checkpoint_store.write(source_name, checkpoint)
    return len(result.valid)
