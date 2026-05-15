from __future__ import annotations

from pathlib import Path

import yaml

from nexus.models import NexusConfig


def load_config(path: Path) -> NexusConfig:
    with path.open("r", encoding="utf-8") as config_file:
        raw = yaml.safe_load(config_file)
    return NexusConfig.model_validate(raw)

