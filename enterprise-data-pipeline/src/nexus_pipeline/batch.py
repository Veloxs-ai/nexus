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

import csv
import json
from pathlib import Path
from typing import Any

from .config import SourceConfig
from .integrity import CheckpointStore, latest_checkpoint, validate_records


class FileDropConnector:
    def __init__(self, source: SourceConfig) -> None:
        self.source = source

    def read(self, checkpoint: str | None = None) -> list[dict[str, Any]]:
        source_uri = self.source.connection["source_uri"]
        if source_uri.startswith("s3://"):
            raise NotImplementedError(
                "S3 file-drop reading requires a production object-store adapter"
            )

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
    if detected_format in {"txt", "md", "markdown", "text"}:
        with path.open("r", encoding="utf-8") as input_file:
            content = input_file.read()
        return [
            {
                "document_id": path.stem,
                "title": path.stem.replace("_", " ").title(),
                "body": content,
                "filename": path.name,
            }
        ]
    raise ValueError(f"Unsupported batch file format: {detected_format}")


def run_batch(source_name: str, source: SourceConfig, checkpoint_store: CheckpointStore) -> int:
    checkpoint = checkpoint_store.read(source_name)
    connector = FileDropConnector(source)
    result = validate_records(source_name, source, connector.read(checkpoint))
    checkpoint = latest_checkpoint(result.valid)
    if checkpoint:
        checkpoint_store.write(source_name, checkpoint)
    return len(result.valid)
