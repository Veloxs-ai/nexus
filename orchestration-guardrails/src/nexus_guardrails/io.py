from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def resolve_uri(uri: str, base_dir: Path) -> Path:
    path = Path(uri)
    return path if path.is_absolute() else (base_dir / path).resolve()


def read_json(uri: str, base_dir: Path) -> dict[str, Any]:
    path = resolve_uri(uri, base_dir)
    with path.open("r", encoding="utf-8") as json_file:
        return json.load(json_file)

