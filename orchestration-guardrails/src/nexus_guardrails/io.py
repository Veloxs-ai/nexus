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
    if path.is_absolute():
        return path
    resolved = (base_dir / path).resolve()
    if not resolved.is_relative_to(base_dir.resolve()):
        raise ValueError(f"URI {uri!r} resolves outside base directory {base_dir}")
    return resolved


def read_json(uri: str, base_dir: Path) -> dict[str, Any]:
    path = resolve_uri(uri, base_dir)
    with path.open("r", encoding="utf-8") as json_file:
        return json.load(json_file)

