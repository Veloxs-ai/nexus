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

from pydantic import BaseModel


def resolve_uri(uri: str, base_dir: Path) -> Path:
    path = Path(uri)
    # URIs come from trusted operator config; layers reference sibling-layer
    # outputs via relative paths (e.g. ../other-layer/data/...), so no containment.
    return path if path.is_absolute() else (base_dir / path)


def append_jsonl(uri: str, base_dir: Path, record: BaseModel | dict[str, Any]) -> None:
    path = resolve_uri(uri, base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = record.model_dump(mode="json") if isinstance(record, BaseModel) else record
    with path.open("a", encoding="utf-8") as output:
        output.write(json.dumps(payload, sort_keys=True) + "\n")


def read_jsonl(uri: str, base_dir: Path) -> list[dict[str, Any]]:
    path = resolve_uri(uri, base_dir)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as input_file:
        return [json.loads(line) for line in input_file if line.strip()]

