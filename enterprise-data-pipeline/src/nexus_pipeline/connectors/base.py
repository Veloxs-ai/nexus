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

from abc import ABC, abstractmethod
from typing import Any, Iterable

from nexus_pipeline.config import SourceConfig


class Connector(ABC):
    def __init__(self, source: SourceConfig) -> None:
        self.source = source

    @abstractmethod
    def read(self, checkpoint: str | None = None) -> Iterable[dict[str, Any]]:
        """Read source records from the configured system."""

