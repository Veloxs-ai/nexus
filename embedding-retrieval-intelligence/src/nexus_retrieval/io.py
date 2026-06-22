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
from typing import Any


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


def read_json(uri: str, base_dir: Path) -> dict[str, Any]:
    path = resolve_uri(uri, base_dir)
    with path.open("r", encoding="utf-8") as json_file:
        return json.load(json_file)


def write_json(uri: str, base_dir: Path, payload: dict[str, Any]) -> None:
    path = resolve_uri(uri, base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as json_file:
        json.dump(payload, json_file, indent=2, sort_keys=True)
        json_file.write("\n")


def get_path(record: dict[str, Any], path: str, default: Any = None) -> Any:
    current: Any = record
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current

