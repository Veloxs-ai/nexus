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

from pydantic import BaseModel


def resolve_uri(uri: str, base_dir: Path) -> Path:
    path = Path(uri)
    if path.is_absolute():
        return path
    resolved = (base_dir / path).resolve()
    if not resolved.is_relative_to(base_dir.resolve()):
        raise ValueError(f"URI {uri!r} resolves outside base directory {base_dir}")
    return resolved


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
            if isinstance(record, BaseModel):
                payload = record.model_dump(mode="json")
            else:
                payload = record
            output_file.write(json.dumps(payload, sort_keys=True) + "\n")
            count += 1
    return count

