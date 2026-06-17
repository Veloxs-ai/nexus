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

from nexus_observability.config import StorageConfig
from nexus_observability.io import append_jsonl, read_jsonl
from nexus_observability.models import MetricEvent, MetricKind


class MetricRecorder:
    def __init__(self, storage: StorageConfig, base_dir: Path) -> None:
        self.storage = storage
        self.base_dir = base_dir

    def record(
        self,
        service: str,
        name: str,
        value: float,
        kind: MetricKind = MetricKind.GAUGE,
        tenant: str | None = None,
        attributes: dict | None = None,
    ) -> MetricEvent:
        event = MetricEvent(
            service=service,
            name=name,
            value=value,
            kind=kind,
            tenant=tenant,
            attributes=attributes or {},
        )
        append_jsonl(self.storage.metrics_uri, self.base_dir, event)
        return event

    def read_all(self) -> list[dict]:
        return read_jsonl(self.storage.metrics_uri, self.base_dir)

