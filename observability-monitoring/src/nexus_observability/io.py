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
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def resolve_uri(uri: str, base_dir: Path) -> Path:
    path = Path(uri)
    # URIs come from trusted operator config; layers reference sibling-layer
    # outputs via relative paths (e.g. ../other-layer/data/...), so no containment.
    return path if path.is_absolute() else (base_dir / path)


def append_jsonl(uri: str, base_dir: Path, record: BaseModel | dict[str, Any]) -> None:
    path = resolve_uri(uri, base_dir)
    payload = record.model_dump(mode="json") if isinstance(record, BaseModel) else record
    line = json.dumps(payload, sort_keys=True) + "\n"
    try:  # the directory exists after the first append: no mkdir/stat per event
        output = path.open("a", encoding="utf-8")
    except FileNotFoundError:
        path.parent.mkdir(parents=True, exist_ok=True)
        output = path.open("a", encoding="utf-8")
    with output:
        output.write(line)


def read_jsonl(uri: str, base_dir: Path) -> list[dict[str, Any]]:
    return list(iter_jsonl(uri, base_dir))


def iter_jsonl(uri: str, base_dir: Path) -> Iterator[dict[str, Any]]:
    """The records of a JSONL file one at a time (the file is never held in memory whole)."""
    path = resolve_uri(uri, base_dir)
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as input_file:
        for line in input_file:
            if line.strip():
                yield json.loads(line)
