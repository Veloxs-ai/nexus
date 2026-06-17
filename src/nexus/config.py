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

from pathlib import Path

import yaml

from nexus.models import NexusConfig


def load_config(path: Path) -> NexusConfig:
    with path.open("r", encoding="utf-8") as config_file:
        raw = yaml.safe_load(config_file)
    return NexusConfig.model_validate(raw)

