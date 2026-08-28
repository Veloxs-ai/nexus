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
