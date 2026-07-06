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

from nexus.models import NexusConfig


class ConfigFormatError(Exception):
    """Raised when a config file cannot be parsed in a supported format."""


def load_raw_config(path: Path) -> Any:
    """Parse a JSON (native) or YAML (optional extra) config file.

    JSON needs only the standard library, keeping the platform free of
    third-party parsers. YAML files still load when PyYAML is installed
    (`pip install nexus-enterprise-ai[yaml]`); parsing always uses
    `yaml.safe_load` — never `yaml.load`.
    """
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except ModuleNotFoundError as exc:
            raise ConfigFormatError(
                f"{path} is YAML, but PyYAML is not installed. Use a JSON config "
                "or install the optional extra: pip install nexus-enterprise-ai[yaml]"
            ) from exc
        return yaml.safe_load(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigFormatError(f"{path} is not valid JSON: {exc}") from exc


def load_config(path: Path) -> NexusConfig:
    return NexusConfig.model_validate(load_raw_config(path))
