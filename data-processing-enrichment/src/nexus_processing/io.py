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

from pydantic import BaseModel


def resolve_uri(uri: str, base_dir: Path) -> Path:
    path = Path(uri)
    # URIs come from trusted operator config; layers reference sibling-layer
    # outputs via relative paths (e.g. ../other-layer/data/...), so no containment.
    return path if path.is_absolute() else (base_dir / path)


def read_jsonl(uri: str, base_dir: Path) -> list[dict[str, Any]]:
    path = resolve_uri(uri, base_dir)
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as jsonl_file:
        for line_number, line in enumerate(jsonl_file, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                records.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}") from exc
    return records


def write_jsonl(uri: str, base_dir: Path, records: Iterable[BaseModel | dict[str, Any]]) -> int:
    path = resolve_uri(uri, base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as output_file:
        for record in records:
            payload = record.model_dump(mode="json") if isinstance(record, BaseModel) else record
            output_file.write(json.dumps(payload, sort_keys=True) + "\n")
            count += 1
    return count
