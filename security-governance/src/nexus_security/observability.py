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

from nexus_security.config import ObservabilityConfig
from nexus_security.io import append_jsonl, read_jsonl
from nexus_security.models import TelemetryEvent


class ObservabilityRecorder:
    def __init__(self, config: ObservabilityConfig, base_dir: Path) -> None:
        self.config = config
        self.base_dir = base_dir

    def emit(self, metric_name: str, value: float, attributes: dict | None = None) -> None:
        if not self.config.enabled:
            return
        append_jsonl(
            self.config.output_uri,
            self.base_dir,
            TelemetryEvent(
                service_name=self.config.service_name,
                metric_name=metric_name,
                value=value,
                attributes=attributes or {},
            ),
        )

    def read_all(self) -> list[dict]:
        return read_jsonl(self.config.output_uri, self.base_dir)

